from typing import List, Tuple

class BasePublisher:
    """
    Base class for periodic DroneCAN publishers.
    """
    def get_timeout(self, now: float) -> float:
        """Returns the time remaining in seconds until this publisher needs to run."""
        return float('inf')

    def process(self, now: float) -> List[Tuple[int, bytes]]:
        """Processes the state and returns list of CAN frames to send."""
        return []
