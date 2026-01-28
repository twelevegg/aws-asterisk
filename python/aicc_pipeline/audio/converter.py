"""
Audio Converter.

Converts telephony audio (u-law/a-law 8kHz) to PCM 16kHz for STT processing.
Python 3.13+ compatible using numpy and scipy (no deprecated audioop).
"""

import numpy as np
from typing import Any, Optional, Tuple

try:
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# u-law to linear conversion table (ITU-T G.711)
ULAW_DECODE_TABLE = np.array([
    -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
    -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
    -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
    -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
    -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
    -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
    -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
    -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
    -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
    -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
    -876, -844, -812, -780, -748, -716, -684, -652,
    -620, -588, -556, -524, -492, -460, -428, -396,
    -372, -356, -340, -324, -308, -292, -276, -260,
    -244, -228, -212, -196, -180, -164, -148, -132,
    -120, -112, -104, -96, -88, -80, -72, -64,
    -56, -48, -40, -32, -24, -16, -8, 0,
    32124, 31100, 30076, 29052, 28028, 27004, 25980, 24956,
    23932, 22908, 21884, 20860, 19836, 18812, 17788, 16764,
    15996, 15484, 14972, 14460, 13948, 13436, 12924, 12412,
    11900, 11388, 10876, 10364, 9852, 9340, 8828, 8316,
    7932, 7676, 7420, 7164, 6908, 6652, 6396, 6140,
    5884, 5628, 5372, 5116, 4860, 4604, 4348, 4092,
    3900, 3772, 3644, 3516, 3388, 3260, 3132, 3004,
    2876, 2748, 2620, 2492, 2364, 2236, 2108, 1980,
    1884, 1820, 1756, 1692, 1628, 1564, 1500, 1436,
    1372, 1308, 1244, 1180, 1116, 1052, 988, 924,
    876, 844, 812, 780, 748, 716, 684, 652,
    620, 588, 556, 524, 492, 460, 428, 396,
    372, 356, 340, 324, 308, 292, 276, 260,
    244, 228, 212, 196, 180, 164, 148, 132,
    120, 112, 104, 96, 88, 80, 72, 64,
    56, 48, 40, 32, 24, 16, 8, 0,
], dtype=np.int16)


# a-law to linear conversion table (ITU-T G.711)
ALAW_DECODE_TABLE = np.array([
    -5504, -5248, -6016, -5760, -4480, -4224, -4992, -4736,
    -7552, -7296, -8064, -7808, -6528, -6272, -7040, -6784,
    -2752, -2624, -3008, -2880, -2240, -2112, -2496, -2368,
    -3776, -3648, -4032, -3904, -3264, -3136, -3520, -3392,
    -22016, -20992, -24064, -23040, -17920, -16896, -19968, -18944,
    -30208, -29184, -32256, -31232, -26112, -25088, -28160, -27136,
    -11008, -10496, -12032, -11520, -8960, -8448, -9984, -9472,
    -15104, -14592, -16128, -15616, -13056, -12544, -14080, -13568,
    -344, -328, -376, -360, -280, -264, -312, -296,
    -472, -456, -504, -488, -408, -392, -440, -424,
    -88, -72, -120, -104, -24, -8, -56, -40,
    -216, -200, -248, -232, -152, -136, -184, -168,
    -1376, -1312, -1504, -1440, -1120, -1056, -1248, -1184,
    -1888, -1824, -2016, -1952, -1632, -1568, -1760, -1696,
    -688, -656, -752, -720, -560, -528, -624, -592,
    -944, -912, -1008, -976, -816, -784, -880, -848,
    5504, 5248, 6016, 5760, 4480, 4224, 4992, 4736,
    7552, 7296, 8064, 7808, 6528, 6272, 7040, 6784,
    2752, 2624, 3008, 2880, 2240, 2112, 2496, 2368,
    3776, 3648, 4032, 3904, 3264, 3136, 3520, 3392,
    22016, 20992, 24064, 23040, 17920, 16896, 19968, 18944,
    30208, 29184, 32256, 31232, 26112, 25088, 28160, 27136,
    11008, 10496, 12032, 11520, 8960, 8448, 9984, 9472,
    15104, 14592, 16128, 15616, 13056, 12544, 14080, 13568,
    344, 328, 376, 360, 280, 264, 312, 296,
    472, 456, 504, 488, 408, 392, 440, 424,
    88, 72, 120, 104, 24, 8, 56, 40,
    216, 200, 248, 232, 152, 136, 184, 168,
    1376, 1312, 1504, 1440, 1120, 1056, 1248, 1184,
    1888, 1824, 2016, 1952, 1632, 1568, 1760, 1696,
    688, 656, 752, 720, 560, 528, 624, 592,
    944, 912, 1008, 976, 816, 784, 880, 848,
], dtype=np.int16)


class AudioConverter:
    """Convert u-law/a-law 8kHz to PCM 16kHz."""

    @staticmethod
    def ulaw_to_pcm16(ulaw_bytes: bytes) -> bytes:
        """
        Convert u-law encoded audio to 16-bit PCM.

        Args:
            ulaw_bytes: u-law encoded audio data

        Returns:
            16-bit PCM audio data (little-endian)
        """
        ulaw_array = np.frombuffer(ulaw_bytes, dtype=np.uint8)
        linear = ULAW_DECODE_TABLE[ulaw_array]
        return linear.tobytes()

    @staticmethod
    def alaw_to_pcm16(alaw_bytes: bytes) -> bytes:
        """
        Convert a-law encoded audio to 16-bit PCM.

        Args:
            alaw_bytes: a-law encoded audio data

        Returns:
            16-bit PCM audio data (little-endian)
        """
        alaw_array = np.frombuffer(alaw_bytes, dtype=np.uint8)
        linear = ALAW_DECODE_TABLE[alaw_array]
        return linear.tobytes()

    @staticmethod
    def resample(
        pcm_data: bytes,
        src_rate: int,
        dst_rate: int,
        state: Any = None
    ) -> Tuple[bytes, Any]:
        """
        Resample PCM audio to a different sample rate.

        Args:
            pcm_data: 16-bit PCM audio data
            src_rate: Source sample rate (e.g., 8000)
            dst_rate: Destination sample rate (e.g., 16000)
            state: Resampler state (unused, kept for API compatibility)

        Returns:
            Tuple of (resampled_data, new_state)
        """
        if src_rate == dst_rate:
            return pcm_data, state

        samples = np.frombuffer(pcm_data, dtype=np.int16)

        if SCIPY_AVAILABLE:
            # High-quality resampling with scipy
            num_samples = int(len(samples) * dst_rate / src_rate)
            resampled = signal.resample(samples, num_samples)
            return resampled.astype(np.int16).tobytes(), state
        else:
            # Fallback: simple linear interpolation
            ratio = dst_rate / src_rate
            new_length = int(len(samples) * ratio)
            x_old = np.arange(len(samples))
            x_new = np.linspace(0, len(samples) - 1, new_length)
            resampled = np.interp(x_new, x_old, samples.astype(np.float32))
            return resampled.astype(np.int16).tobytes(), state

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

    @staticmethod
    def is_scipy_available() -> bool:
        """Check if scipy is available for high-quality resampling."""
        return SCIPY_AVAILABLE
