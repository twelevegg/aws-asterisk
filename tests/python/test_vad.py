"""Tests for VAD module."""

import os
import sys
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))

from aicc_pipeline.vad.detector import EnergyVAD, create_vad, BaseVAD


class TestEnergyVAD:
    """Test energy-based VAD."""

    def setup_method(self):
        self.vad = EnergyVAD(threshold=500.0, sample_rate=16000)

    def test_window_size(self):
        """Test window size calculation."""
        # 32ms at 16kHz = 512 samples
        assert self.vad.window_size == 512

    def test_silence_detection(self):
        """Test silence is not detected as speech."""
        silence = np.zeros(512, dtype=np.int16).tobytes()
        assert self.vad.is_speech(silence) is False

    def test_loud_signal_detection(self):
        """Test loud signal is detected as speech."""
        # Create loud signal
        loud = (np.ones(512) * 10000).astype(np.int16).tobytes()
        assert self.vad.is_speech(loud) is True

    def test_confidence_silence(self):
        """Test confidence for silence."""
        silence = np.zeros(512, dtype=np.int16).tobytes()
        confidence = self.vad.get_confidence(silence)
        assert confidence < 0.1

    def test_confidence_loud(self):
        """Test confidence for loud signal."""
        loud = (np.ones(512) * 10000).astype(np.int16).tobytes()
        confidence = self.vad.get_confidence(loud)
        assert confidence > 0.5

    def test_empty_audio(self):
        """Test handling of empty audio."""
        assert self.vad.is_speech(b'') is False
        assert self.vad.get_confidence(b'') == 0.0

    def test_short_audio(self):
        """Test handling of very short audio."""
        short = b'\x00'
        assert self.vad.is_speech(short) is False


class TestCreateVAD:
    """Test VAD factory function."""

    def test_creates_energy_vad_when_pipecat_unavailable(self):
        """Test fallback to EnergyVAD."""
        vad = create_vad(prefer_silero=False)
        assert isinstance(vad, EnergyVAD)

    def test_threshold_scaling(self):
        """Test that threshold is scaled for EnergyVAD."""
        vad = create_vad(threshold=0.5, prefer_silero=False)
        # Energy threshold should be 500 * 0.5 = 250
        assert vad.threshold == 250.0

    def test_returns_base_vad_interface(self):
        """Test that returned VAD implements BaseVAD."""
        vad = create_vad(prefer_silero=False)
        assert isinstance(vad, BaseVAD)
        assert hasattr(vad, 'is_speech')
        assert hasattr(vad, 'get_confidence')
        assert hasattr(vad, 'window_size')


class TestVADEdgeCases:
    """Test VAD edge cases."""

    def test_near_threshold(self):
        """Test signal near threshold."""
        vad = EnergyVAD(threshold=500.0)

        # Create signal just below threshold
        below = (np.ones(512) * 400).astype(np.int16).tobytes()
        assert vad.is_speech(below) is False

        # Create signal just above threshold
        above = (np.ones(512) * 600).astype(np.int16).tobytes()
        assert vad.is_speech(above) is True

    def test_alternating_signal(self):
        """Test alternating positive/negative signal."""
        vad = EnergyVAD(threshold=500.0)

        # Alternating signal has RMS based on amplitude
        samples = np.array([1000, -1000] * 256, dtype=np.int16)
        assert vad.is_speech(samples.tobytes()) is True

    def test_different_sample_rates(self):
        """Test VAD with different sample rates."""
        vad_8k = EnergyVAD(sample_rate=8000)
        vad_16k = EnergyVAD(sample_rate=16000)

        # Window size should differ
        assert vad_8k.window_size < vad_16k.window_size


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
