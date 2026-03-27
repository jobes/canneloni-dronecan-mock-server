import struct
from crc import compute_transfer_crc
from constants import HEALTH_OK, MODE_OPERATIONAL


def build_tail_byte(sot, eot, toggle, tid):
    return (int(sot) << 7) | (int(eot) << 6) | (int(toggle) << 5) | (tid & 0x1F)


def build_node_status(uptime_sec, health=HEALTH_OK, mode=MODE_OPERATIONAL):
    status_byte = ((health & 0x03) << 6) | ((mode & 0x07) << 3)
    return struct.pack('<I', uptime_sec) + struct.pack('B', status_byte) + struct.pack('<H', 0)


def build_getnodeinfo_response(uptime_sec, node_name):
    payload = build_node_status(uptime_sec)              # NodeStatus (7B)
    payload += struct.pack('<BBB', 1, 0, 0)              # SW version
    payload += struct.pack('<I', 0)                       # vcs_commit
    payload += struct.pack('<Q', 0)                       # image_crc
    payload += struct.pack('<BB', 1, 0)                   # HW version
    payload += bytes(16)                                  # unique_id[16]
    payload += struct.pack('B', 0)                        # certificate len=0
    payload += node_name.encode('ascii')                  # name (tail array)
    return payload


def build_multi_frame(payload, data_type_signature, transfer_id):
    crc = compute_transfer_crc(payload, data_type_signature)
    data = struct.pack('<H', crc) + payload
    frames, offset, toggle = [], 0, False
    while offset < len(data):
        chunk = data[offset:offset + 7]
        is_first, is_last = offset == 0, offset + len(chunk) >= len(data)
        tail = build_tail_byte(is_first, is_last, toggle, transfer_id)
        frames.append(chunk + struct.pack('B', tail))
        offset += len(chunk)
        toggle = not toggle
    return frames
