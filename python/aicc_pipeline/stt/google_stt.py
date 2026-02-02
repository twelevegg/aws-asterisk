"""
Google Cloud Speech-to-Text V2 - Batch Mode.

Simple batch transcription: buffer audio, then transcribe all at once.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("aicc.stt")

# Google Cloud STT
try:
    from google.cloud import speech_v2 as speech
    GOOGLE_STT_AVAILABLE = True
except ImportError:
    GOOGLE_STT_AVAILABLE = False
    logger.warning("Google Cloud Speech not available")


class GoogleCloudSTT:
    """
    Google Cloud Speech-to-Text V2 for Korean.

    Simple batch mode: buffer audio with add_audio(), then get_transcript().
    """

    def __init__(
        self,
        credentials_path: str,
        language: str = "ko-KR",
        sample_rate: int = 16000,
    ):
        """
        Initialize Google Cloud STT.

        Args:
            credentials_path: Path to GCP credentials JSON
            language: Speech recognition language
            sample_rate: Audio sample rate (16000 for PCM 16kHz)
        """
        self.credentials_path = credentials_path
        self.language = language
        self.sample_rate = sample_rate

        self._client: Optional[speech.SpeechClient] = None
        self._recognizer: Optional[str] = None
        self._buffer: List[bytes] = []

        if GOOGLE_STT_AVAILABLE:
            self._init_client()

    def _init_client(self):
        """Initialize Google Cloud STT client."""
        import os
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path

        creds_path = Path(self.credentials_path)
        if not creds_path.exists():
            logger.warning(f"GCP credentials not found: {self.credentials_path}")
            return

        try:
            with open(creds_path) as f:
                creds = json.load(f)
                project_id = creds.get("project_id", "")

            self._client = speech.SpeechClient()
            self._recognizer = f"projects/{project_id}/locations/global/recognizers/_"
            logger.info(f"Google Cloud STT initialized (project: {project_id})")
        except Exception as e:
            logger.warning(f"Failed to initialize Google Cloud STT: {e}")

    @property
    def is_available(self) -> bool:
        """Check if STT client is available."""
        return self._client is not None

    def add_audio(self, pcm_bytes: bytes):
        """
        Add audio to buffer.

        Args:
            pcm_bytes: 16-bit PCM audio data
        """
        self._buffer.append(pcm_bytes)

    def get_transcript(self) -> str:
        """
        Get transcript from buffered audio (synchronous batch transcription).

        Returns:
            Transcribed text, or empty string on error
        """
        if not self._client or not self._buffer:
            return ""

        try:
            audio_data = b''.join(self._buffer)

            config = speech.RecognitionConfig(
                explicit_decoding_config=speech.ExplicitDecodingConfig(
                    encoding=speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=self.sample_rate,
                    audio_channel_count=1,
                ),
                language_codes=[self.language],
                model="telephony",
            )

            request = speech.RecognizeRequest(
                recognizer=self._recognizer,
                config=config,
                content=audio_data,
            )

            response = self._client.recognize(request=request)

            transcript = ""
            for result in response.results:
                if result.alternatives:
                    transcript += result.alternatives[0].transcript

            return transcript.strip()

        except Exception as e:
            logger.warning(f"STT error: {e}")
            return ""

    def clear(self):
        """Clear audio buffer."""
        self._buffer = []
