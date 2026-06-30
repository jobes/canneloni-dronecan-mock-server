from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Callable

from constants import (
    DRONECAN_GETNODEINFO_DTID,
    DRONECAN_GETNODEINFO_SIGNATURE,
    DRONECAN_ICE_FUEL_TANK_STATUS_DTID,
    DRONECAN_ICE_FUEL_TANK_STATUS_SIGNATURE,
    DRONECAN_ICE_RECIPROCATING_STATUS_DTID,
    DRONECAN_ICE_RECIPROCATING_STATUS_SIGNATURE,
)
from node import DroneCANMockNode
from publishers.base import BasePublisher, ClockProtocol
from publishers.fuel_tank import IceFuelTankPublisher
from publishers.gnss import GNSSPublisher
from publishers.heartbeat import HeartbeatPublisher
from publishers.ice import IceReciprocatingPublisher
from reassembler import TransferReassembler
from services.base import BaseServiceHandler
from services.node_info import GetNodeInfoHandler


@dataclass
class NodeConfig:
    node_id: int
    node_name: str
    priority: int
    heartbeat_interval: float
    gpx_path: str
    ice_config: Mapping[str, object]
    fuel_tank_config: Mapping[str, object]
    reassembler_session_timeout: float


PublisherBuilder = Callable[[NodeConfig, ClockProtocol], BasePublisher]
ServiceBuilder = Callable[[NodeConfig], tuple[int, BaseServiceHandler]]


def _build_heartbeat_publisher(config: NodeConfig, clock: ClockProtocol) -> BasePublisher:
    return HeartbeatPublisher(
        node_id=config.node_id,
        clock=clock,
        interval=config.heartbeat_interval,
        priority=config.priority,
    )


def _build_gnss_publisher(config: NodeConfig, clock: ClockProtocol) -> BasePublisher:
    return GNSSPublisher(
        node_id=config.node_id,
        gpx_path=config.gpx_path,
        clock=clock,
        priority=config.priority,
    )


def _build_ice_reciprocating_publisher(config: NodeConfig, clock: ClockProtocol) -> BasePublisher:
    return IceReciprocatingPublisher(
        node_id=config.node_id,
        clock=clock,
        priority=config.priority,
        config=config.ice_config,
    )


def _build_fuel_tank_publisher(config: NodeConfig, clock: ClockProtocol) -> BasePublisher:
    return IceFuelTankPublisher(
        node_id=config.node_id,
        clock=clock,
        priority=config.priority,
        config=config.fuel_tank_config,
    )


def _build_get_node_info_handler(config: NodeConfig) -> tuple[int, BaseServiceHandler]:
    return DRONECAN_GETNODEINFO_DTID, GetNodeInfoHandler(node_id=config.node_id, node_name=config.node_name)


PUBLISHER_REGISTRY: tuple[PublisherBuilder, ...] = (
    _build_heartbeat_publisher,
    _build_gnss_publisher,
    _build_ice_reciprocating_publisher,
    _build_fuel_tank_publisher,
)

SERVICE_REGISTRY: tuple[ServiceBuilder, ...] = (
    _build_get_node_info_handler,
)

REASSEMBLER_SIGNATURE_REGISTRY: dict[tuple[bool, int], int] = {
    (True, DRONECAN_GETNODEINFO_DTID): DRONECAN_GETNODEINFO_SIGNATURE,
    (False, DRONECAN_ICE_RECIPROCATING_STATUS_DTID): DRONECAN_ICE_RECIPROCATING_STATUS_SIGNATURE,
    (False, DRONECAN_ICE_FUEL_TANK_STATUS_DTID): DRONECAN_ICE_FUEL_TANK_STATUS_SIGNATURE,
}


def build_default_publishers(
    node_id: int,
    priority: int,
    heartbeat_interval: float,
    gpx_path: str,
    ice_config: Mapping[str, object],
    fuel_tank_config: Mapping[str, object],
    clock: ClockProtocol,
) -> Sequence[BasePublisher]:
    config = NodeConfig(
        node_id=node_id,
        node_name='',
        priority=priority,
        heartbeat_interval=heartbeat_interval,
        gpx_path=gpx_path,
        ice_config=ice_config,
        fuel_tank_config=fuel_tank_config,
        reassembler_session_timeout=2.0,
    )
    return [builder(config, clock) for builder in PUBLISHER_REGISTRY]


def build_default_service_handlers(node_id: int, node_name: str) -> dict[int, BaseServiceHandler]:
    config = NodeConfig(
        node_id=node_id,
        node_name=node_name,
        priority=0,
        heartbeat_interval=1.0,
        gpx_path='',
        ice_config={},
        fuel_tank_config={},
        reassembler_session_timeout=2.0,
    )
    return {service_id: handler for service_id, handler in (builder(config) for builder in SERVICE_REGISTRY)}


def build_default_reassembler(session_timeout: float) -> TransferReassembler:
    return TransferReassembler(dict(REASSEMBLER_SIGNATURE_REGISTRY), session_timeout=session_timeout)


def build_default_node(config: NodeConfig, clock: ClockProtocol) -> DroneCANMockNode:
    publishers = [builder(config, clock) for builder in PUBLISHER_REGISTRY]
    service_handlers = {service_id: handler for service_id, handler in (builder(config) for builder in SERVICE_REGISTRY)}
    reassembler = build_default_reassembler(session_timeout=config.reassembler_session_timeout)

    return DroneCANMockNode(
        node_id=config.node_id,
        node_name=config.node_name,
        priority=config.priority,
        clock=clock,
        publishers=publishers,
        service_handlers=service_handlers,
        reassembler=reassembler,
    )
