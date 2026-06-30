import unittest

from cannelloni import build_cannelloni_packet, parse_cannelloni_packet


class CannelloniPacketTests(unittest.TestCase):
    def test_roundtrip_multiple_frames(self) -> None:
        frames = [
            (0x123, b"\x01\x02\x03"),
            (0x1ABCDE, b"\xFF"),
        ]
        pkt = build_cannelloni_packet(17, frames)
        parsed = parse_cannelloni_packet(pkt)
        self.assertEqual(parsed, frames)

    def test_oversized_frame_list_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_cannelloni_packet(0, [(0, b"")] * 65536)

    def test_invalid_header_is_ignored(self) -> None:
        pkt = bytearray(build_cannelloni_packet(1, [(0x42, b"\xAA")]))
        pkt[0] = 99
        self.assertEqual(parse_cannelloni_packet(bytes(pkt)), [])

    def test_truncated_packet_returns_partial(self) -> None:
        pkt = build_cannelloni_packet(2, [(0x100, b"\x01\x02"), (0x200, b"\x03\x04")])
        truncated = pkt[:-2]
        parsed = parse_cannelloni_packet(truncated)
        self.assertEqual(parsed, [(0x100, b"\x01\x02")])


if __name__ == "__main__":
    unittest.main()
