"""Audio processing module."""
from .rtp import RTPPacket
from .converter import AudioConverter

# Convenience functions for backward compatibility
def ulaw_to_linear(ulaw_bytes: bytes) -> bytes:
    """Convert u-law to 16-bit PCM."""
    return AudioConverter.ulaw_to_pcm16(ulaw_bytes)

def resample(pcm_data: bytes, src_rate: int, dst_rate: int, state=None):
    """Resample PCM audio."""
    return AudioConverter.resample(pcm_data, src_rate, dst_rate, state)

__all__ = ["RTPPacket", "AudioConverter", "ulaw_to_linear", "resample"]
