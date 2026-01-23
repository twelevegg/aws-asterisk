"""Speech-to-Text module."""
from .google_stt import GoogleCloudSTT, TranscriptResult

__all__ = ["GoogleCloudSTT", "TranscriptResult"]
