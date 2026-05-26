import struct
import logging
from typing import List, Tuple
from publishers.base import BasePublisher
from constants import (
    DRONECAN_NODESTATUS_DTID,
    DRONECAN_PRIORITY_DEFAULT,
    HEALTH_OK,
    MODE_OPERATIONAL
)
from can_utils import build_message_can_id
from dronecan import build_node_status, build_tail_byte

logger = logging.getLogger(__name__)

class HeartbeatPublisher(BasePublisher):
    """
    Broadcasts uavcan.protocol.NodeStatus heartbeat every 1 second.
    """
    def __init__(self, node_id: int, clock, interval: float = 1.0, priority: int = DRONECAN_PRIORITY_DEFAULT) -> None:
        self.node_id = node_id
        self.clock = clock
        self.interval = interval
        self.priority = priority
        self.tid = 0
        self.last_send = 0.0
        self.can_id = build_message_can_id(self.priority, DRONECAN_NODESTATUS_DTID, self.node_id)

    def get_uptime_sec(self) -> int:
        return self.clock.get_uptime_sec()

    def get_timeout(self, now: float) -> float:
        return max(0.0, self.interval - (now - self.last_send))

    def process(self, now: float) -> List[Tuple[int, bytes]]:
        if now - self.last_send >= self.interval:
            uptime_sec = self.get_uptime_sec()
            payload = build_node_status(uptime_sec, HEALTH_OK, MODE_OPERATIONAL)
            tail = build_tail_byte(sot=True, eot=True, toggle=False, tid=self.tid)
            can_data = payload + struct.pack('B', tail)

            logger.debug(f"[{uptime_sec:>6}s] TX heartbeat  tid={self.tid:>2} "
                         f"| {can_data.hex()}")

            self.tid = (self.tid + 1) & 0x1F
            self.last_send = now
            return [(self.can_id, can_data)]
        return []

