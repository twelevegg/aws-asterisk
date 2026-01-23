"""Tests for audio processing module."""

import os
import sys
import struct
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))

from aicc_pipeline.audio import RTPPacket, AudioConverter


class TestRTPPacket:
    """Test RTP packet parsing."""

    def test_parse_valid_packet(self):
        """Test parsing a valid RTP packet."""
        # Create a minimal RTP packet
        # Version: 2, Padding: 0, Extension: 0, CSRC count: 0
        # Marker: 0, Payload type: 0 (PCMU)
        first_byte = 0x80  # Version 2
        second_byte = 0x00  # PT 0
        seq = 1234
        timestamp = 160
        ssrc = 0x12345678
        payload = b'\x00' * 160

        header = struct.pack('!BBHII',
                           first_byte, second_byte,
                           seq, timestamp, ssrc)
        packet_data = header + payload

        rtp = RTPPacket.parse(packet_data)

        assert rtp.version == 2
        assert rtp.payload_type == 0
        assert rtp.sequence_number == 1234
        assert rtp.timestamp == 160
        assert rtp.ssrc == 0x12345678
        assert len(rtp.payload) == 160

    def test_parse_too_small(self):
        """Test parsing a packet that's too small."""
        with pytest.raises(ValueError, match="too small"):
            RTPPacket.parse(b'\x00' * 5)

    def test_parse_with_marker(self):
        """Test parsing packet with marker bit set."""
        first_byte = 0x80
        second_byte = 0x80  # Marker bit set
        header = struct.pack('!BBHII', first_byte, second_byte, 0, 0, 0)
        payload = b'\x00' * 10

        rtp = RTPPacket.parse(header + payload)

        assert rtp.marker is True


class TestAudioConverter:
    """Test audio format conversion."""

    def test_ulaw_to_pcm(self):
        """Test u-law to PCM conversion."""
        # u-law silence is 0xFF
        ulaw_silence = b'\xff' * 160

        pcm = AudioConverter.ulaw_to_pcm16(ulaw_silence)

        # PCM output should be 2x the size (16-bit samples)
        assert len(pcm) == 320

    def test_resample_8k_to_16k(self):
        """Test resampling from 8kHz to 16kHz."""
        # Create simple 8kHz PCM
        pcm_8k = b'\x00\x00' * 160  # 160 samples at 8kHz = 20ms

        pcm_16k = AudioConverter.resample_8k_to_16k(pcm_8k)

        # 16kHz should have 2x samples
        assert len(pcm_16k) == len(pcm_8k) * 2

    def test_full_conversion(self):
        """Test full conversion pipeline."""
        ulaw = b'\xff' * 160  # 160 bytes = 20ms at 8kHz

        pcm_16k = AudioConverter.convert(ulaw)

        # ulaw -> pcm16 (2x) -> 16kHz (2x) = 4x
        assert len(pcm_16k) == 160 * 4


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
