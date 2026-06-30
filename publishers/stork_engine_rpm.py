import logging
import random
from collections.abc import Mapping
from typing import Any, cast, override

from publishers.base import BasePublisher, ClockProtocol
from constants import (
    DRONECAN_STORK_ENGINE_RPM_DTID,
    DRONECAN_STORK_ENGINE_RPM_SIGNATURE,
)
from can_utils import build_message_can_id
from dronecan import build_stork_engine_rpm_payload, build_multi_frame, build_tail_byte

logger = logging.getLogger(__name__)


class StorkEngineRPMPublisher(BasePublisher):
    """
    Broadcasts stork.equipment.ice.EngineRPM updates with smooth transitions.
    """

    def __init__(self, node_id: int, clock: ClockProtocol, config: Mapping[str, Any], priority: int = 4) -> None:
        self.node_id: int = node_id
        self.clock: ClockProtocol = clock
        self.priority: int = priority
        self.config: Mapping[str, Any] = config
        self.interval: float = float(cast(float | int | str, self.config.get('interval', 0.1)))
        self.tid: int = 0
        self.last_send: float = 0.0
        self.can_id: int = build_message_can_id(self.priority, DRONECAN_STORK_ENGINE_RPM_DTID, self.node_id)
        self._rng: random.Random = random.Random((self.node_id << 8) ^ 0x5A17)

        # State for smooth RPM and load transitions
        self.current_rpm: float | None = None
        self.target_rpm: float | None = None
        self.current_load: float | None = None
        self.target_load: float | None = None

    def get_uptime_sec(self) -> int:
        return self.clock.get_uptime_sec()

    def _get_min_max(self, field: str, default_min: float, default_max: float) -> tuple[float, float]:
        value: Any = self.config.get(field)
        if isinstance(value, Mapping):
            range_value = cast(Mapping[str, Any], value)
            lower = float(cast(float | int | str, range_value.get('min', default_min)))
            upper = float(cast(float | int | str, range_value.get('max', default_max)))
            if lower > upper:
                lower, upper = upper, lower
            return lower, upper
        if value is None:
            return default_min, default_max
        val_float = float(cast(float | int | str, value))
        return val_float, val_float

    def _sample_int(self, field: str, default_min: int, default_max: int) -> int:
        value: Any = self.config.get(field)
        if isinstance(value, Mapping):
            range_value = cast(Mapping[str, Any], value)
            lower = int(cast(float | int | str, range_value.get('min', default_min)))
            upper = int(cast(float | int | str, range_value.get('max', default_max)))
            if lower > upper:
                lower, upper = upper, lower
            return self._rng.randint(lower, upper)
        if value is None:
            return self._rng.randint(default_min, default_max)
        return int(cast(float | int | str, value))

    def _update_smooth_values(self) -> None:
        # Get configured ranges
        rpm_min, rpm_max = self._get_min_max('engine_speed_rpm', 700.0, 2400.0)
        load_min, load_max = self._get_min_max('engine_load_percent', 10.0, 75.0)

        # Initialize current values if not set
        if self.current_rpm is None:
            self.current_rpm = self._rng.uniform(rpm_min, rpm_max)
        if self.current_load is None:
            self.current_load = self._rng.uniform(load_min, load_max)

        # Pick new targets if none or if close to existing targets
        if self.target_rpm is None or abs(self.current_rpm - self.target_rpm) < 10.0:
            self.target_rpm = self._rng.uniform(rpm_min, rpm_max)
        if self.target_load is None or abs(self.current_load - self.target_load) < 2.0:
            self.target_load = self._rng.uniform(load_min, load_max)

        # Move smoothly towards target
        # Max step per cycle: e.g. 5 to 15 RPM, 0.5% to 1.5% load
        rpm_step = self._rng.uniform(5.0, 15.0)
        if self.current_rpm < self.target_rpm:
            self.current_rpm = min(self.target_rpm, self.current_rpm + rpm_step)
        else:
            self.current_rpm = max(self.target_rpm, self.current_rpm - rpm_step)

        load_step = self._rng.uniform(0.5, 1.5)
        if self.current_load < self.target_load:
            self.current_load = min(self.target_load, self.current_load + load_step)
        else:
            self.current_load = max(self.target_load, self.current_load - load_step)

    def _sample_status(self) -> dict[str, int]:
        self._update_smooth_values()
        return {
            'state': self._sample_int('state', 0, 2),
            'ecu_index': self._sample_int('ecu_index', 0, 0),
            'engine_load_percent': int(round(cast(float, self.current_load))),
            'engine_speed_rpm': int(round(cast(float, self.current_rpm))),
            'throttle_position_percent': self._sample_int('throttle_position_percent', 8, 70),
        }

    @override
    def get_timeout(self, now: float) -> float:
        return max(0.0, self.interval - (now - self.last_send))

    @override
    def process(self, now: float) -> list[tuple[int, bytes]]:
        if now - self.last_send < self.interval:
            return []

        uptime_sec = self.get_uptime_sec()
        sampled = self._sample_status()

        payload = build_stork_engine_rpm_payload(
            state=sampled['state'],
            ecu_index=sampled['ecu_index'],
            engine_load_percent=sampled['engine_load_percent'],
            engine_speed_rpm=sampled['engine_speed_rpm'],
            throttle_position_percent=sampled['throttle_position_percent'],
        )

        # Since it is to fit in one frame (<=7 bytes of payload), it will produce a single frame.
        if len(payload) <= 7:
            tail = build_tail_byte(True, True, False, self.tid)
            can_frames = [payload + bytes([tail])]
        else:
            can_frames = build_multi_frame(payload, DRONECAN_STORK_ENGINE_RPM_SIGNATURE, self.tid)

        logger.debug(
            f"[{uptime_sec:>6}s] TX Stork EngineRPM tid={self.tid:>2} | "
            f"state={sampled['state']} ecu={sampled['ecu_index']} "
            f"load={sampled['engine_load_percent']}% rpm={sampled['engine_speed_rpm']} "
            f"throttle={sampled['throttle_position_percent']}%"
        )

        self.tid = (self.tid + 1) & 0x1F
        self.last_send = now
        return [(self.can_id, fd) for fd in can_frames]
