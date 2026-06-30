import logging
import random
from collections.abc import Mapping
from typing import Any, cast, override

from publishers.base import BasePublisher, ClockProtocol
from constants import (
    DRONECAN_ICE_FUEL_TANK_STATUS_DTID,
    DRONECAN_ICE_FUEL_TANK_STATUS_SIGNATURE,
)
from can_utils import build_message_can_id
from dronecan import build_ice_fuel_tank_status_payload, build_multi_frame

logger = logging.getLogger(__name__)


class IceFuelTankPublisher(BasePublisher):
    """
    Broadcasts uavcan.equipment.ice.FuelTankStatus updates using config-driven values.
    """

    def __init__(self, node_id: int, clock: ClockProtocol, config: Mapping[str, Any], priority: int = 4) -> None:
        self.node_id: int = node_id
        self.clock: ClockProtocol = clock
        self.priority: int = priority
        self.config: Mapping[str, Any] = config
        self.interval: float = float(cast(float | int | str, self.config.get('interval', 1.0)))
        self.tid: int = 0
        self.last_send: float = 0.0
        self.can_id: int = build_message_can_id(self.priority, DRONECAN_ICE_FUEL_TANK_STATUS_DTID, self.node_id)
        self._rng: random.Random = random.Random((self.node_id << 8) ^ 0x63F1)

    def get_uptime_sec(self) -> int:
        return self.clock.get_uptime_sec()

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

    def _sample_float(self, field: str, default_min: float, default_max: float) -> float:
        value: Any = self.config.get(field)
        if isinstance(value, Mapping):
            range_value = cast(Mapping[str, Any], value)
            lower = float(cast(float | int | str, range_value.get('min', default_min)))
            upper = float(cast(float | int | str, range_value.get('max', default_max)))
            if lower > upper:
                lower, upper = upper, lower
            return self._rng.uniform(lower, upper)
        if value is None:
            return self._rng.uniform(default_min, default_max)
        return float(cast(float | int | str, value))

    @override
    def get_timeout(self, now: float) -> float:
        return max(0.0, self.interval - (now - self.last_send))

    @override
    def process(self, now: float) -> list[tuple[int, bytes]]:
        if now - self.last_send < self.interval:
            return []

        uptime_sec = self.get_uptime_sec()

        available_cm3 = self._sample_float('available_fuel_volume_cm3', 0.0, 0.0)

        available_cm3_config = self.config.get('available_fuel_volume_cm3')
        if isinstance(available_cm3_config, Mapping):
            max_volume = float(cast(float | int | str, available_cm3_config.get('max', 0.0)))
        elif available_cm3_config is not None:
            max_volume = float(cast(float | int | str, available_cm3_config))
        else:
            max_volume = 0.0

        if max_volume > 0.0:
            available_percent = max(0, min(100, int(round((available_cm3 / max_volume) * 100.0))))
        else:
            available_percent = 0

        consumption_cm3pm = self._sample_float('fuel_consumption_rate_cm3pm', 0.0, 0.0)
        fuel_temperature = self._sample_float('fuel_temperature', float('nan'), float('nan'))
        fuel_tank_id = self._sample_int('fuel_tank_id', 0, 255)

        payload = build_ice_fuel_tank_status_payload(
            available_fuel_volume_percent=available_percent,
            available_fuel_volume_cm3=available_cm3,
            fuel_consumption_rate_cm3pm=consumption_cm3pm,
            fuel_temperature=fuel_temperature,
            fuel_tank_id=fuel_tank_id,
        )

        can_frames = build_multi_frame(payload, DRONECAN_ICE_FUEL_TANK_STATUS_SIGNATURE, self.tid)

        logger.debug(
            f"[{uptime_sec:>6}s] TX FuelTankStatus tid={self.tid:>2} | "
            f"tank={fuel_tank_id} available={available_percent}% "
            f"volume_cm3={available_cm3:.1f} consumption_cm3pm={consumption_cm3pm:.1f}"
        )

        self.tid = (self.tid + 1) & 0x1F
        self.last_send = now
        return [(self.can_id, fd) for fd in can_frames]
