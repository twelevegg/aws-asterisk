"""
AICC Pipeline - UDP RTP to WebSocket with Turn Detection.

Processes dual-channel telephony audio (customer/agent) through:
- RTP packet parsing
- Voice Activity Detection (VAD)
- Speech-to-Text (Google Cloud STT)
- Turn completeness detection (Korean morpheme analysis)
- WebSocket event streaming

Usage:
    python -m aicc_pipeline

Environment Variables:
    AICC_WS_URL - WebSocket endpoint URL
    AICC_CUSTOMER_PORT - Customer audio UDP port (default: 12345)
    AICC_AGENT_PORT - Agent audio UDP port (default: 12346)
    GOOGLE_APPLICATION_CREDENTIALS - GCP credentials path
"""

__version__ = "2.0.0"

from .config import PipelineConfig, get_config
from .core import AICCPipeline, TurnEvent

__all__ = [
    "PipelineConfig",
    "get_config",
    "AICCPipeline",
    "TurnEvent",
]
