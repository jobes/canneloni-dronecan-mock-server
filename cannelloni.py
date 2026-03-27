import struct
from constants import CANNELLONI_VERSION, CANNELLONI_OP_DATA, CANNELLONI_HEADER_SIZE


def build_cannelloni_packet(seq_no, frames_list):
    """frames_list: list of (can_id, data) tuples"""
    header = struct.pack('!BBBh', CANNELLONI_VERSION, CANNELLONI_OP_DATA,
                         seq_no & 0xFF, len(frames_list))
    body = b''
    for can_id, data in frames_list:
        body += struct.pack('!IB', can_id, len(data)) + data
    return header + body


def parse_cannelloni_packet(packet):
    if len(packet) < CANNELLONI_HEADER_SIZE:
        return []
    version, op_code, _, count = struct.unpack('!BBBh', packet[:5])
    if version != CANNELLONI_VERSION or op_code != CANNELLONI_OP_DATA:
        return []
    frames, offset = [], 5
    for _ in range(count):
        if offset + 5 > len(packet):
            break
        can_id, length = struct.unpack('!IB', packet[offset:offset + 5])
        offset += 5
        if offset + length > len(packet):
            break
        frames.append((can_id, packet[offset:offset + length]))
        offset += length
    return frames
