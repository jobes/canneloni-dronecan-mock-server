#!/usr/bin/env python3
"""
Cannelloni CAN Mock Server - DroneCAN Node Simulator

Simulates a DroneCAN (UAVCAN v0) node that:
  - Broadcasts uavcan.protocol.NodeStatus heartbeat every 1 second
  - Responds to uavcan.protocol.GetNodeInfo service requests with node name

Bidirectional cannelloni setup:
  Mock server (port 20001) ←→ cannelloni (port 20000) ←→ vcan0

Usage:
  python3 cannelloni_dronecan_heartbeat.py --host <CANNELLONI_IP>
"""

import argparse
import select
import socket
import struct
import time
import signal

from constants import (
    DRONECAN_NODE_ID,
    DRONECAN_NODE_NAME,
    DRONECAN_NODESTATUS_DTID,
    DRONECAN_GETNODEINFO_DTID,
    DRONECAN_GETNODEINFO_SIGNATURE,
    DRONECAN_PRIORITY_DEFAULT
)
from can_utils import build_message_can_id, build_service_can_id, parse_can_id
from dronecan import build_node_status, build_tail_byte, build_getnodeinfo_response, build_multi_frame
from cannelloni import build_cannelloni_packet, parse_cannelloni_packet

def main():
    parser = argparse.ArgumentParser(
        description='Cannelloni DroneCAN Mock Node')
    parser.add_argument('--host', default='127.0.0.1',
                        help='Cannelloni remote IP (default: 127.0.0.1)')
    parser.add_argument('--remote-port', type=int, default=20000,
                        help='Cannelloni remote UDP port (default: 20000)')
    parser.add_argument('--local-port', type=int, default=20001,
                        help='Local UDP port to bind (default: 20001)')
    parser.add_argument('--node-id', type=int, default=DRONECAN_NODE_ID,
                        help=f'DroneCAN Node ID (default: {DRONECAN_NODE_ID})')
    parser.add_argument('--node-name', default=DRONECAN_NODE_NAME,
                        help=f'Node name (default: {DRONECAN_NODE_NAME})')
    parser.add_argument('--priority', type=int, default=DRONECAN_PRIORITY_DEFAULT,
                        help=f'CAN priority (default: {DRONECAN_PRIORITY_DEFAULT})')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Heartbeat interval in seconds (default: 1.0)')
    args = parser.parse_args()

    heartbeat_can_id = build_message_can_id(
        args.priority, DRONECAN_NODESTATUS_DTID, args.node_id)

    # UDP socket — bind to fixed local port for bidirectional communication
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', args.local_port))

    remote = (args.host, args.remote_port)

    running = True
    def signal_handler(sig, frame):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    seq_no = 0
    heartbeat_tid = 0
    start_time = time.monotonic()
    last_heartbeat = 0.0

    print(f"╔══════════════════════════════════════════════════════════╗")
    print(f"║  Cannelloni DroneCAN Mock Node                         ║")
    print(f"╠══════════════════════════════════════════════════════════╣")
    print(f"║  Remote:       {args.host}:{args.remote_port:<29}║")
    print(f"║  Local port:   {args.local_port:<40}║")
    print(f"║  Node ID:      {args.node_id:<40}║")
    print(f"║  Node Name:    {args.node_name:<40}║")
    print(f"║  CAN ID:       0x{heartbeat_can_id:08X}{' ' * 30}║")
    print(f"╠══════════════════════════════════════════════════════════╣")
    print(f"║  Heartbeat + GetNodeInfo  (Ctrl+C to stop)              ║")
    print(f"╚══════════════════════════════════════════════════════════╝")
    print()

    try:
        while running:
            now = time.monotonic()
            uptime_sec = int(now - start_time)

            # ── Heartbeat ───────────────────────────────────────
            if now - last_heartbeat >= args.interval:
                payload = build_node_status(uptime_sec)
                tail = build_tail_byte(True, True, False, heartbeat_tid)
                can_data = payload + struct.pack('B', tail)

                pkt = build_cannelloni_packet(seq_no, [(heartbeat_can_id, can_data)])
                sock.sendto(pkt, remote)

                print(f"[{uptime_sec:>6}s] TX heartbeat  tid={heartbeat_tid:>2} "
                      f"| {can_data.hex()}")

                seq_no = (seq_no + 1) & 0xFF
                heartbeat_tid = (heartbeat_tid + 1) & 0x1F
                last_heartbeat = now

            # ── Receive incoming CAN frames from cannelloni ─────
            timeout = max(0.01, args.interval - (time.monotonic() - last_heartbeat))
            readable, _, _ = select.select([sock], [], [], timeout)

            if not readable:
                continue

            try:
                data, addr = sock.recvfrom(4096)
            except OSError:
                continue

            for can_id, frame_data in parse_cannelloni_packet(data):
                parsed = parse_can_id(can_id)

                if not (parsed['is_service'] and
                        parsed['request_not_response'] and
                        parsed['dest_node_id'] == args.node_id):
                    continue

                svc_id = parsed['service_type_id']
                requester = parsed['source_node_id']
                req_prio = parsed['priority']
                req_tid = frame_data[-1] & 0x1F if frame_data else 0

                if svc_id == DRONECAN_GETNODEINFO_DTID:
                    print(f"[{uptime_sec:>6}s] RX GetNodeInfo from node {requester} "
                          f"(tid={req_tid})")

                    resp_payload = build_getnodeinfo_response(
                        uptime_sec, args.node_name)
                    resp_can_id = build_service_can_id(
                        req_prio, DRONECAN_GETNODEINFO_DTID,
                        False, requester, args.node_id)

                    can_frames = build_multi_frame(
                        resp_payload, DRONECAN_GETNODEINFO_SIGNATURE, req_tid)

                    frame_tuples = [(resp_can_id, fd) for fd in can_frames]
                    resp_pkt = build_cannelloni_packet(seq_no, frame_tuples)
                    sock.sendto(resp_pkt, addr)

                    seq_no = (seq_no + 1) & 0xFF
                    print(f"[{uptime_sec:>6}s] TX GetNodeInfo → node {requester} "
                          f"({len(can_frames)} frames, \"{args.node_name}\")")
                else:
                    print(f"[{uptime_sec:>6}s] RX service {svc_id} from node {requester}")

    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("\nStopped.")


if __name__ == '__main__':
    main()
