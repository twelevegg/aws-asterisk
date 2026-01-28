"""
Async UDP Receiver using DatagramProtocol.

Non-blocking UDP receiver with queue-based processing and backpressure handling.
"""

import asyncio
import logging
from typing import Callable, Optional, Tuple, Set

logger = logging.getLogger("aicc.async_udp")


class UDPProtocol(asyncio.DatagramProtocol):
    """Async UDP protocol that queues received datagrams."""

    def __init__(
        self,
        queue: asyncio.Queue,
        max_queue_size: int = 1000,
        allowed_sources: Optional[Set[str]] = None,
    ):
        self.queue = queue
        self.max_queue_size = max_queue_size
        self.allowed_sources = allowed_sources
        self.dropped_packets = 0
        self.received_packets = 0
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        logger.debug("UDP transport connected")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        self.received_packets += 1

        # Source validation
        if self.allowed_sources and addr[0] not in self.allowed_sources:
            if self.dropped_packets % 100 == 0:
                logger.warning(f"Dropped packet from unauthorized source: {addr[0]}")
            self.dropped_packets += 1
            return

        try:
            self.queue.put_nowait((data, addr))
        except asyncio.QueueFull:
            self.dropped_packets += 1
            if self.dropped_packets % 100 == 0:
                logger.warning(
                    f"Dropped {self.dropped_packets} packets due to backpressure "
                    f"(received: {self.received_packets})"
                )

    def error_received(self, exc):
        logger.error(f"UDP error: {exc}")

    def connection_lost(self, exc):
        if exc:
            logger.error(f"UDP connection lost: {exc}")
        else:
            logger.debug("UDP connection closed")


class AsyncUDPReceiver:
    """
    Non-blocking UDP receiver using DatagramProtocol.

    Features:
    - Async queue-based processing
    - Backpressure handling with packet dropping
    - Source IP whitelisting
    - Concurrent packet handling
    """

    def __init__(
        self,
        port: int,
        speaker: str,
        on_audio: Callable[[bytes, str], None],
        bind_address: str = "127.0.0.1",
        queue_size: int = 1000,
        allowed_sources: Optional[Set[str]] = None,
    ):
        self.port = port
        self.speaker = speaker
        self.on_audio = on_audio
        self.bind_address = bind_address
        self.queue_size = queue_size
        self.allowed_sources = allowed_sources

        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self._protocol: Optional[UDPProtocol] = None
        self._transport = None
        self._running = False
        self._process_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start receiving UDP packets (non-blocking)."""
        if self._running:
            return

        loop = asyncio.get_event_loop()

        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(
                self._queue,
                self.queue_size,
                self.allowed_sources
            ),
            local_addr=(self.bind_address, self.port)
        )

        self._running = True
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info(f"AsyncUDPReceiver listening on {self.bind_address}:{self.port} ({self.speaker})")

    async def _process_loop(self) -> None:
        """Process queued packets without blocking receive."""
        while self._running:
            try:
                data, addr = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                # Process in separate task to avoid blocking queue consumer
                asyncio.create_task(self._handle_packet(data, addr))
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.error(f"Process loop error ({self.speaker}): {e}")

    async def _handle_packet(self, data: bytes, addr: Tuple[str, int]) -> None:
        """Handle a single packet (runs concurrently)."""
        try:
            # Parse RTP header (12 bytes minimum)
            if len(data) < 12:
                return

            # Extract payload (skip RTP header)
            payload = data[12:]

            # Call the audio callback
            # Note: The callback should handle conversion from ulaw to PCM
            self.on_audio(payload, self.speaker)

        except Exception as e:
            logger.warning(f"Packet handling error ({self.speaker}): {e}")

    def stop(self) -> None:
        """Stop the receiver."""
        self._running = False
        if self._transport:
            self._transport.close()
        if self._process_task:
            self._process_task.cancel()
        logger.info(f"AsyncUDPReceiver stopped ({self.speaker})")

    async def wait_closed(self) -> None:
        """Wait for receiver to fully close."""
        if self._process_task:
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

    @property
    def stats(self) -> dict:
        """Get receiver statistics."""
        if self._protocol:
            return {
                "received": self._protocol.received_packets,
                "dropped": self._protocol.dropped_packets,
                "queue_size": self._queue.qsize(),
            }
        return {"received": 0, "dropped": 0, "queue_size": 0}

    def is_healthy(self) -> bool:
        """Check if receiver is healthy."""
        return self._running and self._transport is not None
