import unittest

from can_utils import build_message_can_id, build_service_can_id, parse_can_id
from constants import CAN_EFF_FLAG


class CanIdTests(unittest.TestCase):
    def test_message_id_build_parse_roundtrip(self) -> None:
        can_id = build_message_can_id(priority=4, msg_type_id=1120, src_node_id=42)
        parsed = parse_can_id(can_id)

        self.assertFalse(parsed["is_service"])
        self.assertEqual(parsed["priority"], 4)
        self.assertEqual(parsed["message_type_id"], 1120)
        self.assertEqual(parsed["source_node_id"], 42)

    def test_service_id_build_parse_roundtrip(self) -> None:
        can_id = build_service_can_id(
            priority=3,
            svc_type_id=1,
            is_request=True,
            dst_node_id=10,
            src_node_id=55,
        )
        parsed = parse_can_id(can_id)

        self.assertTrue(parsed["is_service"])
        self.assertEqual(parsed["priority"], 3)
        self.assertEqual(parsed["service_type_id"], 1)
        self.assertTrue(parsed["request_not_response"])
        self.assertEqual(parsed["dest_node_id"], 10)
        self.assertEqual(parsed["source_node_id"], 55)

    def test_anonymous_message_parse(self) -> None:
        priority = 4
        message_type_id = 1
        discriminator = 0x1234
        raw = ((priority & 0x1F) << 24) | ((discriminator & 0x3FFF) << 10) | ((message_type_id & 0x3) << 8)
        can_id = CAN_EFF_FLAG | raw

        parsed = parse_can_id(can_id)

        self.assertFalse(parsed["is_service"])
        self.assertEqual(parsed["source_node_id"], 0)
        self.assertEqual(parsed["priority"], priority)
        self.assertEqual(parsed["message_type_id"], message_type_id)
        self.assertEqual(parsed["discriminator"], discriminator)


if __name__ == "__main__":
    unittest.main()
