"""Pytest configuration and fixtures."""

import os
import sys
import pytest

# Add python directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))


def pytest_configure(config):
    """Configure pytest."""
    os.environ['AICC_LOG_LEVEL'] = 'WARNING'
    # Register asyncio marker
    config.addinivalue_line("markers", "asyncio: mark test as async")


@pytest.fixture
def sample_audio_silence():
    """Generate silent audio samples."""
    import numpy as np
    return np.zeros(512, dtype=np.int16).tobytes()


@pytest.fixture
def sample_audio_speech():
    """Generate speech-like audio samples."""
    import numpy as np
    return (np.random.randn(512) * 5000).astype(np.int16).tobytes()


@pytest.fixture
def sample_rtp_packet():
    """Generate sample RTP packet."""
    import struct
    header = struct.pack('!BBHII', 0x80, 0x00, 1234, 160, 0x12345678)
    payload = b'\xff' * 160
    return header + payload
