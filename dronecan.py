import struct
from typing import List, Optional

from constants import HEALTH_OK, MODE_OPERATIONAL
from crc import compute_transfer_crc
from bit_packing import BitWriter


def build_tail_byte(sot: bool, eot: bool, toggle: bool, tid: int) -> int:
    """
    Builds the tail byte for a DroneCAN transport frame.
    sot: Start of Transfer
    eot: End of Transfer
    toggle: Toggle bit
    tid: Transfer ID (5-bit)
    """
    return (int(sot) << 7) | (int(eot) << 6) | (int(toggle) << 5) | (tid & 0x1F)


def build_node_status(uptime_sec: int, health: int = HEALTH_OK, mode: int = MODE_OPERATIONAL) -> bytes:
    """
    Builds the payload for a uavcan.protocol.NodeStatus heartbeat message.
    """
    status_byte = ((health & 0x03) << 6) | ((mode & 0x07) << 3)
    return struct.pack('<I', uptime_sec) + struct.pack('B', status_byte) + struct.pack('<H', 0)


def build_getnodeinfo_response(uptime_sec: int, node_name: str) -> bytes:
    """
    Builds the payload for a uavcan.protocol.GetNodeInfo service response.
    """
    payload = build_node_status(uptime_sec)              # NodeStatus (7B)
    payload += struct.pack('<BBB', 1, 0, 0)              # SW version (major, minor, pre-release)
    payload += struct.pack('<I', 0)                       # vcs_commit
    payload += struct.pack('<Q', 0)                       # image_crc
    payload += struct.pack('<BB', 1, 0)                   # HW version (major, minor)
    payload += bytes(16)                                  # unique_id[16]
    payload += struct.pack('B', 0)                        # certificate len=0
    payload += node_name.encode('ascii')                  # name (tail array)
    return payload


def build_multi_frame(payload: bytes, data_type_signature: int, transfer_id: int) -> List[bytes]:
    """
    Packages a payload into a list of CAN transport frames using the multi-frame protocol.
    Includes a 16-bit CRC of the payload and signature prepended to the payload.
    """
    crc = compute_transfer_crc(payload, data_type_signature)
    data = struct.pack('<H', crc) + payload
    
    frames: List[bytes] = []
    offset = 0
    toggle = False
    
    while offset < len(data):
        chunk = data[offset:offset + 7]
        is_first = (offset == 0)
        is_last = (offset + len(chunk) >= len(data))
        
        tail = build_tail_byte(is_first, is_last, toggle, transfer_id)
        frames.append(chunk + struct.pack('B', tail))
        
        offset += len(chunk)
        toggle = not toggle
        
    return frames


def build_fix2_payload(
    timestamp_usec: int,
    gnss_timestamp_usec: int,
    lat: float,
    lon: float,
    ele: float,
    v_n: float,
    v_e: float,
    v_d: float,
    sats_used: int,
    status: int,
    mode: int = 0,
    sub_mode: int = 0,
    covariance: Optional[List[float]] = None,
    pdop: float = 1.5
) -> bytes:
    """
    Serializes a uavcan.equipment.gnss.Fix2 DroneCAN message payload (Data Type ID 1063).
    Utilizes bit-by-bit little-endian serialization for non-byte-aligned fields.
    Adheres strictly to the DroneCAN DSDL specification.
    """
    bw = BitWriter()
    
    # 1. timestamp: uavcan.Timestamp (uint56)
    bw.write_unsigned(timestamp_usec, 56)
    
    # 2. gnss_timestamp: uavcan.Timestamp (uint56)
    bw.write_unsigned(gnss_timestamp_usec, 56)
    
    # 3. gnss_time_standard: uint3 (2 = UTC time standard)
    bw.write_unsigned(2, 3)
    
    # 4. void13: 13 bits reserved padding
    bw.write_unsigned(0, 13)
    
    # 5. num_leap_seconds: uint8 (0 = unknown/not set)
    bw.write_unsigned(0, 8)
    
    # 6. longitude_deg_1e8: int37
    bw.write_signed(int(round(lon * 1e8)), 37)
    
    # 7. latitude_deg_1e8: int37
    bw.write_signed(int(round(lat * 1e8)), 37)
    
    # 8. height_ellipsoid_mm: int27 (height above WGS84 ellipsoid)
    bw.write_signed(int(round(ele * 1000)), 27)
    
    # 9. height_msl_mm: int27 (height above mean sea level)
    bw.write_signed(int(round(ele * 1000)), 27)
    
    # 10. ned_velocity: float32[3] (North, East, Down velocity components)
    bw.write_float32(v_n)
    bw.write_float32(v_e)
    bw.write_float32(v_d)
    
    # 11. sats_used: uint6 (number of tracked satellites)
    bw.write_unsigned(sats_used, 6)
    
    # 12. status: uint2 (3 = 3D Fix)
    bw.write_unsigned(status, 2)

    # 13. mode: uint4 (0 = Single)
    bw.write_unsigned(mode, 4)

    # 14. sub_mode: uint6
    bw.write_unsigned(sub_mode, 6)

    # 15. covariance: float16[<=36]
    cov = covariance or []
    if len(cov) > 36:
        raise ValueError("covariance can contain at most 36 elements")
    bw.write_unsigned(len(cov), 6)
    for c in cov:
        bw.write_float16(c)
        
    # 16. pdop: float16
    bw.write_float16(pdop)

    return bw.get_bytes()
