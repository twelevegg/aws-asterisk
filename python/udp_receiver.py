#!/usr/bin/env python3
"""
UDP RTP Packet Receiver for Asterisk ExternalMedia

This script receives RTP packets from Asterisk ExternalMedia channel,
parses the RTP header, extracts audio payload, and provides hexdump output.

Usage:
    python3 udp_receiver.py [--port 12345] [--output captured_audio.ulaw]

RTP Header Structure (12 bytes):
    - Byte 0: Version (2 bits), Padding (1), Extension (1), CSRC count (4)
    - Byte 1: Marker (1 bit), Payload Type (7 bits)
    - Bytes 2-3: Sequence Number (16 bits)
    - Bytes 4-7: Timestamp (32 bits)
    - Bytes 8-11: SSRC (32 bits)
"""

import socket
import struct
import argparse
import signal
import sys
from datetime import datetime


class RTPPacket:
    """Parser for RTP packet headers"""

    HEADER_SIZE = 12

    def __init__(self, data: bytes):
        if len(data) < self.HEADER_SIZE:
            raise ValueError(f"Packet too small: {len(data)} bytes (minimum {self.HEADER_SIZE})")

        self.raw_data = data
        self._parse_header()

    def _parse_header(self):
        # First byte: V(2) P(1) X(1) CC(4)
        first_byte = self.raw_data[0]
        self.version = (first_byte >> 6) & 0x03
        self.padding = (first_byte >> 5) & 0x01
        self.extension = (first_byte >> 4) & 0x01
        self.csrc_count = first_byte & 0x0F

        # Second byte: M(1) PT(7)
        second_byte = self.raw_data[1]
        self.marker = (second_byte >> 7) & 0x01
        self.payload_type = second_byte & 0x7F

        # Sequence number (2 bytes)
        self.sequence_number = struct.unpack('!H', self.raw_data[2:4])[0]

        # Timestamp (4 bytes)
        self.timestamp = struct.unpack('!I', self.raw_data[4:8])[0]

        # SSRC (4 bytes)
        self.ssrc = struct.unpack('!I', self.raw_data[8:12])[0]

        # Calculate header size (including CSRC if present)
        self.header_size = self.HEADER_SIZE + (self.csrc_count * 4)

        # Extract payload
        self.payload = self.raw_data[self.header_size:]

    def get_payload_type_name(self) -> str:
        """Return human-readable payload type name"""
        payload_types = {
            0: 'PCMU (G.711 u-law)',
            8: 'PCMA (G.711 A-law)',
            9: 'G.722',
            18: 'G.729',
        }
        return payload_types.get(self.payload_type, f'Unknown ({self.payload_type})')

    def __str__(self) -> str:
        return (
            f"RTP [V:{self.version} PT:{self.payload_type} ({self.get_payload_type_name()}) "
            f"Seq:{self.sequence_number} TS:{self.timestamp} SSRC:{self.ssrc:08X}] "
            f"Payload: {len(self.payload)} bytes"
        )


def hexdump(data: bytes, length: int = 32) -> str:
    """Generate hexdump string for data"""
    hex_str = ' '.join(f'{b:02X}' for b in data[:length])
    if len(data) > length:
        hex_str += ' ...'
    return hex_str


class UDPReceiver:
    """UDP Socket receiver for RTP packets"""

    def __init__(self, host: str, port: int, output_file: str = None):
        self.host = host
        self.port = port
        self.output_file = output_file
        self.sock = None
        self.running = False
        self.packet_count = 0
        self.total_bytes = 0
        self.audio_file = None

    def start(self):
        """Start the UDP receiver"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(1.0)  # 1 second timeout for graceful shutdown

        if self.output_file:
            self.audio_file = open(self.output_file, 'wb')
            print(f"[INFO] Audio will be saved to: {self.output_file}")

        self.running = True
        print("=" * 70)
        print(f"UDP RTP Receiver Started")
        print("=" * 70)
        print(f"Listening on: {self.host}:{self.port}")
        print(f"Output file:  {self.output_file or 'None (display only)'}")
        print("=" * 70)
        print("Waiting for RTP packets...")
        print()

        try:
            self._receive_loop()
        except KeyboardInterrupt:
            print("\n[INFO] Interrupted by user")
        finally:
            self.stop()

    def _receive_loop(self):
        """Main receive loop"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                self._process_packet(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERROR] Receive error: {e}")

    def _process_packet(self, data: bytes, addr: tuple):
        """Process received UDP packet"""
        self.packet_count += 1
        self.total_bytes += len(data)

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]

        try:
            rtp = RTPPacket(data)

            # Print packet info
            print(f"[{timestamp}] Packet #{self.packet_count} from {addr[0]}:{addr[1]}")
            print(f"  {rtp}")
            print(f"  Header Hex: {hexdump(data[:12])}")
            print(f"  Payload Hex: {hexdump(rtp.payload, 20)}")
            print()

            # Save audio payload to file
            if self.audio_file:
                self.audio_file.write(rtp.payload)
                self.audio_file.flush()

        except ValueError as e:
            print(f"[{timestamp}] Invalid packet from {addr}: {e}")
            print(f"  Raw Hex: {hexdump(data)}")
            print()

    def stop(self):
        """Stop the receiver and cleanup"""
        self.running = False

        if self.sock:
            self.sock.close()

        if self.audio_file:
            self.audio_file.close()

        print()
        print("=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Total packets received: {self.packet_count}")
        print(f"Total bytes received:   {self.total_bytes}")
        if self.output_file:
            print(f"Audio saved to:         {self.output_file}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='UDP RTP Packet Receiver for Asterisk ExternalMedia'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=12345,
        help='UDP port to listen on (default: 12345)'
    )
    parser.add_argument(
        '--output', '-o',
        default='captured_audio.ulaw',
        help='Output file for audio payload (default: captured_audio.ulaw)'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Do not save audio to file (display only)'
    )

    args = parser.parse_args()

    output_file = None if args.no_save else args.output

    receiver = UDPReceiver(args.host, args.port, output_file)

    # Setup signal handlers
    def signal_handler(signum, frame):
        print(f"\n[INFO] Received signal {signum}")
        receiver.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    receiver.start()


if __name__ == '__main__':
    main()
