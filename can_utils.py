from constants import CAN_EFF_FLAG, CAN_EFF_MASK
from typing import Literal, TypedDict


class ParsedServiceCanId(TypedDict):
    is_service: Literal[True]
    priority: int
    service_type_id: int
    request_not_response: bool
    dest_node_id: int
    source_node_id: int


class ParsedAnonymousMessageCanId(TypedDict):
    is_service: Literal[False]
    priority: int
    message_type_id: int
    source_node_id: Literal[0]
    discriminator: int


class ParsedMessageCanId(TypedDict):
    is_service: Literal[False]
    priority: int
    message_type_id: int
    source_node_id: int


ParsedCanId = ParsedServiceCanId | ParsedAnonymousMessageCanId | ParsedMessageCanId
ParsedNonServiceCanId = ParsedAnonymousMessageCanId | ParsedMessageCanId


def build_message_can_id(priority: int, msg_type_id: int, src_node_id: int) -> int:
    return CAN_EFF_FLAG | ((priority & 0x1F) << 24) | ((msg_type_id & 0xFFFF) << 8) | (src_node_id & 0x7F)


def build_service_can_id(
    priority: int,
    svc_type_id: int,
    is_request: bool,
    dst_node_id: int,
    src_node_id: int,
) -> int:
    return (CAN_EFF_FLAG |
            ((priority & 0x1F) << 24) |
            ((svc_type_id & 0xFF) << 16) |
            (int(is_request) << 15) |
            ((dst_node_id & 0x7F) << 8) |
            (1 << 7) |
            (src_node_id & 0x7F))


def parse_can_id(can_id: int) -> ParsedCanId:
    raw = can_id & CAN_EFF_MASK
    is_service = bool(raw & (1 << 7))
    source_node_id = raw & 0x7F
    if is_service:
        return {
            'is_service': True,
            'priority': (raw >> 24) & 0x1F,
            'service_type_id': (raw >> 16) & 0xFF,
            'request_not_response': bool(raw & (1 << 15)),
            'dest_node_id': (raw >> 8) & 0x7F,
            'source_node_id': source_node_id,
        }
    
    if source_node_id == 0:
        return {
            'is_service': False,
            'priority': (raw >> 24) & 0x1F,
            'message_type_id': (raw >> 8) & 3,
            'source_node_id': 0,
            'discriminator': (raw >> 10) & 0x3FFF,
        }
    
    return {
        'is_service': False,
        'priority': (raw >> 24) & 0x1F,
        'message_type_id': (raw >> 8) & 0xFFFF,
        'source_node_id': source_node_id,
    }
