import asyncio
import unittest
from typing import Any

from app_runtime import CannelloniProtocol, publisher_task
from cannelloni import build_cannelloni_packet, parse_cannelloni_packet


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))


class FakeNodeForProtocol:
    def __init__(self) -> None:
        self.calls: list[tuple[int, bytes]] = []

    def handle_frame(self, can_id: int, frame_data: bytes) -> list[tuple[int, bytes]]:
        self.calls.append((can_id, frame_data))
        return [(0x222, b"\xAA\x55")]


class FakeNodeForPublisher:
    def __init__(self) -> None:
        self._publish_count = 0

    def process_publishers(self) -> list[tuple[int, bytes]]:
        self._publish_count += 1
        return [(0x123, b"\x10\x20")]

    def get_timeout(self) -> float:
        return 0.01


class FakeProtocolForPublisher:
    def __init__(self) -> None:
        self.remotes = [("127.0.0.1", 20000)]
        self.sent: list[tuple[list[tuple[int, bytes]], tuple[str, int]]] = []

    def get_active_remotes(self, _now: float) -> list[tuple[str, int]]:
        return list(self.remotes)

    def send_packet(self, frames: list[tuple[int, bytes]], addr: tuple[str, int]) -> None:
        self.sent.append((frames, addr))


class AppRuntimeSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_receives_and_replies(self) -> None:
        node = FakeNodeForProtocol()
        protocol = CannelloniProtocol(node, peer_timeout=10.0, max_peers=4)
        transport = FakeTransport()
        protocol.connection_made(transport)  # type: ignore[arg-type]

        incoming_frames = [(0x111, b"\x01\x02")]
        packet = build_cannelloni_packet(1, incoming_frames)
        addr = ("127.0.0.1", 20000)

        protocol.datagram_received(packet, addr)

        self.assertEqual(node.calls, incoming_frames)
        self.assertEqual(len(transport.sent), 1)

        sent_packet, sent_addr = transport.sent[0]
        self.assertEqual(sent_addr, addr)
        parsed_out = parse_cannelloni_packet(sent_packet)
        self.assertEqual(parsed_out, [(0x222, b"\xAA\x55")])

    async def test_publisher_task_sends_periodic_frames(self) -> None:
        node = FakeNodeForPublisher()
        protocol = FakeProtocolForPublisher()

        task = asyncio.create_task(publisher_task(node, protocol))  # type: ignore[arg-type]
        try:
            await asyncio.sleep(0.03)
        finally:
            task.cancel()
            await task

        self.assertTrue(protocol.sent)
        frames, addr = protocol.sent[0]
        self.assertEqual(addr, ("127.0.0.1", 20000))
        self.assertEqual(frames, [(0x123, b"\x10\x20")])


if __name__ == "__main__":
    unittest.main()
