import asyncio
import logging
import signal
import socket
from typing import cast, override

from zeroconf import ServiceInfo

from cannelloni import build_cannelloni_packet, parse_cannelloni_packet
from clock import SystemClock
from config_loader import ServerConfig
from mdns import mdns_service
from node import DroneCANMockNode
from node_factory import NodeConfig, build_default_node
from scheduler import PublisherScheduler

logger = logging.getLogger(__name__)

CanFrame = tuple[int, bytes]
RemoteAddr = tuple[str, int]


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
    def __init__(self, node: DroneCANMockNode, peer_timeout: float = 10.0, max_peers: int = 64) -> None:
        self.node: DroneCANMockNode = node
        self.transport: asyncio.DatagramTransport | None = None
        self.seq_no: int = 0
        self.peer_timeout: float = max(0.5, float(peer_timeout))
        self.max_peers: int = max(1, int(max_peers))
        self.active_remotes: dict[RemoteAddr, float] = {}

    @override
    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    @override
    def datagram_received(self, data: bytes, addr: RemoteAddr) -> None:
        now = asyncio.get_running_loop().time()
        is_new_remote = addr not in self.active_remotes
        if is_new_remote and len(self.active_remotes) >= self.max_peers:
            oldest_addr, _ = min(self.active_remotes.items(), key=lambda item: item[1])
            logger.warning(
                '[System] Max peers reached (%s). Evicting oldest remote %s:%s to admit %s:%s.',
                self.max_peers,
                oldest_addr[0],
                oldest_addr[1],
                addr[0],
                addr[1],
            )
            _ = self.active_remotes.pop(oldest_addr, None)

        if is_new_remote:
            logger.info('[System] Remote client connected: %s:%s. Starting periodic broadcasts.', addr[0], addr[1])
        self.active_remotes[addr] = now

        resp_frames: list[CanFrame] = []
        try:
            parsed_frames = parse_cannelloni_packet(data)
        except Exception:
            logger.exception('Failed to parse incoming cannelloni packet from %s:%s', addr[0], addr[1])
            return

        for can_id, frame_data in parsed_frames:
            try:
                resp = self.node.handle_frame(can_id, frame_data)
            except Exception:
                logger.exception('Node frame handler failed for CAN ID 0x%08X', can_id)
                continue
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
        try:
            pkt = build_cannelloni_packet(self.seq_no, frames)
        except Exception:
            logger.exception('Failed to build cannelloni packet')
            return
        self.transport.sendto(pkt, addr)
        self.seq_no = (self.seq_no + 1) & 0xFF

    def get_active_remotes(self, now: float) -> list[RemoteAddr]:
        stale = [addr for addr, ts in self.active_remotes.items() if now - ts > self.peer_timeout]
        for addr in stale:
            logger.info('[System] Remote client expired: %s:%s', addr[0], addr[1])
            _ = self.active_remotes.pop(addr, None)
        return list(self.active_remotes.keys())


async def publisher_task(node: DroneCANMockNode, protocol: CannelloniProtocol) -> None:
    scheduler = PublisherScheduler(node)
    try:
        while True:
            now = asyncio.get_running_loop().time()
            remotes = protocol.get_active_remotes(now)
            has_remotes = bool(remotes)

            pub_frames = scheduler.collect_frames(has_remotes)
            if pub_frames:
                for remote in remotes:
                    protocol.send_packet(pub_frames, remote)

            timeout = scheduler.next_sleep(has_remotes)
            await asyncio.sleep(timeout)
    except asyncio.CancelledError:
        pass


async def run_server(config: ServerConfig) -> None:
    clock = SystemClock()
    node_config = NodeConfig(
        node_id=config['node_id'],
        node_name=config['node_name'],
        priority=config['priority'],
        heartbeat_interval=config['heartbeat_interval'],
        gpx_path=config['gpx'],
        ice_config=config['ice_reciprocating'],
        fuel_tank_config=config['ice_fuel_tank'],
        reassembler_session_timeout=config['reassembler_session_timeout'],
    )
    node = build_default_node(node_config, clock)

    local_ip = get_local_ip()
    local_ip_bytes = socket.inet_aton(local_ip)

    service_info = ServiceInfo(
        '_cannelloni._udp.local.',
        'avionics-dronecan._cannelloni._udp.local.',
        addresses=[local_ip_bytes],
        port=config['local_port'],
        properties={},
        server='mockavionics.local.',
    )
    async with mdns_service(service_info):
        logger.info('╔══════════════════════════════════════════════════════════╗')
        logger.info('║  Cannelloni DroneCAN Mock Node                         ║')
        logger.info('╠══════════════════════════════════════════════════════════╣')
        logger.info('║  Local port:   %-40s║', config['local_port'])
        logger.info('║  mDNS Target:  %s:%-35s║', local_ip, config['local_port'])
        logger.info('║  Node ID:      %-40s║', config['node_id'])
        logger.info('║  Node Name:    %-40s║', config['node_name'])
        logger.info('║  CAN ID:       0x%08X%s║', node.heartbeat_can_id, ' ' * 30)
        logger.info('╠══════════════════════════════════════════════════════════╣')
        logger.info('║  Heartbeat + GetNodeInfo + ICE + DNA (Waiting for client...) ║')
        logger.info('╚══════════════════════════════════════════════════════════╝')

        loop = asyncio.get_running_loop()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', config['local_port']))
        sock.setblocking(False)

        transport, protocol = await loop.create_datagram_endpoint(
            lambda: CannelloniProtocol(node, config['peer_timeout'], config['max_peers']),
            sock=sock,
        )

        pub_task = asyncio.create_task(publisher_task(node, protocol))

        stop_event = asyncio.Event()

        def shutdown_handler() -> None:
            _ = stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                _ = loop.add_signal_handler(sig, shutdown_handler)
            except NotImplementedError:
                pass

        try:
            _ = await stop_event.wait()
        finally:
            logger.info('Stopping...')
            _ = pub_task.cancel()
            try:
                await pub_task
            except asyncio.CancelledError:
                pass

            _ = transport.close()
            _ = sock.close()
            logger.info('Stopped.')
