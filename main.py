#!/usr/bin/env python3
"""
Cannelloni CAN Mock Server - DroneCAN Node Simulator

Simulates a DroneCAN (UAVCAN v0) node that:
  - Broadcasts uavcan.protocol.NodeStatus heartbeat every 1 second
  - Responds to uavcan.protocol.GetNodeInfo service requests with node name
  - Implements Dynamic Node Allocation (DNA)

Bidirectional cannelloni setup:
  Mock server (port 20001) ←→ cannelloni (port 20000) ←→ vcan0

Usage:
  python3 main.py --config config.yaml
"""

import argparse
import asyncio
import socket
import signal
import json
import yaml
import logging
from collections.abc import Awaitable, Mapping
from typing import Protocol, cast, override
from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf

from constants import DRONECAN_NODE_ID, DRONECAN_NODE_NAME, DRONECAN_PRIORITY_DEFAULT
from cannelloni import build_cannelloni_packet, parse_cannelloni_packet
from node import DroneCANMockNode
from clock import SystemClock

logger = logging.getLogger(__name__)

CanFrame = tuple[int, bytes]
RemoteAddr = tuple[str, int]
ConfigValue = int | float | str
Config = dict[str, ConfigValue]


class AsyncZeroconfProtocol(Protocol):
    def async_register_service(self, info: ServiceInfo) -> Awaitable[object]: ...

    def async_unregister_service(self, info: ServiceInfo) -> Awaitable[object]: ...

    def async_close(self) -> Awaitable[object]: ...

# Default configuration values (without host and remote_port, as they are dynamically learned)
DEFAULT_CONFIG: Config = {
    'local_port': 20001,
    'node_id': DRONECAN_NODE_ID,
    'node_name': DRONECAN_NODE_NAME,
    'priority': DRONECAN_PRIORITY_DEFAULT,
    'heartbeat_interval': 1.0,
    'gpx': 'assets/flight.gpx'
}

def get_local_ip() -> str:
    ip: str = '127.0.0.1'
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = cast(tuple[str, int], s.getsockname())[0]
    except Exception:
        pass
    finally:
        s.close()
    return ip


class CannelloniProtocol(asyncio.DatagramProtocol):
    def __init__(self, node: DroneCANMockNode) -> None:
        self.node: DroneCANMockNode = node
        self.transport: asyncio.DatagramTransport | None = None
        self.seq_no: int = 0
        self.active_remote: RemoteAddr | None = None

    @override
    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    @override
    def datagram_received(self, data: bytes, addr: RemoteAddr) -> None:
        # Dynamically discover/update the remote client address
        if self.active_remote != addr:
            logger.info(f"[System] Remote client connected: {addr[0]}:{addr[1]}. Starting periodic broadcasts.")
            self.active_remote = addr

        resp_frames: list[CanFrame] = []
        for can_id, frame_data in parse_cannelloni_packet(data):
            resp = self.node.handle_frame(can_id, frame_data)
            if resp:
                resp_frames.extend(resp)
        
        if resp_frames:
            if self.transport is None:
                return
            pkt = build_cannelloni_packet(self.seq_no, resp_frames)
            self.transport.sendto(pkt, addr)
            self.seq_no = (self.seq_no + 1) & 0xFF

    def send_packet(self, frames: list[CanFrame], addr: RemoteAddr) -> None:
        if not self.transport or not frames:
            return
        pkt = build_cannelloni_packet(self.seq_no, frames)
        self.transport.sendto(pkt, addr)
        self.seq_no = (self.seq_no + 1) & 0xFF


async def publisher_task(node: DroneCANMockNode, protocol: CannelloniProtocol) -> None:
    try:
        while True:
            if protocol.active_remote is None:
                await asyncio.sleep(0.1)
                continue
                
            pub_frames = node.process_publishers()
            if pub_frames:
                protocol.send_packet(pub_frames, protocol.active_remote)
            
            timeout = node.get_timeout()
            await asyncio.sleep(timeout)
    except asyncio.CancelledError:
        pass


async def run_server(config: Config) -> None:
    # Setup clock and node
    clock = SystemClock()
    node = DroneCANMockNode(
        int(config['node_id']),
        str(config['node_name']),
        int(config['priority']),
        float(config['heartbeat_interval']),
        str(config['gpx']),
        clock
    )
    
    local_ip = get_local_ip()
    local_ip_bytes = socket.inet_aton(local_ip)
    
    service_info = ServiceInfo(
        "_cannelloni._udp.local.",
        "avionics-dronecan._cannelloni._udp.local.",
        addresses=[local_ip_bytes],
        port=int(config['local_port']),
        properties={},
        server="mockavionics.local.",
    )
    aiozc: AsyncZeroconfProtocol = cast(AsyncZeroconfProtocol, AsyncZeroconf())
    _ = await aiozc.async_register_service(service_info)

    logger.info("╔══════════════════════════════════════════════════════════╗")
    logger.info("║  Cannelloni DroneCAN Mock Node                         ║")
    logger.info("╠══════════════════════════════════════════════════════════╣")
    logger.info(f"║  Local port:   {config['local_port']:<40}║")
    logger.info(f"║  mDNS Target:  {local_ip}:{config['local_port']:<35}║")
    logger.info(f"║  Node ID:      {config['node_id']:<40}║")
    logger.info(f"║  Node Name:    {config['node_name']:<40}║")
    logger.info(f"║  CAN ID:       0x{node.heartbeat_can_id:08X}{' ' * 30}║")
    logger.info("╠══════════════════════════════════════════════════════════╣")
    logger.info("║  Heartbeat + GetNodeInfo + DNA  (Waiting for client...) ║")
    logger.info("╚══════════════════════════════════════════════════════════╝")

    loop = asyncio.get_running_loop()
    
    # Setup datagram socket endpoint
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', int(config['local_port'])))
    sock.setblocking(False)

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: CannelloniProtocol(node),
        sock=sock
    )
    
    # Start periodic publisher task
    pub_task = asyncio.create_task(publisher_task(node, protocol))

    stop_event = asyncio.Event()

    def shutdown_handler() -> None:
        _ = stop_event.set()

    # Register signals for clean shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            _ = loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            pass

    try:
        _ = await stop_event.wait()
    finally:
        logger.info("Stopping...")
        _ = pub_task.cancel()
        try:
            await pub_task
        except asyncio.CancelledError:
            pass
        
        _ = transport.close()
        _ = await aiozc.async_unregister_service(service_info)
        _ = await aiozc.async_close()
        _ = sock.close()
        logger.info("Stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Cannelloni DroneCAN Mock Node')
    _ = parser.add_argument('--config', default='config.yaml',
                            help='Path to YAML or JSON config file (default: config.yaml)')
    _ = parser.add_argument('--log-level', default='INFO',
                            choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                            help='Set the logging level (default: INFO)')
    args = parser.parse_args()
    config_path = cast(str, args.config)
    log_level_name = cast(str, args.log_level)

    # Configure logging
    log_level = int(getattr(logging, log_level_name.upper(), logging.INFO))
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    config = DEFAULT_CONFIG.copy()

    try:
        with open(config_path, 'r') as f:
            if config_path.endswith(('.yaml', '.yml')):
                loaded_raw: object = cast(object, yaml.safe_load(f))
            else:
                loaded_raw = cast(object, json.load(f))

            if isinstance(loaded_raw, Mapping):
                loaded_map = cast(Mapping[str, object], loaded_raw)
                # Merge loaded configuration parameters
                for key, val in loaded_map.items():
                    norm_key = key.replace('-', '_')
                    if norm_key in config:
                        default_val = config[norm_key]
                        if isinstance(default_val, bool):
                            config[norm_key] = bool(val)
                        elif isinstance(default_val, int):
                            if isinstance(val, (int, float, str, bool)):
                                config[norm_key] = int(val)
                            else:
                                config[norm_key] = default_val
                        elif isinstance(default_val, float):
                            if isinstance(val, (int, float, str, bool)):
                                config[norm_key] = float(val)
                            else:
                                config[norm_key] = default_val
                        else:
                            config[norm_key] = str(val)
                    else:
                        config[norm_key] = str(val)
        logger.info(f"Loaded configuration from {config_path}")
    except FileNotFoundError:
        if config_path != 'config.yaml':
            logger.error(f"Error: Configuration file {config_path} not found.")
            return
        else:
            logger.warning("Warning: Default config.yaml not found. Running with default settings.")
    except Exception as e:
        logger.error(f"Failed to load config {config_path}: {e}")
        return

    try:
        asyncio.run(run_server(config))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

