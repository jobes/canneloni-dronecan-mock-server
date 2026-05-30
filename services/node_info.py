import logging
from typing import override
from services.base import BaseServiceHandler
from constants import DRONECAN_GETNODEINFO_DTID, DRONECAN_GETNODEINFO_SIGNATURE
from can_utils import ParsedServiceCanId, build_service_can_id
from dronecan import build_getnodeinfo_response, build_multi_frame

logger = logging.getLogger(__name__)

class GetNodeInfoHandler(BaseServiceHandler):
    """
    Handles uavcan.protocol.GetNodeInfo service requests.
    """
    def __init__(self, node_id: int, node_name: str) -> None:
        self.node_id: int = node_id
        self.node_name: str = node_name

    @override
    def handle_request(
        self, 
        parsed: ParsedServiceCanId,
        request_payload: bytes, 
        req_tid: int, 
        req_prio: int, 
        uptime_sec: int
    ) -> list[tuple[int, bytes]]:
        requester = parsed['source_node_id']
        logger.info(f"[{uptime_sec:>6}s] RX GetNodeInfo from node {requester} (tid={req_tid})")

        resp_payload = build_getnodeinfo_response(uptime_sec, self.node_name)
        resp_can_id = build_service_can_id(
            req_prio, DRONECAN_GETNODEINFO_DTID, False, requester, self.node_id
        )

        can_frames = build_multi_frame(
            resp_payload, DRONECAN_GETNODEINFO_SIGNATURE, req_tid
        )

        logger.info(f"[{uptime_sec:>6}s] TX GetNodeInfo → node {requester} ({len(can_frames)} frames, \"{self.node_name}\")")

        return [(resp_can_id, fd) for fd in can_frames]

