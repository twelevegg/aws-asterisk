"""
UDP Receiver for RTP Audio Streams.

Handles async UDP socket operations for receiving RTP packets.
"""

import asyncio
import logging
import socket
from typing import Callable, Optional

from ..audio import RTPPacket, AudioConverter

logger = logging.getLogger("aicc.udp")


class UDPReceiver:
    """
    Async UDP receiver for RTP audio.

    Receives RTP packets on a UDP port and processes them.
    """

    def __init__(
        self,
        port: int,
        speaker: str,
        on_audio: Callable[[bytes, str], None],
        on_first_packet: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize UDP receiver.

        Args:
            port: UDP port to listen on
            speaker: Speaker identifier ("customer" or "agent")
            on_audio: Callback for processed PCM audio (pcm_bytes, speaker)
            on_first_packet: Optional callback for first packet received
        """
        self.port = port
        self.speaker = speaker
        self.on_audio = on_audio
        self.on_first_packet = on_first_packet

        self._socket: Optional[socket.socket] = None
        self._running = False
        self._first_packet_received = False
        self._packet_count = 0
        self._error_count = 0

    @property
    def packet_count(self) -> int:
        """Number of packets received."""
        return self._packet_count

    @property
    def error_count(self) -> int:
        """Number of parse errors."""
        return self._error_count

    def _create_socket(self) -> socket.socket:
        """Create and configure UDP socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self.port))
        sock.setblocking(False)
        return sock

    async def start(self):
        """Start receiving UDP packets."""
        self._socket = self._create_socket()
        self._running = True
        self._first_packet_received = False

        logger.info(f"Listening on UDP:{self.port} ({self.speaker})")

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                data = await loop.sock_recv(self._socket, 2048)

                # First packet callback
                if not self._first_packet_received:
                    self._first_packet_received = True
                    if self.on_first_packet:
                        self.on_first_packet(self.speaker)

                # Parse RTP packet
                try:
                    rtp = RTPPacket.parse(data)
                    self._packet_count += 1
                except ValueError as e:
                    self._error_count += 1
                    if self._error_count <= 5:
                        logger.warning(f"RTP parse error ({self.speaker}): {e}")
                    continue

                # Convert audio: ulaw 8kHz -> PCM 16kHz
                try:
                    pcm_16k = AudioConverter.convert(rtp.payload)
                    self.on_audio(pcm_16k, self.speaker)
                except Exception as e:
                    if self._error_count <= 5:
                        logger.warning(f"Audio convert error ({self.speaker}): {e}")
                    self._error_count += 1

            except BlockingIOError:
                await asyncio.sleep(0.001)
            except Exception as e:
                if self._running:
                    logger.error(f"UDP error ({self.speaker}): {e}")
                    self._error_count += 1
                    await asyncio.sleep(0.01)

    def stop(self):
        """Stop receiving."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def get_stats(self) -> dict:
        """Get receiver statistics."""
        return {
            "speaker": self.speaker,
            "port": self.port,
            "packets": self._packet_count,
            "errors": self._error_count,
        }
