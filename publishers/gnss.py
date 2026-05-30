import logging
from typing import override
from publishers.base import BasePublisher, ClockProtocol
from constants import DRONECAN_GNSS_FIX2_DTID, DRONECAN_GNSS_FIX2_SIGNATURE
from can_utils import build_message_can_id
from dronecan import build_fix2_payload, build_multi_frame
from gpx_sim import GPXPoint, GPXSimulator

logger = logging.getLogger(__name__)

class GNSSPublisher(BasePublisher):
    """
    Broadcasts simulated GNSS Fix2 updates driven sequentially by a GPX flight track.
    """
    def __init__(self, node_id: int, gpx_path: str, clock: ClockProtocol, priority: int = 4) -> None:
        self.node_id: int = node_id
        self.priority: int = priority
        self.clock: ClockProtocol = clock
        self.gpx_sim: GPXSimulator = GPXSimulator(gpx_path)
        self.can_id: int = build_message_can_id(self.priority, DRONECAN_GNSS_FIX2_DTID, self.node_id)
        self.tid: int = 0
        self.sim_start_time: float = 0.0
        self.next_point_idx: int = 0
        self.last_send: float = 0.0

    def get_uptime_sec(self) -> int:
        return self.clock.get_uptime_sec()

    @override
    def get_timeout(self, now: float) -> float:
        if self.next_point_idx == 0:
            return 0.0
        elapsed = now - self.sim_start_time
        if self.next_point_idx < len(self.gpx_sim.points):
            pt = self.gpx_sim.points[self.next_point_idx]
            return max(0.0, pt.elapsed_sec - elapsed)
        return float('inf')

    @override
    def process(self, now: float) -> list[tuple[int, bytes]]:
        send_gps = False
        active_pt: GPXPoint | None = None

        if self.next_point_idx == 0:
            # First point of simulation triggers immediately
            active_pt = self.gpx_sim.points[0]
            self.sim_start_time = now
            self.next_point_idx = 1
            send_gps = True
        else:
            elapsed = now - self.sim_start_time
            if self.next_point_idx < len(self.gpx_sim.points):
                pt = self.gpx_sim.points[self.next_point_idx]
                if elapsed >= pt.elapsed_sec:
                    active_pt = pt
                    self.next_point_idx += 1
                    send_gps = True
                    # Wrap around indices if final GPX point was processed
                    if self.next_point_idx >= len(self.gpx_sim.points):
                        self.next_point_idx = 0

        if send_gps and active_pt is not None:
            uptime_sec = self.get_uptime_sec()
            timestamp_usec = int(self.clock.get_uptime() * 1e6)
            gnss_timestamp_usec = int(active_pt.time.timestamp() * 1e6)
            
            payload = build_fix2_payload(
                timestamp_usec=timestamp_usec,
                gnss_timestamp_usec=gnss_timestamp_usec,
                lat=active_pt.lat,
                lon=active_pt.lon,
                ele=active_pt.ele,
                v_n=active_pt.v_n,
                v_e=active_pt.v_e,
                v_d=active_pt.v_d,
                sats_used=60,
                status=3,  # 3D Fix
                mode=3,    # Single
                sub_mode= 58,
                covariance=[9.0, 0.0, 0.0, 9.0, 0.0, 100.0]  # Upper-right 3x3 NED covariance: 3 m horiz, 10 m vert (m^2)
            )

            can_frames = build_multi_frame(payload, DRONECAN_GNSS_FIX2_SIGNATURE, self.tid)
            
            logger.debug(
                f"[{uptime_sec:>6}s] TX GNSS Fix2   tid={self.tid:>2} | "
                + f"Lat={active_pt.lat:.7f} Lon={active_pt.lon:.7f} Alt={active_pt.ele:.1f}m "
                + f"Speed={active_pt.speed:.1f}m/s Hdg={active_pt.bearing:.1f}°"
            )

            self.tid = (self.tid + 1) & 0x1F
            self.last_send = now
            return [(self.can_id, fd) for fd in can_frames]

        return []

