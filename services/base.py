from can_utils import ParsedServiceCanId

class BaseServiceHandler:
    """
    Base class for handling DroneCAN service requests.
    """
    def handle_request(
        self, 
        _parsed: ParsedServiceCanId,
        _request_payload: bytes,
        _req_tid: int,
        _req_prio: int,
        _uptime_sec: int,
    ) -> list[tuple[int, bytes]]:
        """Handles a specific service request and returns response CAN frames."""
        return []
