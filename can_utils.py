from constants import CAN_EFF_FLAG, CAN_EFF_MASK

def build_message_can_id(priority, msg_type_id, src_node_id):
    return CAN_EFF_FLAG | ((priority & 0x1F) << 24) | ((msg_type_id & 0xFFFF) << 8) | (src_node_id & 0x7F)

def build_service_can_id(priority, svc_type_id, is_request, dst_node_id, src_node_id):
    return (CAN_EFF_FLAG |
            ((priority & 0x1F) << 24) |
            ((svc_type_id & 0xFF) << 16) |
            (int(is_request) << 15) |
            ((dst_node_id & 0x7F) << 8) |
            (1 << 7) |
            (src_node_id & 0x7F))

def parse_can_id(can_id):
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
