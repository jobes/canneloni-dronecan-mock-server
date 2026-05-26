from typing import Dict, Any, List, Tuple

class BaseServiceHandler:
    """
    Base class for handling DroneCAN service requests.
    """
    def handle_request(
        self, 
        parsed: Dict[str, Any], 
        request_payload: bytes, 
        req_tid: int, 
        req_prio: int, 
        uptime_sec: int
    ) -> List[Tuple[int, bytes]]:
        """Handles a specific service request and returns response CAN frames."""
        return []
