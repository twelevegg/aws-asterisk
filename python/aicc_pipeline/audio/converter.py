"""
Audio Converter.

Converts telephony audio (u-law 8kHz) to PCM 16kHz for STT processing.
"""

import audioop
from typing import Tuple


class AudioConverter:
    """Convert u-law 8kHz to PCM 16kHz."""

    @staticmethod
    def ulaw_to_pcm16(ulaw_bytes: bytes) -> bytes:
        """
        Convert u-law encoded audio to 16-bit PCM.

        Args:
            ulaw_bytes: u-law encoded audio data

        Returns:
            16-bit PCM audio data
        """
        return audioop.ulaw2lin(ulaw_bytes, 2)

    @staticmethod
    def alaw_to_pcm16(alaw_bytes: bytes) -> bytes:
        """
        Convert a-law encoded audio to 16-bit PCM.

        Args:
            alaw_bytes: a-law encoded audio data

        Returns:
            16-bit PCM audio data
        """
        return audioop.alaw2lin(alaw_bytes, 2)

    @staticmethod
    def resample(
        pcm_data: bytes,
        src_rate: int,
        dst_rate: int,
        state: bytes = None
    ) -> Tuple[bytes, bytes]:
        """
        Resample PCM audio to a different sample rate.

        Args:
            pcm_data: 16-bit PCM audio data
            src_rate: Source sample rate (e.g., 8000)
            dst_rate: Destination sample rate (e.g., 16000)
            state: Resampler state for continuous streams

        Returns:
            Tuple of (resampled_data, new_state)
        """
        resampled, new_state = audioop.ratecv(
            pcm_data, 2, 1, src_rate, dst_rate, state
        )
        return resampled, new_state

    @classmethod
    def convert(cls, ulaw_bytes: bytes, src_rate: int = 8000, dst_rate: int = 16000) -> bytes:
        """
        Full conversion: u-law 8kHz to PCM 16kHz.

        Args:
            ulaw_bytes: u-law encoded audio at source rate
            src_rate: Source sample rate (default 8000)
            dst_rate: Destination sample rate (default 16000)

        Returns:
            16-bit PCM audio at destination rate
        """
        pcm_src = cls.ulaw_to_pcm16(ulaw_bytes)
        pcm_dst, _ = cls.resample(pcm_src, src_rate, dst_rate)
        return pcm_dst
