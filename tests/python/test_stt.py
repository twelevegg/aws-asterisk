"""Tests for STT module."""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))

from aicc_pipeline.stt.google_stt import GoogleCloudSTT, TranscriptResult


class TestTranscriptResult:
    """Test TranscriptResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = TranscriptResult(text="hello", is_final=True)

        assert result.text == "hello"
        assert result.is_final is True
        assert result.confidence == 0.0
        assert result.language == "ko-KR"

    def test_with_confidence(self):
        """Test with confidence value."""
        result = TranscriptResult(
            text="안녕하세요",
            is_final=True,
            confidence=0.95,
            language="ko-KR"
        )

        assert result.confidence == 0.95


class TestGoogleCloudSTT:
    """Test GoogleCloudSTT class."""

    def test_init_without_credentials(self):
        """Test initialization without credentials."""
        with patch.dict(os.environ, {}, clear=True):
            stt = GoogleCloudSTT(
                credentials_path="/nonexistent/path.json",
                language="ko-KR"
            )
            # Should not crash, just warn
            assert stt.is_available is False

    def test_add_audio(self):
        """Test audio buffer."""
        stt = GoogleCloudSTT(
            credentials_path="/nonexistent/path.json"
        )

        stt.add_audio(b'\x00' * 100)
        stt.add_audio(b'\x00' * 100)

        assert len(stt._buffer) == 2

    def test_clear_buffer(self):
        """Test buffer clearing."""
        stt = GoogleCloudSTT(
            credentials_path="/nonexistent/path.json"
        )

        stt.add_audio(b'\x00' * 100)
        stt.clear()

        assert len(stt._buffer) == 0

    def test_get_transcript_empty_buffer(self):
        """Test transcript with empty buffer."""
        stt = GoogleCloudSTT(
            credentials_path="/nonexistent/path.json"
        )

        result = stt.get_transcript()
        assert result == ""

    @pytest.mark.asyncio
    async def test_transcribe_empty_audio(self):
        """Test async transcribe with empty audio."""
        stt = GoogleCloudSTT(
            credentials_path="/nonexistent/path.json"
        )

        result = await stt.transcribe(b'')

        assert result.text == ""
        assert result.is_final is True


class TestGoogleCloudSTTMocked:
    """Test GoogleCloudSTT with mocked client."""

    @pytest.fixture
    def mock_stt(self):
        """Create STT with mocked client."""
        with patch('aicc_pipeline.stt.google_stt.GOOGLE_STT_AVAILABLE', True):
            stt = GoogleCloudSTT(
                credentials_path="/nonexistent/path.json"
            )
            stt._client = MagicMock()
            stt._recognizer = "projects/test/locations/global/recognizers/_"
            return stt

    def test_max_retries(self, mock_stt):
        """Test retry behavior on failure."""
        mock_stt._client.recognize.side_effect = Exception("API Error")

        result = mock_stt._sync_transcribe(b'\x00' * 1000)

        assert result.text == ""
        assert mock_stt._client.recognize.call_count == 3  # max_retries


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
