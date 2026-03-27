import struct

def crc16_ccitt(data: bytes, init: int = 0xFFFF) -> int:
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def compute_transfer_crc(payload: bytes, data_type_signature: int) -> int:
    sig_bytes = struct.pack('<Q', data_type_signature)
    return crc16_ccitt(sig_bytes + payload)
