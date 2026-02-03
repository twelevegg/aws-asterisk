"""
Google Cloud Speech-to-Text V2 - Batch Mode.

Simple batch transcription: buffer audio, then transcribe all at once.
"""

import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger("aicc.stt")

# Google Cloud STT
speech: Any = None
try:
    speech = importlib.import_module("google.cloud.speech_v2")
    GOOGLE_STT_AVAILABLE = True
except Exception:
    GOOGLE_STT_AVAILABLE = False
    logger.warning("Google Cloud Speech not available")


def _split_phrases(value: str) -> List[str]:
    """Split comma-separated phrase list and strip whitespace."""
    phrases = []
    for raw in value.split(","):
        phrase = raw.strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def _get_phrases_from_env() -> List[str]:
    """Collect STT phrase hints from env or file."""
    phrases: List[str] = []

    env_value = os.getenv("AICC_STT_PHRASES")
    if env_value:
        phrases.extend(_split_phrases(env_value))

    phrases_path = os.getenv("AICC_STT_PHRASES_PATH")
    if phrases_path:
        try:
            with open(phrases_path, "r", encoding="utf-8") as f:
                for line in f:
                    phrase = line.strip()
                    if phrase and not phrase.startswith("#"):
                        phrases.append(phrase)
        except Exception:
            pass

    seen = set()
    unique_phrases = []
    for phrase in phrases:
        if phrase not in seen:
            seen.add(phrase)
            unique_phrases.append(phrase)

    return unique_phrases


def _get_phrase_boost_from_env() -> float:
    """Get phrase boost value from env."""
    try:
        return float(os.getenv("AICC_STT_PHRASE_BOOST", "10.0"))
    except Exception:
        return 10.0


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
        phrases: Optional[List[str]] = None,
        phrase_boost: Optional[float] = None,
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
        self.phrases = _get_phrases_from_env() if phrases is None else phrases
        self.phrase_boost = (
            _get_phrase_boost_from_env() if phrase_boost is None else phrase_boost
        )

        self._client: Optional[Any] = None
        self._recognizer: Optional[str] = None
        self._buffer: List[bytes] = []

        if GOOGLE_STT_AVAILABLE:
            self._init_client()

    def _init_client(self):
        """Initialize Google Cloud STT client."""
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

    def _build_adaptation(self):
        """Build speech adaptation with phrase hints."""
        if not self.phrases:
            return None

        try:
            phrase_entries = [
                speech.PhraseSet.Phrase(value=phrase) for phrase in self.phrases
            ]
            phrase_set = speech.PhraseSet(
                phrases=phrase_entries,
                boost=self.phrase_boost,
            )
            return speech.SpeechAdaptation(phrase_sets=[phrase_set])
        except Exception as e:
            logger.warning(f"Failed to build speech adaptation: {e}")
            return None

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
            audio_data = b"".join(self._buffer)

            config_kwargs = {
                "explicit_decoding_config": speech.ExplicitDecodingConfig(
                    encoding=speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=self.sample_rate,
                    audio_channel_count=1,
                ),
                "language_codes": [self.language],
                "model": "telephony",
            }

            adaptation = self._build_adaptation()
            if adaptation:
                config_kwargs["adaptation"] = adaptation

            try:
                config = speech.RecognitionConfig(**config_kwargs)
            except TypeError:
                config_kwargs.pop("adaptation", None)
                config = speech.RecognitionConfig(**config_kwargs)

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
