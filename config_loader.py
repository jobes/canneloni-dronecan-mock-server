import json
import logging
from collections.abc import Mapping
from typing import Any, TypedDict, cast

import yaml

from constants import DRONECAN_NODE_ID, DRONECAN_NODE_NAME, DRONECAN_PRIORITY_DEFAULT

logger = logging.getLogger(__name__)


class ServerConfig(TypedDict):
    local_port: int
    peer_timeout: float
    max_peers: int
    reassembler_session_timeout: float
    node_id: int
    node_name: str
    priority: int
    heartbeat_interval: float
    gpx: str
    ice_reciprocating: dict[str, object]
    ice_fuel_tank: dict[str, object]


DEFAULT_CONFIG: ServerConfig = {
    'local_port': 20001,
    'peer_timeout': 10.0,
    'max_peers': 64,
    'reassembler_session_timeout': 2.0,
    'node_id': DRONECAN_NODE_ID,
    'node_name': DRONECAN_NODE_NAME,
    'priority': DRONECAN_PRIORITY_DEFAULT,
    'heartbeat_interval': 1.0,
    'gpx': 'assets/flight.gpx',
    'ice_reciprocating': {
        'interval': 1.0,
        'state': {'min': 0, 'max': 2},
        'flags': {'min': 0, 'max': 0},
        'engine_load_percent': {'min': 10, 'max': 75},
        'engine_speed_rpm': {'min': 700, 'max': 2400},
        'spark_dwell_time_ms': {'min': 1.5, 'max': 4.5},
        'atmospheric_pressure_kpa': {'min': 98.0, 'max': 102.5},
        'intake_manifold_pressure_kpa': {'min': 25.0, 'max': 90.0},
        'intake_manifold_temperature': {'min': 300.0, 'max': 390.0},
        'coolant_temperature': {'min': 320.0, 'max': 410.0},
        'oil_pressure': {'min': 180.0, 'max': 450.0},
        'oil_temperature': {'min': 320.0, 'max': 410.0},
        'fuel_pressure': {'min': 180.0, 'max': 420.0},
        'fuel_consumption_rate_cm3pm': {'min': 0.0, 'max': 220.0},
        'estimated_consumed_fuel_volume_cm3': {'min': 0.0, 'max': 5000.0},
        'throttle_position_percent': {'min': 8, 'max': 70},
        'ecu_index': {'min': 0, 'max': 0},
        'spark_plug_usage': {'min': 0, 'max': 3},
        'cylinder_status': [
            {
                'ignition_timing_deg': {'min': 6.0, 'max': 20.0},
                'injection_time_ms': {'min': 1.5, 'max': 6.0},
                'cylinder_head_temperature': {'min': 340.0, 'max': 410.0},
                'exhaust_gas_temperature': {'min': 700.0, 'max': 980.0},
                'lambda_coefficient': {'min': 0.85, 'max': 1.10},
            },
            {
                'ignition_timing_deg': {'min': 6.0, 'max': 20.0},
                'injection_time_ms': {'min': 1.5, 'max': 6.0},
                'cylinder_head_temperature': {'min': 340.0, 'max': 410.0},
                'exhaust_gas_temperature': {'min': 700.0, 'max': 980.0},
                'lambda_coefficient': {'min': 0.85, 'max': 1.10},
            },
        ],
    },
    'ice_fuel_tank': {
        'interval': 1.0,
        'available_fuel_volume_cm3': {'min': 1000.0, 'max': 10000.0},
        'fuel_consumption_rate_cm3pm': {'min': 0.0, 'max': 220.0},
        'fuel_temperature': {'min': 278.0, 'max': 325.0},
        'fuel_tank_id': {'min': 0, 'max': 0},
    },
}


def _clone_config_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _clone_config_value(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_clone_config_value(val) for val in value]
    return value


def _merge_config_value(default_value: object, loaded_value: object) -> object:
    if isinstance(default_value, Mapping) and isinstance(loaded_value, Mapping):
        merged = {str(key): _clone_config_value(val) for key, val in default_value.items()}
        for key, val in loaded_value.items():
            norm_key = str(key).replace('-', '_')
            if norm_key in merged:
                merged[norm_key] = _merge_config_value(merged[norm_key], val)
            else:
                merged[norm_key] = _clone_config_value(val)
        return merged
    if isinstance(default_value, bool):
        return bool(loaded_value)
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        return int(loaded_value)
    if isinstance(default_value, float):
        return float(loaded_value)
    if isinstance(default_value, str):
        return str(loaded_value)
    return _clone_config_value(loaded_value)


def _as_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f'{field_name} must be an integer, got bool')
    try:
        return int(cast(int | float | str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be an integer, got {type(value).__name__}') from exc


def _as_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f'{field_name} must be a float, got bool')
    try:
        return float(cast(int | float | str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be a float, got {type(value).__name__}') from exc


def _validate_int_in_range(value: object, field_name: str, minimum: int, maximum: int) -> None:
    parsed = _as_int(value, field_name)
    if parsed < minimum or parsed > maximum:
        raise ValueError(f'{field_name} must be in range [{minimum}, {maximum}], got {parsed}')


def _validate_positive_float(value: object, field_name: str, minimum: float = 0.0) -> None:
    parsed = _as_float(value, field_name)
    if parsed <= minimum:
        raise ValueError(f'{field_name} must be > {minimum}, got {parsed}')


def _validate_min_max_ranges(value: object, path: str) -> None:
    if isinstance(value, Mapping):
        mapping_value = cast(Mapping[str, object], value)
        if 'min' in mapping_value and 'max' in mapping_value:
            minimum = _as_float(mapping_value['min'], f'{path}.min')
            maximum = _as_float(mapping_value['max'], f'{path}.max')
            if minimum > maximum:
                raise ValueError(f'{path}: min cannot be greater than max ({minimum} > {maximum})')

        for key, child in mapping_value.items():
            child_path = f'{path}.{key}' if path else str(key)
            _validate_min_max_ranges(child, child_path)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            _validate_min_max_ranges(child, f'{path}[{idx}]')


def _validate_server_config(config: ServerConfig) -> None:
    _validate_int_in_range(config['local_port'], 'local_port', 1, 65535)
    _validate_positive_float(config['peer_timeout'], 'peer_timeout')
    _validate_int_in_range(config['max_peers'], 'max_peers', 1, 4096)
    _validate_positive_float(config['reassembler_session_timeout'], 'reassembler_session_timeout')

    _validate_int_in_range(config['node_id'], 'node_id', 0, 127)
    node_name = str(config['node_name'])
    if not node_name:
        raise ValueError('node_name must not be empty')
    if len(node_name) > 80:
        raise ValueError(f'node_name must be at most 80 characters, got {len(node_name)}')
    try:
        _ = node_name.encode('ascii')
    except UnicodeEncodeError as exc:
        raise ValueError('node_name must contain ASCII characters only') from exc

    _validate_int_in_range(config['priority'], 'priority', 0, 31)
    _validate_positive_float(config['heartbeat_interval'], 'heartbeat_interval')

    gpx = str(config['gpx']).strip()
    if not gpx:
        raise ValueError('gpx must not be empty')

    ice_cfg = config.get('ice_reciprocating', {})
    if not isinstance(ice_cfg, Mapping):
        raise ValueError('ice_reciprocating must be a mapping')
    if 'interval' in ice_cfg:
        _validate_positive_float(cast(object, ice_cfg['interval']), 'ice_reciprocating.interval')
    _validate_min_max_ranges(cast(object, ice_cfg), 'ice_reciprocating')

    fuel_cfg = config.get('ice_fuel_tank', {})
    if not isinstance(fuel_cfg, Mapping):
        raise ValueError('ice_fuel_tank must be a mapping')
    if 'interval' in fuel_cfg:
        _validate_positive_float(cast(object, fuel_cfg['interval']), 'ice_fuel_tank.interval')
    _validate_min_max_ranges(cast(object, fuel_cfg), 'ice_fuel_tank')


def load_config(config_path: str) -> ServerConfig:
    config = cast(ServerConfig, _clone_config_value(DEFAULT_CONFIG))

    try:
        with open(config_path, 'r') as f:
            if config_path.endswith(('.yaml', '.yml')):
                loaded_raw: object = cast(object, yaml.safe_load(f))
            else:
                loaded_raw = cast(object, json.load(f))

            if isinstance(loaded_raw, Mapping):
                loaded_map = cast(Mapping[str, object], loaded_raw)
                for key, val in loaded_map.items():
                    norm_key = key.replace('-', '_')
                    if norm_key in config:
                        config[norm_key] = _merge_config_value(config[norm_key], val)
                    else:
                        config[norm_key] = _clone_config_value(val)
        logger.info('Loaded configuration from %s', config_path)
    except FileNotFoundError:
        if config_path != 'config.yaml':
            raise
        logger.warning('Warning: Default config.yaml not found. Running with default settings.')

    _validate_server_config(config)
    return cast(ServerConfig, config)
