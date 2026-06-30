import unittest

from dronecan import build_multi_frame
from reassembler import TransferReassembler


class ReassemblerTests(unittest.TestCase):
    def test_single_frame_transfer(self) -> None:
        r = TransferReassembler(signatures={(False, 1120): 0xD38AA3EE75537EC6})
        parsed_id = {
            "is_service": False,
            "priority": 4,
            "message_type_id": 1120,
            "source_node_id": 42,
        }
        frame_data = b"\xAA\xBB" + bytes([0b11000011])

        out = r.process_frame(parsed_id, frame_data, now=0.0)
        self.assertEqual(out, b"\xAA\xBB")

    def test_single_frame_with_toggle_bit_is_rejected(self) -> None:
        r = TransferReassembler(signatures={(False, 1120): 0xD38AA3EE75537EC6})
        parsed_id = {
            "is_service": False,
            "priority": 4,
            "message_type_id": 1120,
            "source_node_id": 42,
        }
        frame_data = b"\xAA\xBB" + bytes([0b11100011])

        out = r.process_frame(parsed_id, frame_data, now=0.0)
        self.assertIsNone(out)

    def test_multiframe_reassembles_and_verifies_crc(self) -> None:
        sig = 0xD38AA3EE75537EC6
        payload = b"abcdefghijklmnopqrstuvwxyz"
        frames = build_multi_frame(payload, sig, transfer_id=5)

        r = TransferReassembler(signatures={(False, 1120): sig})
        parsed_id = {
            "is_service": False,
            "priority": 4,
            "message_type_id": 1120,
            "source_node_id": 42,
        }

        assembled = None
        now = 0.0
        for frame in frames:
            now += 0.01
            assembled = r.process_frame(parsed_id, frame, now=now)

        self.assertEqual(assembled, payload)

    def test_multiframe_crc_mismatch_returns_none(self) -> None:
        sig = 0xD38AA3EE75537EC6
        payload = b"payload-for-crc-check"
        frames = build_multi_frame(payload, sig, transfer_id=9)

        corrupted = bytearray(frames[0])
        corrupted[0] ^= 0xFF
        frames[0] = bytes(corrupted)

        r = TransferReassembler(signatures={(False, 1120): sig})
        parsed_id = {
            "is_service": False,
            "priority": 4,
            "message_type_id": 1120,
            "source_node_id": 42,
        }

        assembled = None
        now = 0.0
        for frame in frames:
            now += 0.01
            assembled = r.process_frame(parsed_id, frame, now=now)

        self.assertIsNone(assembled)

    def test_stale_session_is_dropped(self) -> None:
        sig = 0xD38AA3EE75537EC6
        payload = b"0123456789012345"
        frames = build_multi_frame(payload, sig, transfer_id=2)

        r = TransferReassembler(signatures={(False, 1120): sig}, session_timeout=0.05)
        parsed_id = {
            "is_service": False,
            "priority": 4,
            "message_type_id": 1120,
            "source_node_id": 42,
        }

        first = r.process_frame(parsed_id, frames[0], now=0.0)
        self.assertIsNone(first)

        # Session timed out before continuation frame arrives.
        out = r.process_frame(parsed_id, frames[1], now=1.0)
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
