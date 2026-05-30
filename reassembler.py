import struct
import logging
from typing import TypedDict, cast
from crc import compute_transfer_crc
from can_utils import ParsedCanId, ParsedNonServiceCanId, ParsedServiceCanId

logger = logging.getLogger(__name__)


class SessionState(TypedDict):
    payload: bytearray
    expected_toggle: bool
    ts: float

class TransferReassembler:
    """
    Reassembles single-frame and multi-frame DroneCAN (UAVCAN v0) transfers.
    Provides generic stateful reassembly and CRC verification.
    """
    def __init__(self, signatures: dict[tuple[bool, int], int]) -> None:
        """
        Args:
            signatures: A dictionary mapping (is_service, type_id) -> DSDL signature (int).
        """
        self.signatures: dict[tuple[bool, int], int] = signatures
        # Key: (source_node_id, dest_node_id, is_service, type_id, transfer_id)
        # Value: {
        #   'payload': bytearray,
        #   'expected_toggle': bool,
        #   'ts': float
        # }
        self.sessions: dict[tuple[int, int, bool, int, int], SessionState] = {}

    def process_frame(
        self, 
        parsed_id: ParsedCanId, 
        frame_data: bytes, 
        now: float
    ) -> bytes | None:
        """
        Processes an incoming CAN frame.
        
        Args:
            parsed_id: Dict containing parsed CAN ID fields (from can_utils.parse_can_id).
            frame_data: Raw CAN frame payload bytes (includes the tail byte).
            now: Current monotonic timestamp in seconds.
            
        Returns:
            The fully assembled payload (without CRC or tail byte) if the transfer is complete,
            or None if the transfer is in progress or invalid.
        """
        if not frame_data:
            return None

        # Extract the tail byte
        tail = frame_data[-1]
        sot = bool(tail & 0x80)
        eot = bool(tail & 0x40)
        toggle = bool(tail & 0x20)
        tid = tail & 0x1F

        # The actual payload content of this frame (excluding the tail byte)
        chunk = frame_data[:-1]

        source_node_id = int(parsed_id['source_node_id'])
        is_service = bool(parsed_id['is_service'])
        
        if is_service:
            service_id = cast(ParsedServiceCanId, parsed_id)
            dest_node_id = int(service_id['dest_node_id'])
            type_id = int(service_id['service_type_id'])
        else:
            message_id = cast(ParsedNonServiceCanId, parsed_id)
            dest_node_id = 0
            type_id = int(message_id['message_type_id'])

        # 1. Single-frame transfer (both SOT and EOT are set)
        if sot and eot:
            if toggle:
                # Single-frame transfers must have toggle = 0
                logger.debug(f"[Reassembler] Single-frame transfer from {source_node_id} had toggle=1. Discarding.")
                return None
            return chunk

        # 2. Multi-frame transfer (requires stateful assembly)
        session_key = (source_node_id, dest_node_id, is_service, type_id, tid)

        # Periodically clean up stale, incomplete sessions to avoid memory leaks
        self._cleanup_stale_sessions(now)

        if sot:
            # Start of transfer: toggle must be 0 (False)
            if toggle:
                logger.warning(f"[Reassembler] SOT frame for transfer {session_key} had toggle=1. Discarding.")
                return None
            
            self.sessions[session_key] = {
                'payload': bytearray(chunk),
                'expected_toggle': True,  # Next frame must have toggle = 1 (True)
                'ts': now
            }
            return None

        # Subsequent frames (Middle or End of transfer)
        session = self.sessions.get(session_key)
        if not session:
            # Received middle/end frame but no SOT seen, discard silently
            return None

        # Validate toggle sequence
        if toggle != session['expected_toggle']:
            logger.warning(
                f"[Reassembler] Toggle bit mismatch in multi-frame transfer {session_key}. Got {toggle}, expected {session['expected_toggle']}. Aborting transfer."
            )
            _ = self.sessions.pop(session_key, None)
            return None

        # Append payload chunk
        session['payload'].extend(chunk)
        session['expected_toggle'] = not session['expected_toggle']
        session['ts'] = now

        if eot:
            # End of transfer! Complete and verify CRC.
            session_data = bytes(session['payload'])
            _ = self.sessions.pop(session_key, None)

            if len(session_data) < 2:
                logger.warning(f"[Reassembler] Assembled multi-frame transfer {session_key} is too short (< 2 bytes).")
                return None

            # Multi-frame transfers prepend a 16-bit little-endian CRC
            received_crc = cast(tuple[int], struct.unpack('<H', session_data[:2]))[0]
            actual_payload = session_data[2:]

            signature = self.signatures.get((is_service, type_id))
            if signature is None:
                # If the signature is not registered, we cannot check the CRC,
                # but we will log a warning and return the payload to avoid breaking custom fields.
                logger.warning(
                    f"[Reassembler] Multi-frame transfer for ID {type_id} has no registered DSDL signature. Skipping CRC validation."
                )
                return actual_payload

            expected_crc = compute_transfer_crc(actual_payload, signature)
            if received_crc != expected_crc:
                logger.warning(
                    f"[Reassembler] CRC mismatch in transfer {session_key}. Got 0x{received_crc:04X}, expected 0x{expected_crc:04X}."
                )
                return None

            return actual_payload

        return None

    def _cleanup_stale_sessions(self, now: float, max_age: float = 2.0) -> None:
        """Removes incomplete sessions older than max_age seconds."""
        stale_keys = [
            key for key, session in self.sessions.items()
            if now - session['ts'] > max_age
        ]
        for key in stale_keys:
            logger.warning(f"[Reassembler] Cleaning up stale incomplete session {key}.")
            _ = self.sessions.pop(key, None)
