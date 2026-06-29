import logging
import random
from collections.abc import Mapping
from typing import Any, cast, override

from publishers.base import BasePublisher, ClockProtocol
from constants import (
    DRONECAN_ICE_RECIPROCATING_STATUS_DTID,
    DRONECAN_ICE_RECIPROCATING_STATUS_SIGNATURE,
)
from can_utils import build_message_can_id
from dronecan import build_ice_reciprocating_status_payload, build_multi_frame

logger = logging.getLogger(__name__)


class IceReciprocatingPublisher(BasePublisher):
    """
    Broadcasts uavcan.equipment.ice.reciprocating.Status updates using config-driven ranges.
    """

    def __init__(self, node_id: int, clock: ClockProtocol, config: Mapping[str, Any], priority: int = 4) -> None:
        self.node_id: int = node_id
        self.clock: ClockProtocol = clock
        self.priority: int = priority
        self.config: Mapping[str, Any] = config
        self.interval: float = float(cast(float | int | str, self.config.get('interval', 1.0)))
        self.tid: int = 0
        self.last_send: float = 0.0
        self.can_id: int = build_message_can_id(self.priority, DRONECAN_ICE_RECIPROCATING_STATUS_DTID, self.node_id)
        self._rng: random.Random = random.Random((self.node_id << 8) ^ 0x5A17)

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

    def _sample_status(self) -> dict[str, int | float]:
        return {
            'state': self._sample_int('state', 0, 2),
            'flags': self._sample_int('flags', 0, 0),
            'engine_load_percent': self._sample_int('engine_load_percent', 0, 127),
            'engine_speed_rpm': self._sample_int('engine_speed_rpm', 0, 10000),
            'spark_dwell_time_ms': self._sample_float('spark_dwell_time_ms', 0.0, 0.0),
            'atmospheric_pressure_kpa': self._sample_float('atmospheric_pressure_kpa', 0.0, 0.0),
            'intake_manifold_pressure_kpa': self._sample_float('intake_manifold_pressure_kpa', 0.0, 0.0),
            'intake_manifold_temperature': self._sample_float('intake_manifold_temperature', 0.0, 0.0),
            'coolant_temperature': self._sample_float('coolant_temperature', 0.0, 0.0),
            'oil_pressure': self._sample_float('oil_pressure', 0.0, 0.0),
            'oil_temperature': self._sample_float('oil_temperature', 0.0, 0.0),
            'fuel_pressure': self._sample_float('fuel_pressure', 0.0, 0.0),
            'fuel_consumption_rate_cm3pm': self._sample_float('fuel_consumption_rate_cm3pm', 0.0, 0.0),
            'estimated_consumed_fuel_volume_cm3': self._sample_float('estimated_consumed_fuel_volume_cm3', 0.0, 0.0),
            'throttle_position_percent': self._sample_int('throttle_position_percent', 0, 100),
            'ecu_index': self._sample_int('ecu_index', 0, 0),
            'spark_plug_usage': self._sample_int('spark_plug_usage', 0, 3),
        }

    def _sample_cylinder_status(self) -> list[dict[str, float]]:
        cylinders_value: Any = self.config.get('cylinder_status')
        if not isinstance(cylinders_value, list):
            return []

        sampled_cylinders: list[dict[str, float]] = []
        for cylinder_config in cast(list[Any], cylinders_value):
            if not isinstance(cylinder_config, Mapping):
                continue
            cylinder_map = cast(Mapping[str, Any], cylinder_config)

            def sample(field: str, default_min: float, default_max: float) -> float:
                value: Any = cylinder_map.get(field)
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

            sampled_cylinders.append({
                'ignition_timing_deg': sample('ignition_timing_deg', 0.0, 40.0),
                'injection_time_ms': sample('injection_time_ms', 0.0, 8.0),
                'cylinder_head_temperature': sample('cylinder_head_temperature', 320.0, 420.0),
                'exhaust_gas_temperature': sample('exhaust_gas_temperature', 0.0, 1200.0),
                'lambda_coefficient': sample('lambda_coefficient', 0.8, 1.2),
            })

        return sampled_cylinders

    @override
    def get_timeout(self, now: float) -> float:
        return max(0.0, self.interval - (now - self.last_send))

    @override
    def process(self, now: float) -> list[tuple[int, bytes]]:
        if now - self.last_send < self.interval:
            return []

        uptime_sec = self.get_uptime_sec()
        sampled = self._sample_status()
        cylinders = self._sample_cylinder_status()

        payload = build_ice_reciprocating_status_payload(
            state=int(sampled['state']),
            flags=int(sampled['flags']),
            engine_load_percent=int(sampled['engine_load_percent']),
            engine_speed_rpm=int(sampled['engine_speed_rpm']),
            spark_dwell_time_ms=float(sampled['spark_dwell_time_ms']),
            atmospheric_pressure_kpa=float(sampled['atmospheric_pressure_kpa']),
            intake_manifold_pressure_kpa=float(sampled['intake_manifold_pressure_kpa']),
            intake_manifold_temperature=float(sampled['intake_manifold_temperature']),
            coolant_temperature=float(sampled['coolant_temperature']),
            oil_pressure=float(sampled['oil_pressure']),
            oil_temperature=float(sampled['oil_temperature']),
            fuel_pressure=float(sampled['fuel_pressure']),
            fuel_consumption_rate_cm3pm=float(sampled['fuel_consumption_rate_cm3pm']),
            estimated_consumed_fuel_volume_cm3=float(sampled['estimated_consumed_fuel_volume_cm3']),
            throttle_position_percent=int(sampled['throttle_position_percent']),
            ecu_index=int(sampled['ecu_index']),
            spark_plug_usage=int(sampled['spark_plug_usage']),
            cylinder_status=cylinders,
        )

        can_frames = build_multi_frame(payload, DRONECAN_ICE_RECIPROCATING_STATUS_SIGNATURE, self.tid)

        logger.debug(
            f"[{uptime_sec:>6}s] TX ICE Status tid={self.tid:>2} | "
            f"state={sampled['state']} load={sampled['engine_load_percent']} rpm={sampled['engine_speed_rpm']} "
            f"cylinders={len(cylinders)}"
        )

        self.tid = (self.tid + 1) & 0x1F
        self.last_send = now
        return [(self.can_id, fd) for fd in can_frames]