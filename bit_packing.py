import struct

class BitWriter:
    """
    A utility class to build a sequence of bits and package them as little-endian bytes.
    Useful for DroneCAN DSDL serialization which uses non-byte-aligned types.
    """
    def __init__(self) -> None:
        self.bit_string: str = ""

    def write_unsigned(self, val: int, bits: int) -> None:
        """Writes an unsigned integer of a specific bit width."""
        val = int(val) & ((1 << bits) - 1)
        if bits <= 8:
            # Packed directly LSB-first
            for i in range(bits):
                self.bit_string += str((val >> i) & 1)
        else:
            # Packed as little-endian bytes, each byte MSB-first.
            # For each byte, we write the bits in decreasing order of their index.
            # If the last byte is partial, we write only the remaining bits, in decreasing order of their index.
            num_bytes = (bits + 7) // 8
            temp_bits = ""
            for k in range(num_bytes):
                low = k * 8
                high = min(bits - 1, k * 8 + 7)
                for i in range(high, low - 1, -1):
                    temp_bits += str((val >> i) & 1)
            self.bit_string += temp_bits

    def write_signed(self, val: int, bits: int) -> None:
        """Writes a two's complement signed integer of a specific bit width."""
        val = int(val)
        if val < 0:
            val = (1 << bits) + val
        self.write_unsigned(val, bits)

    def write_float32(self, val: float) -> None:
        """Writes a standard IEEE 754 32-bit single-precision float."""
        packed = struct.pack('<f', float(val))
        val_u32 = struct.unpack('<I', packed)[0]
        self.write_unsigned(val_u32, 32)

    def write_float16(self, val: float) -> None:
        """Writes an IEEE 754 16-bit half-precision float."""
        packed = struct.pack('<e', float(val))
        val_u16 = struct.unpack('<H', packed)[0]
        self.write_unsigned(val_u16, 16)

    def get_bytes(self) -> bytes:
        """Pads the bit string to a multiple of 8 with zeros and returns the packed bytes."""
        res = bytearray()
        padded = self.bit_string
        while len(padded) % 8 != 0:
            padded += "0"
        for i in range(0, len(padded), 8):
            chunk = padded[i:i+8]
            res.append(int(chunk, 2))
        return bytes(res)
