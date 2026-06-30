import logging
from collections.abc import Sequence
from typing import cast

from constants import (
    DRONECAN_NODESTATUS_DTID, 
    DRONECAN_GETNODEINFO_DTID,
    DRONECAN_GETNODEINFO_SIGNATURE,
    DRONECAN_ICE_RECIPROCATING_STATUS_DTID,
    DRONECAN_ICE_RECIPROCATING_STATUS_SIGNATURE,
    DRONECAN_ICE_FUEL_TANK_STATUS_DTID,
    DRONECAN_ICE_FUEL_TANK_STATUS_SIGNATURE,
)
from can_utils import ParsedNonServiceCanId, ParsedServiceCanId, build_message_can_id, parse_can_id
from allocation import DynamicNodeAllocator
from reassembler import TransferReassembler
from publishers.base import BasePublisher, ClockProtocol
from publishers.heartbeat import HeartbeatPublisher
from publishers.gnss import GNSSPublisher
from publishers.ice import IceReciprocatingPublisher
from publishers.fuel_tank import IceFuelTankPublisher
from services.base import BaseServiceHandler
from services.node_info import GetNodeInfoHandler

logger = logging.getLogger(__name__)
class DroneCANMockNode:
    """
    Simulates a high-fidelity DroneCAN (UAVCAN v0) node.
    Features are componentized into Publishers and Service Handlers for easy extensibility.
    """
    def __init__(
        self,
        node_id: int,
        node_name: str,
        priority: int,
        heartbeat_interval: float,
        gpx_path: str,
        ice_config: dict[str, object],
        fuel_tank_config: dict[str, object],
        clock: ClockProtocol,
        reassembler_session_timeout: float = 2.0,
    ) -> None:
        self.node_id: int = node_id
        self.node_name: str = node_name
        self.priority: int = priority
        self.heartbeat_interval: float = heartbeat_interval
        self.clock: ClockProtocol = clock
        
        # Kept for backward compatibility with main.py's prints
        self.heartbeat_can_id: int = build_message_can_id(
            self.priority, DRONECAN_NODESTATUS_DTID, self.node_id
        )
            
        self.allocator: DynamicNodeAllocator = DynamicNodeAllocator(self.node_id)
 
        # Register Publishers
        self.publishers: Sequence[BasePublisher] = [
            HeartbeatPublisher(node_id=self.node_id, clock=self.clock, interval=self.heartbeat_interval, priority=self.priority),
            GNSSPublisher(node_id=self.node_id, gpx_path=gpx_path, clock=self.clock, priority=self.priority),
            IceReciprocatingPublisher(node_id=self.node_id, clock=self.clock, priority=self.priority, config=ice_config),
            IceFuelTankPublisher(node_id=self.node_id, clock=self.clock, priority=self.priority, config=fuel_tank_config),
        ]

        # Register Service Handlers by Service Type ID
        self.service_handlers: dict[int, BaseServiceHandler] = {
            DRONECAN_GETNODEINFO_DTID: GetNodeInfoHandler(node_id=self.node_id, node_name=self.node_name)
        }

        # Initialize TransferReassembler with registered signatures for incoming services/messages
        signatures = {
            (True, DRONECAN_GETNODEINFO_DTID): DRONECAN_GETNODEINFO_SIGNATURE,
            (False, DRONECAN_ICE_RECIPROCATING_STATUS_DTID): DRONECAN_ICE_RECIPROCATING_STATUS_SIGNATURE,
            (False, DRONECAN_ICE_FUEL_TANK_STATUS_DTID): DRONECAN_ICE_FUEL_TANK_STATUS_SIGNATURE,
        }
        self.reassembler: TransferReassembler = TransferReassembler(
            signatures,
            session_timeout=reassembler_session_timeout,
        )

    def get_uptime_sec(self) -> int:
        """Returns the node simulation uptime in seconds."""
        return self.clock.get_uptime_sec()

    def process_publishers(self) -> list[tuple[int, bytes]]:
        """
        Processes all registered publishers and returns their CAN frames to send.
        This is the preferred generic approach.
        """
        now = self.clock.now()
        frames: list[tuple[int, bytes]] = []
        for pub in self.publishers:
            try:
                frames.extend(pub.process(now))
            except Exception:
                logger.exception("Publisher %s failed during processing", pub.__class__.__name__)
        return frames

    def get_timeout(self) -> float:
        """Returns the time remaining until the next periodic event is due."""
        now = self.clock.now()
        timeouts = [pub.get_timeout(now) for pub in self.publishers]
        # Ensure we return at least 2ms, but no more than the next scheduled publisher task
        return max(0.002, min(timeouts))

    def handle_frame(self, can_id: int, frame_data: bytes) -> list[tuple[int, bytes]]:
        """
        Handles incoming CAN frames, e.g. service requests (GetNodeInfo) or DNA requests.
        """
        uptime_sec = self.get_uptime_sec()
        parsed = parse_can_id(can_id)

        response_frames: list[tuple[int, bytes]] = []

        if parsed['is_service']:
            service_parsed = cast(ParsedServiceCanId, parsed)
            if not (service_parsed['request_not_response'] and service_parsed['dest_node_id'] == self.node_id):
                return []

            svc_id = service_parsed['service_type_id']
            requester = service_parsed['source_node_id']
            req_prio = service_parsed['priority']
            req_tid = frame_data[-1] & 0x1F if frame_data else 0

            # Reassemble incoming service request
            now = self.clock.now()
            try:
                assembled_payload = self.reassembler.process_frame(service_parsed, frame_data, now)
            except Exception:
                logger.exception("Failed to reassemble incoming service transfer for service ID %s", svc_id)
                return []
            if assembled_payload is None:
                # Part of multi-frame transfer or invalid frame
                return []

            handler = self.service_handlers.get(svc_id)
            if handler:
                try:
                    response_frames = handler.handle_request(service_parsed, assembled_payload, req_tid, req_prio, uptime_sec)
                except Exception:
                    logger.exception("Service handler for service ID %s failed", svc_id)
                    return []
            else:
                logger.info(f"[{uptime_sec:>6}s] RX service {svc_id} from node {requester}")
        else:
            msg_parsed = cast(ParsedNonServiceCanId, parsed)
            try:
                alloc_resp = self.allocator.handle_allocation_request(msg_parsed, frame_data, uptime_sec)
            except Exception:
                logger.exception("DNA allocator failed while processing message")
                return []
            if alloc_resp:
                response_frames.extend(alloc_resp)
                logger.info(f"[{uptime_sec:>6}s] TX DNA Response → {len(alloc_resp)} frames")

        return response_frames

