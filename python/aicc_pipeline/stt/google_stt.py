"""
Google Cloud Speech-to-Text V2.

Provides async STT using executor to avoid blocking.
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("aicc.stt")

# Google Cloud STT
try:
    from google.cloud import speech_v2 as speech
    from google.api_core.client_options import ClientOptions
    GOOGLE_STT_AVAILABLE = True
except ImportError:
    GOOGLE_STT_AVAILABLE = False


@dataclass
class TranscriptResult:
    """STT transcript result."""
    text: str
    is_final: bool
    confidence: float = 0.0
    language: str = "ko-KR"


class GoogleCloudSTT:
    """
    Google Cloud Speech-to-Text V2 for Korean.

    Uses ThreadPoolExecutor for non-blocking transcription.
    """

    def __init__(
        self,
        credentials_path: str,
        language: str = "ko-KR",
        sample_rate: int = 16000,
        max_retries: int = 3
    ):
        """
        Initialize Google Cloud STT.

        Args:
            credentials_path: Path to GCP credentials JSON
            language: Speech recognition language
            sample_rate: Audio sample rate
            max_retries: Max retries on STT failure
        """
        self.credentials_path = credentials_path
        self.language = language
        self.sample_rate = sample_rate
        self.max_retries = max_retries

        self._client: Optional[speech.SpeechClient] = None
        self._recognizer: Optional[str] = None
        self._buffer: List[bytes] = []
        self._executor = ThreadPoolExecutor(max_workers=2)

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

    def clear(self):
        """Clear audio buffer."""
        self._buffer = []

    def _sync_transcribe(self, audio_data: bytes) -> TranscriptResult:
        """
        Synchronous transcription (runs in executor).

        Args:
            audio_data: Complete audio data to transcribe

        Returns:
            TranscriptResult with transcribed text
        """
        if not self._client:
            return TranscriptResult(text="", is_final=True)

        last_error = None
        for attempt in range(self.max_retries):
            try:
                config = speech.RecognitionConfig(
                    explicit_decoding_config=speech.ExplicitDecodingConfig(
                        encoding=speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                        sample_rate_hertz=self.sample_rate,
                        audio_channel_count=1,
                    ),
                    language_codes=[self.language],
                    model="long",
                )

                request = speech.RecognizeRequest(
                    recognizer=self._recognizer,
                    config=config,
                    content=audio_data,
                )

                response = self._client.recognize(request=request)

                transcript = ""
                confidence = 0.0
                for result in response.results:
                    if result.alternatives:
                        transcript += result.alternatives[0].transcript
                        confidence = max(confidence, result.alternatives[0].confidence or 0.0)

                return TranscriptResult(
                    text=transcript.strip(),
                    is_final=True,
                    confidence=confidence,
                    language=self.language
                )

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    continue

        logger.warning(f"STT failed after {self.max_retries} attempts: {last_error}")
        return TranscriptResult(text="", is_final=True)

    async def transcribe(self, audio_bytes: Optional[bytes] = None) -> TranscriptResult:
        """
        Async transcription using executor (non-blocking).

        Args:
            audio_bytes: Audio data to transcribe. If None, uses buffered audio.

        Returns:
            TranscriptResult with transcribed text
        """
        if audio_bytes is None:
            audio_bytes = b''.join(self._buffer)

        if not audio_bytes:
            return TranscriptResult(text="", is_final=True)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            self._sync_transcribe,
            audio_bytes
        )
        return result

    def get_transcript(self) -> str:
        """
        Synchronous get transcript (for compatibility).

        Note: This blocks. Prefer using async transcribe() method.

        Returns:
            Transcribed text
        """
        audio_data = b''.join(self._buffer)
        if not audio_data:
            return ""
        result = self._sync_transcribe(audio_data)
        return result.text

    def shutdown(self):
        """Shutdown executor."""
        self._executor.shutdown(wait=False)
