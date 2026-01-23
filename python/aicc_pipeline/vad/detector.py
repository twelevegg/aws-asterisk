"""
Voice Activity Detection (VAD).

Provides both simple energy-based VAD and Silero VAD (via Pipecat).
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

logger = logging.getLogger("aicc.vad")

# Pipecat/Silero (optional)
try:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams as PipecatVADParams
    PIPECAT_AVAILABLE = True
except ImportError:
    PIPECAT_AVAILABLE = False


class BaseVAD(ABC):
    """Abstract base class for VAD implementations."""

    @abstractmethod
    def is_speech(self, pcm_bytes: bytes) -> bool:
        """
        Check if audio contains speech.

        Args:
            pcm_bytes: 16-bit PCM audio data

        Returns:
            True if speech is detected
        """
        pass

    @abstractmethod
    def get_confidence(self, pcm_bytes: bytes) -> float:
        """
        Get speech confidence score.

        Args:
            pcm_bytes: 16-bit PCM audio data

        Returns:
            Confidence score (0.0 ~ 1.0)
        """
        pass

    @property
    @abstractmethod
    def window_size(self) -> int:
        """Required audio window size in samples."""
        pass


class EnergyVAD(BaseVAD):
    """Simple energy-based VAD (fallback when Pipecat not available)."""

    def __init__(
        self,
        threshold: float = 500.0,
        sample_rate: int = 16000,
        window_ms: float = 32.0
    ):
        """
        Initialize energy-based VAD.

        Args:
            threshold: RMS energy threshold for speech detection
            sample_rate: Audio sample rate
            window_ms: Analysis window size in milliseconds
        """
        self.threshold = threshold
        self.sample_rate = sample_rate
        self._window_size = int(sample_rate * window_ms / 1000)

    @property
    def window_size(self) -> int:
        return self._window_size

    def _compute_rms(self, pcm_bytes: bytes) -> float:
        """Compute RMS energy of audio."""
        if len(pcm_bytes) < 2:
            return 0.0
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))

    def is_speech(self, pcm_bytes: bytes) -> bool:
        return self._compute_rms(pcm_bytes) > self.threshold

    def get_confidence(self, pcm_bytes: bytes) -> float:
        """
        Convert RMS energy to confidence score.

        Uses sigmoid-like mapping to 0-1 range.
        """
        rms = self._compute_rms(pcm_bytes)
        # Map RMS to 0-1 using soft threshold
        confidence = min(1.0, max(0.0, (rms - self.threshold * 0.5) / self.threshold))
        return confidence


class SileroVAD(BaseVAD):
    """Silero VAD via Pipecat (higher accuracy)."""

    def __init__(
        self,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        min_speech_ms: float = 250.0,
        min_silence_ms: float = 400.0
    ):
        """
        Initialize Silero VAD.

        Args:
            threshold: Speech confidence threshold
            sample_rate: Audio sample rate (must be 16000 for Silero)
            min_speech_ms: Minimum speech duration in ms
            min_silence_ms: Minimum silence duration in ms

        Raises:
            ImportError: If Pipecat is not available
        """
        if not PIPECAT_AVAILABLE:
            raise ImportError("Pipecat not available. Install with: pip install pipecat-ai")

        self.threshold = threshold
        self.sample_rate = sample_rate

        vad_params = PipecatVADParams(
            confidence=threshold,
            start_secs=min_speech_ms / 1000,
            stop_secs=min_silence_ms / 1000,
        )
        self._vad = SileroVADAnalyzer(params=vad_params)
        self._vad.set_sample_rate(sample_rate)
        self._window_size = self._vad.num_frames_required()

    @property
    def window_size(self) -> int:
        return self._window_size

    def is_speech(self, pcm_bytes: bytes) -> bool:
        return self.get_confidence(pcm_bytes) >= self.threshold

    def get_confidence(self, pcm_bytes: bytes) -> float:
        return self._vad.voice_confidence(pcm_bytes)


def create_vad(
    threshold: float = 0.5,
    sample_rate: int = 16000,
    min_speech_ms: float = 250.0,
    min_silence_ms: float = 400.0,
    prefer_silero: bool = True
) -> BaseVAD:
    """
    Factory function to create appropriate VAD instance.

    Args:
        threshold: Speech detection threshold
        sample_rate: Audio sample rate
        min_speech_ms: Minimum speech duration
        min_silence_ms: Minimum silence duration
        prefer_silero: Prefer Silero VAD if available

    Returns:
        VAD instance (SileroVAD if available and preferred, else EnergyVAD)
    """
    if prefer_silero and PIPECAT_AVAILABLE:
        try:
            return SileroVAD(
                threshold=threshold,
                sample_rate=sample_rate,
                min_speech_ms=min_speech_ms,
                min_silence_ms=min_silence_ms
            )
        except Exception as e:
            logger.warning(f"Failed to initialize SileroVAD: {e}")
            logger.info("Falling back to EnergyVAD")

    # Energy threshold is different scale than Silero confidence
    energy_threshold = 500.0 * threshold
    return EnergyVAD(threshold=energy_threshold, sample_rate=sample_rate)
