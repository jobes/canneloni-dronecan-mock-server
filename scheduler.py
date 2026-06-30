from node import DroneCANMockNode


class PublisherScheduler:
    """Coordinates periodic publisher execution timing for a node."""

    def __init__(self, node: DroneCANMockNode, idle_sleep: float = 0.1) -> None:
        self.node: DroneCANMockNode = node
        self.idle_sleep: float = max(0.001, float(idle_sleep))

    def collect_frames(self, has_remotes: bool) -> list[tuple[int, bytes]]:
        if not has_remotes:
            return []
        return self.node.process_publishers()

    def next_sleep(self, has_remotes: bool) -> float:
        if not has_remotes:
            return self.idle_sleep
        return self.node.get_timeout()
