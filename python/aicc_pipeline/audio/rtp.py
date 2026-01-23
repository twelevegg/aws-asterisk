"""
RTP Packet Parser.

Parses RTP (Real-time Transport Protocol) packets from UDP streams.
"""

import struct
from dataclasses import dataclass


@dataclass
class RTPPacket:
    """Parsed RTP packet."""
    version: int
    padding: bool
    extension: bool
    marker: bool
    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    payload: bytes

    @classmethod
    def parse(cls, data: bytes) -> 'RTPPacket':
        """
        Parse raw bytes into an RTPPacket.

        Args:
            data: Raw UDP packet data (minimum 12 bytes for RTP header)

        Returns:
            Parsed RTPPacket instance

        Raises:
            ValueError: If packet is too small or malformed
        """
        if len(data) < 12:
            raise ValueError(f"Packet too small: {len(data)} bytes (minimum 12)")

        first_byte = data[0]
        second_byte = data[1]

        version = (first_byte >> 6) & 0x03
        if version != 2:
            raise ValueError(f"Invalid RTP version: {version} (expected 2)")

        padding = bool((first_byte >> 5) & 0x01)
        extension = bool((first_byte >> 4) & 0x01)
        csrc_count = first_byte & 0x0F
        marker = bool((second_byte >> 7) & 0x01)
        payload_type = second_byte & 0x7F

        sequence_number = struct.unpack('!H', data[2:4])[0]
        timestamp = struct.unpack('!I', data[4:8])[0]
        ssrc = struct.unpack('!I', data[8:12])[0]

        # Calculate header size including CSRC list
        header_size = 12 + (csrc_count * 4)

        # Handle extension header if present
        if extension and len(data) > header_size + 4:
            ext_length = struct.unpack('!H', data[header_size + 2:header_size + 4])[0]
            header_size += 4 + (ext_length * 4)

        if len(data) < header_size:
            raise ValueError(f"Packet too small for header: {len(data)} < {header_size}")

        payload = data[header_size:]

        # Handle padding if present
        if padding and payload:
            padding_length = payload[-1]
            if padding_length > 0 and padding_length <= len(payload):
                payload = payload[:-padding_length]

        return cls(
            version=version,
            padding=padding,
            extension=extension,
            marker=marker,
            payload_type=payload_type,
            sequence_number=sequence_number,
            timestamp=timestamp,
            ssrc=ssrc,
            payload=payload
        )

    def is_ulaw(self) -> bool:
        """Check if payload is u-law encoded (PT=0)."""
        return self.payload_type == 0

    def is_alaw(self) -> bool:
        """Check if payload is a-law encoded (PT=8)."""
        return self.payload_type == 8
