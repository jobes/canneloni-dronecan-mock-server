import struct
from typing import cast
from constants import CANNELLONI_VERSION, CANNELLONI_OP_DATA, CANNELLONI_HEADER_SIZE


def build_cannelloni_packet(seq_no: int, frames_list: list[tuple[int, bytes]]) -> bytes:
    """frames_list: list of (can_id, data) tuples"""
    header = struct.pack('!BBBh', CANNELLONI_VERSION, CANNELLONI_OP_DATA,
                         seq_no & 0xFF, len(frames_list))
    body = b''
    for can_id, data in frames_list:
        body += struct.pack('!IB', can_id, len(data)) + data
    return header + body


def parse_cannelloni_packet(packet: bytes) -> list[tuple[int, bytes]]:
    if len(packet) < CANNELLONI_HEADER_SIZE:
        return []
    version_raw, op_code_raw, reserved_raw, count_raw = cast(
        tuple[int, int, int, int],
        struct.unpack('!BBBh', packet[:5]),
    )
    version = int(version_raw)
    op_code = int(op_code_raw)
    _ = int(reserved_raw)
    count = int(count_raw)
    if version != CANNELLONI_VERSION or op_code != CANNELLONI_OP_DATA:
        return []
    frames: list[tuple[int, bytes]] = []
    offset = 5
    for _ in range(count):
        if offset + 5 > len(packet):
            break
        can_id_raw, length_raw = cast(
            tuple[int, int],
            struct.unpack('!IB', packet[offset:offset + 5]),
        )
        can_id = int(can_id_raw)
        length = int(length_raw)
        offset += 5
        if offset + length > len(packet):
            break
        frames.append((can_id, packet[offset:offset + length]))
        offset += length
    return frames
