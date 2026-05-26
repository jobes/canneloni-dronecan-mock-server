import struct
import logging
from typing import List, Tuple, Dict, Any
from constants import (
    DRONECAN_ALLOCATION_DTID,
    DRONECAN_ALLOCATION_SIGNATURE,
    DRONECAN_PRIORITY_DEFAULT
)
from can_utils import build_message_can_id
from dronecan import build_tail_byte, build_multi_frame

logger = logging.getLogger(__name__)

class DynamicNodeAllocator:
    def __init__(self, node_id: int) -> None:
        self.node_id: int = node_id
        self.allocation_sessions: Dict[int, Dict[str, Any]] = {}
        self.allocation_table: Dict[bytes, int] = {}
        self.next_node_id: int = 10
        self.allocation_tid: int = 0

    def handle_allocation_request(
        self, 
        parsed: Dict[str, Any], 
        frame_data: bytes, 
        uptime_sec: int
    ) -> List[Tuple[int, bytes]]:
        """
        Processes an incoming DroneCAN Allocation frame.
        Returns a list of CAN frames to be sent as a response, or empty list if no response needed.
        """
        msg_id = parsed['message_type_id']
        if msg_id != DRONECAN_ALLOCATION_DTID or len(frame_data) < 2:
            return []

        requester = parsed['source_node_id']  # Discriminator
        req_tid = frame_data[-1] & 0x1F

        first_byte = frame_data[0]
        req_node_id = first_byte & 0x7F
        first_part = bool(first_byte & 0x80)
        chunk = frame_data[1:-1]

        # Only process actual requests (where requested node_id is 0)
        if req_node_id != 0:
            return []

        if requester not in self.allocation_sessions:
            self.allocation_sessions[requester] = {'uid': b'', 'last_tid': -1, 'expected_tid': -1}

        session = self.allocation_sessions[requester]
        if first_part:
            session['uid'] = chunk
            session['last_tid'] = req_tid
            session['expected_tid'] = (req_tid + 1) & 0x1F
        else:
            if req_tid == session['expected_tid']:
                session['uid'] += chunk
                session['last_tid'] = req_tid
                session['expected_tid'] = (req_tid + 1) & 0x1F
            elif req_tid == session['last_tid']:
                # Duplicate/retransmitted frame, ignore silently
                pass
            else:
                # Unexpected TID, packet loss or collision occurred
                logger.warning(
                    f"[{uptime_sec:>6}s] DNA: Session {requester} received unexpected TID {req_tid} "
                    f"(expected {session['expected_tid']}). Resetting session."
                )
                session['uid'] = b''
                session['last_tid'] = -1
                session['expected_tid'] = -1
                return []

        current_uid = session['uid']

        if len(current_uid) < 16:
            # Request more bytes
            resp_payload = struct.pack('B', 0) + current_uid
        else:
            # Full 16 bytes received, allocate ID
            current_uid = current_uid[:16]
            if current_uid not in self.allocation_table:
                self.allocation_table[current_uid] = self.next_node_id
                self.next_node_id += 1
            
            allocated_id = self.allocation_table[current_uid]
            resp_payload = struct.pack('B', allocated_id) + current_uid
            logger.info(f"[{uptime_sec:>6}s] DNA: Allocated Node ID {allocated_id} "
                        f"for UID {current_uid.hex()}")

        resp_can_id = build_message_can_id(
            DRONECAN_PRIORITY_DEFAULT, 
            DRONECAN_ALLOCATION_DTID, 
            self.node_id
        )

        if len(resp_payload) <= 7:
            tail = build_tail_byte(True, True, False, self.allocation_tid)
            can_frames = [resp_payload + struct.pack('B', tail)]
        else:
            can_frames = build_multi_frame(
                resp_payload, 
                DRONECAN_ALLOCATION_SIGNATURE, 
                self.allocation_tid
            )
        
        self.allocation_tid = (self.allocation_tid + 1) & 0x1F

        return [(resp_can_id, fd) for fd in can_frames]

