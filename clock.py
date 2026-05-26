import time

class SystemClock:
    """
    Standard monotonic system clock for real-time DroneCAN simulation.
    Allows abstracting time to support simulated/fast-forward time in testing.
    """
    def __init__(self) -> None:
        self._start_time: float = time.monotonic()

    def now(self) -> float:
        """Returns the current monotonic time in seconds."""
        return time.monotonic()

    def get_uptime(self) -> float:
        """Returns the float uptime since the clock was initialized."""
        return time.monotonic() - self._start_time

    def get_uptime_sec(self) -> int:
        """Returns the integer uptime in seconds."""
        return int(self.get_uptime())
