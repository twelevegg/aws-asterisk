# AICC Pipeline API Documentation

## Overview

AICC Pipeline processes real-time call audio through:
1. UDP RTP reception
2. Voice Activity Detection (VAD)
3. Speech-to-Text (STT)
4. Turn detection with Korean morpheme analysis
5. WebSocket event streaming

---

## Core Modules

### `aicc_pipeline.core.pipeline`

Main orchestrator coordinating all components.

#### `AICCPipeline`

```python
class AICCPipeline:
    """Main AICC Pipeline orchestrator.

    Coordinates UDP receivers, processors, and WebSocket output.

    Args:
        config: Optional PipelineConfig. Uses get_config() if None.

    Methods:
        start(): Start the pipeline (async)
        stop(): Stop and cleanup (async)

    Example:
        pipeline = AICCPipeline()
        await pipeline.start()
    """
```

#### `TurnEvent`

```python
@dataclass
class TurnEvent:
    """Turn event for WebSocket transmission.

    Attributes:
        type: Event type ('metadata_start', 'turn_complete', 'metadata_end')
        call_id: Unique call identifier
        speaker: 'customer' or 'agent'
        timestamp: ISO 8601 timestamp
        transcript: Transcribed text (turn_complete only)
        decision: 'complete' or 'incomplete' (turn_complete only)
        fusion_score: Turn completeness score 0.0-1.0
    """
```

#### `SpeakerProcessor`

```python
class SpeakerProcessor:
    """Process audio for a single speaker.

    Handles VAD, STT buffering, and turn detection for one speaker.

    Args:
        speaker: Speaker identifier ('customer' or 'agent')
        config: PipelineConfig instance
        on_turn: Callback for turn events
        call_id: Call identifier

    Methods:
        process_audio(pcm_bytes): Process PCM audio chunk
        get_stats(): Get processing statistics
    """
```

---

### `aicc_pipeline.core.udp_receiver`

#### `UDPReceiver`

```python
class UDPReceiver:
    """Async UDP receiver for RTP audio.

    Receives RTP packets and converts to PCM.

    Args:
        port: UDP port to listen on
        speaker: Speaker identifier
        on_audio: Callback (pcm_bytes, speaker)
        on_first_packet: Optional first packet callback

    Methods:
        start(): Start receiving (async)
        stop(): Stop receiving
        get_stats(): Get receiver statistics

    Properties:
        packet_count: Number of packets received
        error_count: Number of parse errors
    """
```

---

### `aicc_pipeline.audio`

#### `RTPPacket`

```python
@dataclass
class RTPPacket:
    """Parsed RTP packet.

    Attributes:
        version: RTP version (should be 2)
        payload_type: Audio codec (0=PCMU/ulaw)
        sequence_number: Packet sequence
        timestamp: RTP timestamp
        ssrc: Synchronization source
        payload: Audio payload bytes

    Class Methods:
        parse(data: bytes) -> RTPPacket: Parse raw packet

    Raises:
        ValueError: If packet is too small (<12 bytes)
    """
```

#### `AudioConverter`

```python
class AudioConverter:
    """Convert ulaw 8kHz to PCM 16kHz.

    Static Methods:
        ulaw_to_pcm16(ulaw_bytes) -> bytes: Convert u-law to 16-bit PCM
        resample_8k_to_16k(pcm_8k) -> bytes: Resample to 16kHz
        convert(ulaw_bytes) -> bytes: Full conversion pipeline
    """
```

---

### `aicc_pipeline.vad`

#### `BaseVAD` (Abstract)

```python
class BaseVAD(ABC):
    """Abstract base class for VAD implementations.

    Abstract Methods:
        is_speech(pcm_bytes) -> bool: Check if audio contains speech
        get_confidence(pcm_bytes) -> float: Get confidence score (0-1)

    Properties:
        window_size: Required audio window size in samples
    """
```

#### `EnergyVAD`

```python
class EnergyVAD(BaseVAD):
    """Simple energy-based VAD.

    Args:
        threshold: RMS energy threshold (default: 500.0)
        sample_rate: Audio sample rate (default: 16000)
        window_ms: Window size in ms (default: 32.0)
    """
```

#### `create_vad()`

```python
def create_vad(
    threshold: float = 0.5,
    sample_rate: int = 16000,
    min_speech_ms: float = 250.0,
    min_silence_ms: float = 400.0,
    prefer_silero: bool = True
) -> BaseVAD:
    """Factory function to create VAD instance.

    Returns SileroVAD if available and preferred, else EnergyVAD.
    """
```

---

### `aicc_pipeline.stt`

#### `GoogleCloudSTT`

```python
class GoogleCloudSTT:
    """Google Cloud Speech-to-Text V2.

    Args:
        credentials_path: Path to GCP credentials JSON
        language: Recognition language (default: 'ko-KR')
        sample_rate: Audio sample rate (default: 16000)
        max_retries: Max retries on failure (default: 3)

    Methods:
        add_audio(pcm_bytes): Add audio to buffer
        clear(): Clear audio buffer
        transcribe(audio_bytes=None) -> TranscriptResult: Async transcription
        get_transcript() -> str: Sync transcription (blocks)

    Properties:
        is_available: Whether client is initialized
    """
```

#### `TranscriptResult`

```python
@dataclass
class TranscriptResult:
    """STT transcript result.

    Attributes:
        text: Transcribed text
        is_final: Whether result is final
        confidence: Recognition confidence (0-1)
        language: Recognition language
    """
```

---

### `aicc_pipeline.turn`

#### `TurnDetector`

```python
class TurnDetector:
    """Turn detector with weighted fusion scoring.

    Args:
        morpheme_weight: Weight for morpheme analysis (default: 0.6)
        duration_weight: Weight for duration (default: 0.2)
        silence_weight: Weight for silence (default: 0.2)
        complete_threshold: Threshold for complete turn (default: 0.65)

    Methods:
        detect(transcript, duration, silence_duration_ms) -> TurnResult
    """
```

#### `KoreanMorphemeAnalyzer`

```python
class KoreanMorphemeAnalyzer:
    """Korean morpheme analysis for turn completeness.

    Analyzes Korean sentence endings to determine if a turn is complete.

    Methods:
        analyze(text: str) -> float: Return completion score (0-1)

    Score Guidelines:
        0.95: Formal endings (-습니다, -입니다)
        0.85: Final endings detected by kiwipiepy
        0.50: Neutral/unknown
        0.20: Connecting endings (-는데, -고)
    """
```

---

### `aicc_pipeline.websocket`

#### `WebSocketManager`

```python
class WebSocketManager:
    """Manage multiple WebSocket connections.

    Features:
        - Queue with oldest-event-drop on overflow
        - Automatic reconnection
        - Multiple endpoint support

    Args:
        urls: List of WebSocket URLs
        queue_maxsize: Max queue size (default: 1000)
        reconnect_interval: Reconnect delay in seconds (default: 5.0)

    Methods:
        connect_all(): Connect to all URLs (async)
        send(event): Queue event for sending (async)
        start(): Start manager (async)
        stop(): Stop and close connections (async)
        get_stats(): Get manager statistics

    Properties:
        connected_count: Number of active connections
        dropped_count: Events dropped due to overflow
        sent_count: Successfully sent events
    """
```

---

### `aicc_pipeline.config`

#### `PipelineConfig`

```python
@dataclass
class PipelineConfig:
    """Pipeline configuration with environment variable support.

    Attributes:
        customer_port: Customer UDP port (AICC_CUSTOMER_PORT, default: 12345)
        agent_port: Agent UDP port (AICC_AGENT_PORT, default: 12346)
        sample_rate: Input sample rate (8000)
        target_sample_rate: Output sample rate (16000)
        vad_threshold: VAD confidence threshold (AICC_VAD_THRESHOLD, default: 0.5)
        ws_urls: WebSocket URLs (AICC_WS_URL, AICC_WS_URL_1, ...)
        stt_language: STT language (AICC_STT_LANGUAGE, default: 'ko-KR')
        turn_*_weight: Turn detection weights
        debug: Debug mode (AICC_DEBUG, default: false)
    """
```

#### `get_config()`

```python
def get_config() -> PipelineConfig:
    """Get or create the global config singleton."""
```

#### `setup_logging()`

```python
def setup_logging(
    level: str = None,
    format_string: str = None,
    name: str = "aicc"
) -> logging.Logger:
    """Setup logging for AICC Pipeline.

    Args:
        level: Log level (from AICC_LOG_LEVEL or INFO)
        format_string: Custom format string
        name: Logger name

    Returns:
        Configured logger instance
    """
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AICC_WS_URL` | - | Primary WebSocket URL (required) |
| `AICC_WS_URL_1` | - | Additional WebSocket URL |
| `AICC_CUSTOMER_PORT` | 12345 | Customer audio UDP port |
| `AICC_AGENT_PORT` | 12346 | Agent audio UDP port |
| `AICC_VAD_THRESHOLD` | 0.5 | VAD confidence threshold |
| `AICC_MIN_SPEECH_MS` | 250.0 | Minimum speech duration |
| `AICC_MIN_SILENCE_MS` | 400.0 | Minimum silence for turn end |
| `AICC_STT_LANGUAGE` | ko-KR | STT recognition language |
| `AICC_LOG_LEVEL` | INFO | Log level |
| `GOOGLE_APPLICATION_CREDENTIALS` | - | GCP credentials path |

---

## WebSocket Event Schema

### metadata_start
```json
{
  "type": "metadata_start",
  "call_id": "uuid",
  "timestamp": "ISO8601",
  "customer_number": "+821012345678",
  "agent_id": "agent01"
}
```

### turn_complete
```json
{
  "type": "turn_complete",
  "call_id": "uuid",
  "timestamp": "ISO8601",
  "speaker": "customer",
  "start_time": 0.0,
  "end_time": 1.5,
  "transcript": "안녕하세요",
  "decision": "complete",
  "fusion_score": 0.85
}
```

### metadata_end
```json
{
  "type": "metadata_end",
  "call_id": "uuid",
  "timestamp": "ISO8601",
  "total_duration": 120.5,
  "turn_count": 15,
  "speech_ratio": 0.65,
  "complete_turns": 10,
  "incomplete_turns": 5
}
```
