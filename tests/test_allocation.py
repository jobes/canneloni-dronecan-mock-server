import unittest

from allocation import DynamicNodeAllocator
from constants import DRONECAN_ALLOCATION_DTID
from dronecan import build_tail_byte


class AllocationTests(unittest.TestCase):
    def _parsed_allocation_message(self) -> dict[str, int | bool]:
        return {
            "is_service": False,
            "priority": 4,
            "message_type_id": DRONECAN_ALLOCATION_DTID,
            "source_node_id": 0,
            "discriminator": 0,
        }

    def test_non_allocation_message_is_ignored(self) -> None:
        allocator = DynamicNodeAllocator(node_id=2)
        parsed = {
            "is_service": False,
            "priority": 4,
            "message_type_id": 1120,
            "source_node_id": 10,
        }
        out = allocator.handle_allocation_request(parsed, b"\x00\x00", uptime_sec=1)
        self.assertEqual(out, [])

    def test_full_uid_gets_allocated(self) -> None:
        allocator = DynamicNodeAllocator(node_id=2)
        parsed = self._parsed_allocation_message()

        uid = bytes.fromhex("00112233445566778899aabbccddeeff")

        req1 = bytes([0x01]) + uid[:8] + bytes([build_tail_byte(True, True, False, 1)])
        out1 = allocator.handle_allocation_request(parsed, req1, uptime_sec=1)
        self.assertTrue(out1)

        req2 = bytes([0x00]) + uid[8:] + bytes([build_tail_byte(True, True, False, 2)])
        out2 = allocator.handle_allocation_request(parsed, req2, uptime_sec=2)
        self.assertTrue(out2)

        self.assertIn(uid, allocator.allocation_table)
        self.assertEqual(allocator.allocation_table[uid], 10)

    def test_unexpected_tid_resets_state(self) -> None:
        allocator = DynamicNodeAllocator(node_id=2)
        parsed = self._parsed_allocation_message()

        uid = bytes.fromhex("00112233445566778899aabbccddeeff")

        req1 = bytes([0x01]) + uid[:8] + bytes([build_tail_byte(True, True, False, 1)])
        _ = allocator.handle_allocation_request(parsed, req1, uptime_sec=1)

        req_bad = bytes([0x00]) + uid[8:] + bytes([build_tail_byte(True, True, False, 9)])
        out = allocator.handle_allocation_request(parsed, req_bad, uptime_sec=2)

        self.assertEqual(out, [])
        self.assertEqual(allocator.allocation_state["uid"], b"")
        self.assertEqual(allocator.allocation_state["last_tid"], -1)
        self.assertEqual(allocator.allocation_state["expected_tid"], -1)

    def test_nonzero_requested_node_id_is_ignored(self) -> None:
        allocator = DynamicNodeAllocator(node_id=2)
        parsed = self._parsed_allocation_message()

        req_node_id = 42
        first_byte = (req_node_id << 1) | 1
        frame = bytes([first_byte]) + b"\xAA\xBB" + bytes([build_tail_byte(True, True, False, 1)])
        out = allocator.handle_allocation_request(parsed, frame, uptime_sec=3)
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
