from typing import Protocol


class ClockProtocol(Protocol):
    def now(self) -> float: ...

    def get_uptime(self) -> float: ...

    def get_uptime_sec(self) -> int: ...

class BasePublisher:
    """
    Base class for periodic DroneCAN publishers.
    """
    def get_timeout(self, _now: float) -> float:
        """Returns the time remaining in seconds until this publisher needs to run."""
        return float('inf')

    def process(self, _now: float) -> list[tuple[int, bytes]]:
        """Processes the state and returns list of CAN frames to send."""
        return []
