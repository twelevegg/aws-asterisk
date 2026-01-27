"""Call session state management for multi-call support."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .udp_receiver import UDPReceiver
    from ..core.pipeline import SpeakerProcessor


@dataclass
class CallSession:
    """Represents an active call session with all associated state."""
    call_id: str
    customer_port: int
    agent_port: int
    customer_number: Optional[str] = None
    agent_id: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.utcnow)
    # Processors are set after initialization
    customer_processor: Optional["SpeakerProcessor"] = None
    agent_processor: Optional["SpeakerProcessor"] = None
    # Receivers are set after initialization
    customer_receiver: Optional["UDPReceiver"] = None
    agent_receiver: Optional["UDPReceiver"] = None
