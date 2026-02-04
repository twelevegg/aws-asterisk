"""
Pipeline configuration with environment variable support.

Environment Variables:
    AICC_WS_URL - Main WebSocket URL
    AICC_WS_URL_1, AICC_WS_URL_2... - Additional URLs
    AICC_CUSTOMER_PORT - Customer UDP port (default: 12345)
    AICC_AGENT_PORT - Agent UDP port (default: 12346)
    AICC_DEBUG - Enable debug logging (true/false)
    GOOGLE_APPLICATION_CREDENTIALS - GCP credentials path
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


def _get_gcp_project_id() -> str:
    """Extract project_id from GCP credentials JSON."""
    import json

    creds_path = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(Path.home() / ".config/gcloud/credentials.json"),
    )
    try:
        with open(creds_path) as f:
            creds = json.load(f)
            return creds.get("project_id", "")
    except Exception:
        return ""


def _get_ws_urls_from_env() -> List[str]:
    """Collect WebSocket URLs from environment variables."""
    urls = []

    # Main URL
    main_url = os.getenv("AICC_WS_URL")
    if main_url:
        urls.append(main_url)

    # Additional URLs (AICC_WS_URL_1, AICC_WS_URL_2, ...)
    i = 1
    while True:
        url = os.getenv(f"AICC_WS_URL_{i}")
        if not url:
            break
        urls.append(url)
        i += 1

    return urls


def _split_phrases(value: str) -> List[str]:
    """Split comma-separated phrase list and strip whitespace."""
    phrases = []
    for raw in value.split(","):
        phrase = raw.strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def _get_stt_phrases_from_env() -> List[str]:
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


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    # UDP ports
    customer_port: int = field(
        default_factory=lambda: int(os.getenv("AICC_CUSTOMER_PORT", "12345"))
    )
    agent_port: int = field(
        default_factory=lambda: int(os.getenv("AICC_AGENT_PORT", "12346"))
    )

    # Dynamic call info (set per-call, not from env)
    call_id: Optional[str] = None
    agent_id: Optional[str] = None
    customer_number: Optional[str] = None

    # Audio settings
    sample_rate: int = 8000  # ulaw is 8kHz
    target_sample_rate: int = 16000  # For STT

    # VAD settings
    vad_threshold: float = field(
        default_factory=lambda: float(os.getenv("AICC_VAD_THRESHOLD", "0.45"))
    )
    min_speech_ms: float = field(
        default_factory=lambda: float(os.getenv("AICC_MIN_SPEECH_MS", "300.0"))
    )
    min_silence_ms: float = field(
        default_factory=lambda: float(os.getenv("AICC_MIN_SILENCE_MS", "800.0"))
    )

    # WebSocket settings
    ws_urls: List[str] = field(default_factory=_get_ws_urls_from_env)
    ws_reconnect_interval: float = field(
        default_factory=lambda: float(os.getenv("AICC_WS_RECONNECT_INTERVAL", "5.0"))
    )
    ws_queue_maxsize: int = field(
        default_factory=lambda: int(os.getenv("AICC_WS_QUEUE_MAXSIZE", "1000"))
    )

    # STT settings
    stt_language: str = field(
        default_factory=lambda: os.getenv("AICC_STT_LANGUAGE", "ko-KR")
    )
    stt_phrases: List[str] = field(default_factory=_get_stt_phrases_from_env)
    stt_phrase_boost: float = field(
        default_factory=lambda: float(os.getenv("AICC_STT_PHRASE_BOOST", "10.0"))
    )
    gcp_credentials_path: str = field(
        default_factory=lambda: os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS",
            str(Path.home() / ".config/gcloud/credentials.json"),
        )
    )
    gcp_project_id: str = field(default_factory=_get_gcp_project_id)

    # Turn detection weights (for fusion scoring)
    turn_morpheme_weight: float = field(
        default_factory=lambda: float(os.getenv("AICC_TURN_MORPHEME_WEIGHT", "0.6"))
    )
    turn_duration_weight: float = field(
        default_factory=lambda: float(os.getenv("AICC_TURN_DURATION_WEIGHT", "0.2"))
    )
    turn_silence_weight: float = field(
        default_factory=lambda: float(os.getenv("AICC_TURN_SILENCE_WEIGHT", "0.2"))
    )
    turn_complete_threshold: float = field(
        default_factory=lambda: float(os.getenv("AICC_TURN_COMPLETE_THRESHOLD", "0.65"))
    )

    # Continuous streaming settings
    stt_session_rotation_sec: float = field(
        default_factory=lambda: float(os.getenv("AICC_STT_ROTATION_SEC", "270"))
    )
    turn_boundary_min_silence_ms: float = field(
        default_factory=lambda: float(os.getenv("AICC_TURN_MIN_SILENCE_MS", "800"))
    )
    turn_boundary_min_chars: int = field(
        default_factory=lambda: int(os.getenv("AICC_TURN_MIN_CHARS", "1"))
    )

    # STT audio queue settings
    stt_audio_queue_maxsize: int = field(
        default_factory=lambda: int(os.getenv("AICC_STT_AUDIO_QUEUE_MAXSIZE", "300"))
    )

    # Debug
    debug: bool = field(
        default_factory=lambda: os.getenv("AICC_DEBUG", "false").lower() == "true"
    )

    def __post_init__(self):
        """Validate and set defaults after initialization."""
        import logging

        logger = logging.getLogger("aicc.config")

        # Ensure at least one WebSocket URL
        if not self.ws_urls:
            default_url = os.getenv("AICC_WS_URL")
            if default_url:
                self.ws_urls = [default_url]
            else:
                logger.warning(
                    "No WebSocket URL configured. Set AICC_WS_URL environment variable."
                )

    @property
    def primary_ws_url(self) -> Optional[str]:
        """Get the primary WebSocket URL."""
        return self.ws_urls[0] if self.ws_urls else None


# Singleton config instance
_config: Optional[PipelineConfig] = None


def get_config() -> PipelineConfig:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = PipelineConfig()
    return _config


def reset_config():
    """Reset the global config (useful for testing)."""
    global _config
    _config = None
