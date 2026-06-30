import os
import tempfile
import unittest

from can_utils import parse_can_id
from publishers.fuel_tank import IceFuelTankPublisher
from publishers.gnss import GNSSPublisher
from publishers.heartbeat import HeartbeatPublisher
from publishers.ice import IceReciprocatingPublisher


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def now(self) -> float:
        return self._now

    def get_uptime(self) -> float:
        return self._now

    def get_uptime_sec(self) -> int:
        return int(self._now)

    def advance(self, delta: float) -> None:
        self._now += delta


def _tail_tid(frame: bytes) -> int:
    return frame[-1] & 0x1F


class PublisherContractTests(unittest.TestCase):
    def test_heartbeat_cadence_and_tid(self) -> None:
        clock = FakeClock()
        publisher = HeartbeatPublisher(node_id=2, clock=clock, interval=1.0, priority=4)

        self.assertEqual(publisher.process(clock.now()), [])

        clock.advance(1.0)
        first = publisher.process(clock.now())
        self.assertEqual(len(first), 1)
        can_id, frame = first[0]
        parsed = parse_can_id(can_id)
        self.assertEqual(parsed["message_type_id"], 341)
        self.assertEqual(_tail_tid(frame), 0)

        clock.advance(0.5)
        self.assertEqual(publisher.process(clock.now()), [])

        clock.advance(0.5)
        second = publisher.process(clock.now())
        self.assertEqual(len(second), 1)
        _, second_frame = second[0]
        self.assertEqual(_tail_tid(second_frame), 1)

    def test_gnss_cadence_and_tid(self) -> None:
        gpx = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">\n'
            '  <trk><name>t</name><trkseg>\n'
            '    <trkpt lat="48.1" lon="17.1"><ele>120.0</ele><time>2026-01-01T00:00:00Z</time></trkpt>\n'
            '    <trkpt lat="48.1001" lon="17.1001"><ele>121.0</ele><time>2026-01-01T00:00:01Z</time></trkpt>\n'
            '  </trkseg></trk>\n'
            '</gpx>\n'
        )
        with tempfile.NamedTemporaryFile("w", suffix=".gpx", delete=False) as tmp:
            tmp.write(gpx)
            gpx_path = tmp.name
        self.addCleanup(lambda: os.path.exists(gpx_path) and os.unlink(gpx_path))

        clock = FakeClock()
        publisher = GNSSPublisher(node_id=2, gpx_path=gpx_path, clock=clock, priority=4)

        # First point is sent immediately.
        first = publisher.process(clock.now())
        self.assertTrue(first)
        can_id, frame = first[0]
        parsed = parse_can_id(can_id)
        self.assertEqual(parsed["message_type_id"], 1063)
        self.assertEqual(_tail_tid(frame), 0)

        clock.advance(0.5)
        self.assertEqual(publisher.process(clock.now()), [])

        clock.advance(0.5)
        second = publisher.process(clock.now())
        self.assertTrue(second)
        _, frame2 = second[0]
        self.assertEqual(_tail_tid(frame2), 1)

    def test_ice_publisher_interval_and_tid(self) -> None:
        clock = FakeClock()
        publisher = IceReciprocatingPublisher(node_id=2, clock=clock, priority=4, config={"interval": 1.0})

        self.assertEqual(publisher.process(clock.now()), [])

        clock.advance(1.0)
        first = publisher.process(clock.now())
        self.assertTrue(first)
        can_id, frame = first[0]
        parsed = parse_can_id(can_id)
        self.assertEqual(parsed["message_type_id"], 1120)
        self.assertEqual(_tail_tid(frame), 0)

        clock.advance(1.0)
        second = publisher.process(clock.now())
        self.assertTrue(second)
        _, frame2 = second[0]
        self.assertEqual(_tail_tid(frame2), 1)

    def test_fuel_tank_publisher_interval_and_tid(self) -> None:
        clock = FakeClock()
        publisher = IceFuelTankPublisher(node_id=2, clock=clock, priority=4, config={"interval": 1.0})

        self.assertEqual(publisher.process(clock.now()), [])

        clock.advance(1.0)
        first = publisher.process(clock.now())
        self.assertTrue(first)
        can_id, frame = first[0]
        parsed = parse_can_id(can_id)
        self.assertEqual(parsed["message_type_id"], 1129)
        self.assertEqual(_tail_tid(frame), 0)

        clock.advance(1.0)
        second = publisher.process(clock.now())
        self.assertTrue(second)
        _, frame2 = second[0]
        self.assertEqual(_tail_tid(frame2), 1)

    def test_fuel_tank_publisher_percentage_calculation(self) -> None:
        from unittest.mock import patch
        clock = FakeClock()
        config = {
            "interval": 1.0,
            "available_fuel_volume_cm3": {
                "min": 10000.0,
                "max": 40000.0,
            }
        }
        publisher = IceFuelTankPublisher(node_id=2, clock=clock, priority=4, config=config)

        clock.advance(1.0)
        with patch("publishers.fuel_tank.build_ice_fuel_tank_status_payload") as mock_build:
            publisher.process(clock.now())
            mock_build.assert_called_once()
            kwargs = mock_build.call_args.kwargs
            available_percent = kwargs.get("available_fuel_volume_percent")
            available_cm3 = kwargs.get("available_fuel_volume_cm3")
            
            expected_percent = max(0, min(100, int(round((available_cm3 / 40000.0) * 100.0))))
            self.assertEqual(available_percent, expected_percent)


if __name__ == "__main__":
    unittest.main()
