#!/usr/bin/env python3
"""
AICC Pipeline - UDP RTP → VAD → STT → WebSocket

화자 분리된 2개의 UDP 스트림을 처리하여 WebSocket으로 전송

Usage:
    python3 aicc_pipeline.py

Ports:
    - UDP 12345: Customer audio
    - UDP 12346: Agent audio
    
WebSocket:
    - ws://127.0.0.1:8000/api/v1/agent/check (local)
    - wss://hewable-wholly-wesley.ngrok-free.dev/api/v1/agent/check (ngrok)
"""

import asyncio
import json
import struct
import socket
import time
import re
import audioop
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Callable
from uuid import uuid4

import numpy as np

# WebSocket
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    print("⚠️  websockets not available. pip install websockets")
    WEBSOCKETS_AVAILABLE = False

# Korean morpheme analyzer
try:
    from kiwipiepy import Kiwi
    KIWI_AVAILABLE = True
except ImportError:
    print("⚠️  kiwipiepy not available. pip install kiwipiepy")
    KIWI_AVAILABLE = False

# Pipecat (optional - fallback to simple VAD if not available)
try:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams as PipecatVADParams
    PIPECAT_AVAILABLE = True
except ImportError:
    print("⚠️  Pipecat not available. Using simple energy-based VAD")
    PIPECAT_AVAILABLE = False

# Google Cloud STT
try:
    from google.cloud import speech_v2 as speech
    from google.api_core.client_options import ClientOptions
    GOOGLE_STT_AVAILABLE = True
except ImportError:
    print("⚠️  Google Cloud Speech not available. pip install google-cloud-speech")
    GOOGLE_STT_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class PipelineConfig:
    """Pipeline configuration."""
    # UDP ports
    customer_port: int = 12345
    agent_port: int = 12346
    
    # Audio
    sample_rate: int = 8000  # ulaw is 8kHz
    target_sample_rate: int = 16000  # For STT
    
    # VAD
    vad_threshold: float = 0.5
    min_speech_ms: float = 250.0
    min_silence_ms: float = 400.0
    
    # WebSocket
    ws_url: str = "ws://127.0.0.1:8000/api/v1/agent/check"
    ws_reconnect_interval: float = 5.0
    
    # STT
    stt_language: str = "ko-KR"
    gcp_credentials_path: str = str(Path.home() / ".config/gcloud/credentials.json")


# =============================================================================
# RTP Parser
# =============================================================================

@dataclass
class RTPPacket:
    """Parsed RTP packet."""
    version: int
    padding: bool
    extension: bool
    marker: bool
    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    payload: bytes
    
    @classmethod
    def parse(cls, data: bytes) -> 'RTPPacket':
        if len(data) < 12:
            raise ValueError(f"Packet too small: {len(data)}")
        
        first_byte = data[0]
        second_byte = data[1]
        
        version = (first_byte >> 6) & 0x03
        padding = bool((first_byte >> 5) & 0x01)
        extension = bool((first_byte >> 4) & 0x01)
        csrc_count = first_byte & 0x0F
        marker = bool((second_byte >> 7) & 0x01)
        payload_type = second_byte & 0x7F
        
        sequence_number = struct.unpack('!H', data[2:4])[0]
        timestamp = struct.unpack('!I', data[4:8])[0]
        ssrc = struct.unpack('!I', data[8:12])[0]
        
        header_size = 12 + (csrc_count * 4)
        payload = data[header_size:]
        
        return cls(
            version=version,
            padding=padding,
            extension=extension,
            marker=marker,
            payload_type=payload_type,
            sequence_number=sequence_number,
            timestamp=timestamp,
            ssrc=ssrc,
            payload=payload
        )


# =============================================================================
# Audio Converter
# =============================================================================

class AudioConverter:
    """Convert ulaw 8kHz → PCM 16kHz."""
    
    @staticmethod
    def ulaw_to_pcm16(ulaw_bytes: bytes) -> bytes:
        """Convert u-law to 16-bit PCM."""
        return audioop.ulaw2lin(ulaw_bytes, 2)
    
    @staticmethod
    def resample_8k_to_16k(pcm_8k: bytes) -> bytes:
        """Resample from 8kHz to 16kHz."""
        return audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)[0]
    
    @classmethod
    def convert(cls, ulaw_bytes: bytes) -> bytes:
        """Full conversion: ulaw 8kHz → PCM 16kHz."""
        pcm_8k = cls.ulaw_to_pcm16(ulaw_bytes)
        pcm_16k = cls.resample_8k_to_16k(pcm_8k)
        return pcm_16k


# =============================================================================
# Simple Energy VAD (fallback)
# =============================================================================

class SimpleEnergyVAD:
    """Simple energy-based VAD when Pipecat is not available."""
    
    def __init__(self, threshold: float = 500.0):
        self.threshold = threshold
    
    def is_speech(self, pcm_bytes: bytes) -> bool:
        """Check if audio contains speech based on energy."""
        if len(pcm_bytes) < 2:
            return False
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        energy = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        return energy > self.threshold


# =============================================================================
# Korean Morpheme Analyzer
# =============================================================================

class KoreanMorphemeAnalyzer:
    """한국어 형태소 분석 - 턴 완결성 판단."""
    
    ENDING_PATTERNS = [
        r'습니다$', r'입니다$', r'합니다$', r'됩니다$',
        r'예요$', r'에요$', r'이에요$', r'네요$', r'군요$',
        r'거든요$', r'잖아요$', r'는데요$',
        r'나요\?*$', r'까요\?*$', r'세요\?*$', r'어요\?*$',
        r'습니까\?*$', r'입니까\?*$',
        r'하세요$', r'주세요$', r'해주세요$',
        r'^네$', r'^예$', r'^아니요$', r'^아니오$',
        r'^알겠습니다$', r'^감사합니다$',
    ]
    
    CONTINUING_PATTERNS = [
        r'는데$', r'인데$', r'은데$',
        r'고$', r'며$', r'서$', r'니까$', r'면$',
        r'지만$', r'라서$', r'해서$',
    ]
    
    def __init__(self):
        self._kiwi = Kiwi() if KIWI_AVAILABLE else None
        self._ending_re = [re.compile(p) for p in self.ENDING_PATTERNS]
        self._continuing_re = [re.compile(p) for p in self.CONTINUING_PATTERNS]
    
    def analyze(self, text: str) -> float:
        """Return completion score (0.0 ~ 1.0)."""
        if not text or not text.strip():
            return 0.5
        
        text = text.strip()
        
        for pattern in self._ending_re:
            if pattern.search(text):
                return 0.95
        
        for pattern in self._continuing_re:
            if pattern.search(text):
                return 0.2
        
        if self._kiwi:
            try:
                result = self._kiwi.analyze(text)
                if result and result[0][0]:
                    last_tag = result[0][0][-1].tag
                    if last_tag == 'EF':
                        return 0.85
                    elif last_tag == 'EC':
                        return 0.3
            except Exception:
                pass
        
        return 0.5


# =============================================================================
# Google Cloud STT
# =============================================================================

class GoogleCloudSTT:
    """Google Cloud Speech-to-Text V2 for Korean."""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self._client = None
        self._recognizer = None
        self._buffer: List[bytes] = []
        
        if GOOGLE_STT_AVAILABLE:
            self._init_client()
    
    def _init_client(self):
        """Initialize Google Cloud STT client."""
        import os
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.config.gcp_credentials_path
        
        # Get project ID from credentials
        creds_path = Path(self.config.gcp_credentials_path)
        if creds_path.exists():
            with open(creds_path) as f:
                creds = json.load(f)
                project_id = creds.get("project_id", "")
                
            self._client = speech.SpeechClient()
            self._recognizer = f"projects/{project_id}/locations/global/recognizers/_"
            print(f"✅ Google Cloud STT initialized (project: {project_id})")
        else:
            print(f"⚠️  GCP credentials not found: {self.config.gcp_credentials_path}")
    
    def add_audio(self, pcm_bytes: bytes):
        """Add audio to buffer."""
        self._buffer.append(pcm_bytes)
    
    def get_transcript(self) -> str:
        """Get transcript from buffered audio."""
        if not self._client or not self._buffer:
            return ""
        
        try:
            audio_data = b''.join(self._buffer)
            
            config = speech.RecognitionConfig(
                explicit_decoding_config=speech.ExplicitDecodingConfig(
                    encoding=speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=self.config.target_sample_rate,
                    audio_channel_count=1,
                ),
                language_codes=[self.config.stt_language],
                model="long",
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
            print(f"⚠️  STT error: {e}")
            return ""
    
    def clear(self):
        """Clear buffer."""
        self._buffer = []


# =============================================================================
# Speaker Turn Processor
# =============================================================================

class TurnDecision(Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass
class TurnEvent:
    """Turn event to send via WebSocket."""
    type: str
    call_id: str
    speaker: str  # "customer" or "agent"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    transcript: Optional[str] = None
    decision: Optional[str] = None
    fusion_score: Optional[float] = None
    
    # Metadata fields (for start/end)
    customer_number: Optional[str] = None
    agent_id: Optional[str] = None
    total_duration: Optional[float] = None
    turn_count: Optional[int] = None
    speech_ratio: Optional[float] = None
    complete_turns: Optional[int] = None
    incomplete_turns: Optional[int] = None
    
    def to_dict(self) -> dict:
        result = {"type": self.type, "call_id": self.call_id, "timestamp": self.timestamp}
        
        if self.type == "metadata_start":
            result.update({
                "customer_number": self.customer_number,
                "agent_id": self.agent_id,
            })
        elif self.type == "metadata_end":
            result.update({
                "total_duration": self.total_duration,
                "turn_count": self.turn_count,
                "speech_ratio": self.speech_ratio,
                "complete_turns": self.complete_turns,
                "incomplete_turns": self.incomplete_turns,
            })
        elif self.type == "turn_complete":
            result.update({
                "speaker": self.speaker,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "transcript": self.transcript,
                "decision": self.decision,
                "fusion_score": self.fusion_score,
            })
        
        return result


class SpeakerProcessor:
    """Process audio for a single speaker."""
    
    def __init__(
        self,
        speaker: str,
        config: PipelineConfig,
        on_turn: Callable[[TurnEvent], None],
        call_id: str,
    ):
        self.speaker = speaker
        self.config = config
        self.on_turn = on_turn
        self.call_id = call_id
        
        # VAD
        if PIPECAT_AVAILABLE:
            vad_params = PipecatVADParams(
                confidence=config.vad_threshold,
                start_secs=config.min_speech_ms / 1000,
                stop_secs=config.min_silence_ms / 1000,
            )
            self._vad = SileroVADAnalyzer(params=vad_params)
            self._vad.set_sample_rate(config.target_sample_rate)
            self._window_size = self._vad.num_frames_required()
        else:
            self._vad = SimpleEnergyVAD()
            self._window_size = 512  # ~32ms at 16kHz
        
        # STT
        self._stt = GoogleCloudSTT(config)
        
        # Morpheme analyzer
        self._morpheme = KoreanMorphemeAnalyzer()
        
        # State
        self._audio_buffer = np.array([], dtype=np.int16)
        self._speech_buffer: List[bytes] = []
        self._current_time = 0.0
        self._is_speaking = False
        self._speech_start_time: Optional[float] = None
        self._silence_frames = 0
        
        # Stats
        self.turn_count = 0
        self.complete_turns = 0
        self.incomplete_turns = 0
        self.total_speech_time = 0.0
    
    def process_audio(self, pcm_bytes: bytes):
        """Process PCM audio chunk."""
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        self._audio_buffer = np.concatenate([self._audio_buffer, samples])
        
        while len(self._audio_buffer) >= self._window_size:
            window = self._audio_buffer[:self._window_size]
            self._audio_buffer = self._audio_buffer[self._window_size:]
            
            window_bytes = window.tobytes()
            
            # VAD check
            if PIPECAT_AVAILABLE:
                confidence = self._vad.voice_confidence(window_bytes)
                is_speech = confidence >= self.config.vad_threshold
            else:
                is_speech = self._vad.is_speech(window_bytes)
            
            self._process_vad_state(is_speech, window_bytes)
            self._current_time += self._window_size / self.config.target_sample_rate
    
    def _process_vad_state(self, is_speech: bool, audio_bytes: bytes):
        """Process VAD state and detect turns."""
        min_silence_frames = int(
            self.config.min_silence_ms * self.config.target_sample_rate /
            (self._window_size * 1000)
        )
        
        if is_speech:
            self._silence_frames = 0
            
            if not self._is_speaking:
                self._is_speaking = True
                self._speech_start_time = self._current_time
                self._speech_buffer = []
            
            self._speech_buffer.append(audio_bytes)
            self._stt.add_audio(audio_bytes)
        else:
            if self._is_speaking:
                self._silence_frames += 1
                
                if self._silence_frames >= min_silence_frames:
                    self._finalize_turn()
    
    def _finalize_turn(self):
        """Finalize current turn and emit event."""
        if not self._speech_start_time:
            return
        
        end_time = self._current_time - (
            self._silence_frames * self._window_size / self.config.target_sample_rate
        )
        duration = end_time - self._speech_start_time
        
        if duration < 0.1:
            self._reset_state()
            return
        
        # Get transcript
        transcript = self._stt.get_transcript()
        
        # Morpheme analysis
        morpheme_score = self._morpheme.analyze(transcript) if transcript else 0.5
        
        # Simple fusion (without Smart Turn for now)
        # High morpheme score + sufficient duration = complete
        if morpheme_score >= 0.7 or duration > 2.0:
            decision = TurnDecision.COMPLETE
            fusion_score = morpheme_score
            self.complete_turns += 1
        else:
            decision = TurnDecision.INCOMPLETE
            fusion_score = morpheme_score
            self.incomplete_turns += 1
        
        self.turn_count += 1
        self.total_speech_time += duration
        
        # Emit turn event
        event = TurnEvent(
            type="turn_complete",
            call_id=self.call_id,
            speaker=self.speaker,
            start_time=round(self._speech_start_time, 3),
            end_time=round(end_time, 3),
            transcript=transcript,
            decision=decision.value,
            fusion_score=round(fusion_score, 3),
        )
        self.on_turn(event)
        
        self._reset_state()
    
    def _reset_state(self):
        """Reset turn state."""
        self._is_speaking = False
        self._speech_start_time = None
        self._silence_frames = 0
        self._speech_buffer = []
        self._stt.clear()
    
    def get_stats(self) -> dict:
        """Get processing stats."""
        return {
            "speaker": self.speaker,
            "turn_count": self.turn_count,
            "complete_turns": self.complete_turns,
            "incomplete_turns": self.incomplete_turns,
            "total_speech_time": round(self.total_speech_time, 2),
        }


# =============================================================================
# WebSocket Manager
# =============================================================================

class WebSocketManager:
    """Manage WebSocket connection to FastAPI."""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self._ws = None
        self._connected = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
    
    async def connect(self):
        """Connect to WebSocket server."""
        while self._running:
            try:
                print(f"🔌 Connecting to WebSocket: {self.config.ws_url}")
                self._ws = await websockets.connect(
                    self.config.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                )
                self._connected = True
                print("✅ WebSocket connected!")
                return
            except Exception as e:
                print(f"⚠️  WebSocket connection failed: {e}")
                print(f"   Retrying in {self.config.ws_reconnect_interval}s...")
                await asyncio.sleep(self.config.ws_reconnect_interval)
    
    async def send(self, event: TurnEvent):
        """Send event to WebSocket."""
        await self._queue.put(event)
    
    async def _send_loop(self):
        """Background loop to send queued events."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                
                if not self._connected or not self._ws:
                    await self.connect()
                
                if self._ws:
                    data = json.dumps(event.to_dict(), ensure_ascii=False)
                    await self._ws.send(data)
                    print(f"📤 Sent: {event.type} ({event.speaker if hasattr(event, 'speaker') and event.speaker else 'meta'})")
                    
            except asyncio.TimeoutError:
                continue
            except websockets.exceptions.ConnectionClosed:
                print("⚠️  WebSocket disconnected, reconnecting...")
                self._connected = False
                await self.connect()
            except Exception as e:
                print(f"⚠️  Send error: {e}")
    
    async def start(self):
        """Start WebSocket manager."""
        self._running = True
        asyncio.create_task(self._send_loop())
        await self.connect()
    
    async def stop(self):
        """Stop WebSocket manager."""
        self._running = False
        if self._ws:
            await self._ws.close()


# =============================================================================
# Main Pipeline
# =============================================================================

class AICCPipeline:
    """Main AICC pipeline."""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self._ws_manager = WebSocketManager(self.config)
        self._call_id: Optional[str] = None
        self._customer_processor: Optional[SpeakerProcessor] = None
        self._agent_processor: Optional[SpeakerProcessor] = None
        self._start_time: Optional[float] = None
        self._running = False
    
    async def _on_turn(self, event: TurnEvent):
        """Handle turn event."""
        await self._ws_manager.send(event)
    
    async def _udp_receiver(self, port: int, speaker: str):
        """UDP receiver for a speaker."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', port))
        sock.setblocking(False)
        
        print(f"🎤 Listening on UDP:{port} ({speaker})")
        
        processor = self._customer_processor if speaker == "customer" else self._agent_processor
        first_packet = True
        
        loop = asyncio.get_event_loop()
        
        while self._running:
            try:
                data = await loop.sock_recv(sock, 2048)
                
                if first_packet and speaker == "customer":
                    first_packet = False
                    # Send metadata_start
                    event = TurnEvent(
                        type="metadata_start",
                        call_id=self._call_id,
                        speaker="",
                        customer_number="incoming",
                        agent_id="agent02",
                    )
                    await self._ws_manager.send(event)
                
                # Parse RTP
                rtp = RTPPacket.parse(data)
                
                # Convert audio
                pcm_16k = AudioConverter.convert(rtp.payload)
                
                # Process
                processor.process_audio(pcm_16k)
                
            except BlockingIOError:
                await asyncio.sleep(0.001)
            except Exception as e:
                if self._running:
                    print(f"⚠️  UDP error ({speaker}): {e}")
        
        sock.close()
    
    async def start(self):
        """Start the pipeline."""
        self._running = True
        self._call_id = str(uuid4())
        self._start_time = time.time()
        
        print("=" * 60)
        print("AICC Pipeline Starting")
        print("=" * 60)
        print(f"Call ID: {self._call_id}")
        print(f"Customer port: UDP {self.config.customer_port}")
        print(f"Agent port: UDP {self.config.agent_port}")
        print(f"WebSocket: {self.config.ws_url}")
        print("=" * 60)
        
        # Initialize processors
        self._customer_processor = SpeakerProcessor(
            speaker="customer",
            config=self.config,
            on_turn=lambda e: asyncio.create_task(self._on_turn(e)),
            call_id=self._call_id,
        )
        
        self._agent_processor = SpeakerProcessor(
            speaker="agent",
            config=self.config,
            on_turn=lambda e: asyncio.create_task(self._on_turn(e)),
            call_id=self._call_id,
        )
        
        # Start WebSocket
        await self._ws_manager.start()
        
        # Start UDP receivers
        await asyncio.gather(
            self._udp_receiver(self.config.customer_port, "customer"),
            self._udp_receiver(self.config.agent_port, "agent"),
        )
    
    async def stop(self):
        """Stop the pipeline and send final metadata."""
        self._running = False
        
        if self._start_time:
            total_duration = time.time() - self._start_time
            
            # Combine stats
            customer_stats = self._customer_processor.get_stats() if self._customer_processor else {}
            agent_stats = self._agent_processor.get_stats() if self._agent_processor else {}
            
            total_turns = customer_stats.get("turn_count", 0) + agent_stats.get("turn_count", 0)
            total_complete = customer_stats.get("complete_turns", 0) + agent_stats.get("complete_turns", 0)
            total_incomplete = customer_stats.get("incomplete_turns", 0) + agent_stats.get("incomplete_turns", 0)
            total_speech = customer_stats.get("total_speech_time", 0) + agent_stats.get("total_speech_time", 0)
            
            # Send metadata_end
            event = TurnEvent(
                type="metadata_end",
                call_id=self._call_id,
                speaker="",
                total_duration=round(total_duration, 2),
                turn_count=total_turns,
                speech_ratio=round(total_speech / total_duration, 3) if total_duration > 0 else 0,
                complete_turns=total_complete,
                incomplete_turns=total_incomplete,
            )
            await self._ws_manager.send(event)
            
            # Wait for send
            await asyncio.sleep(0.5)
        
        await self._ws_manager.stop()
        
        print("\n" + "=" * 60)
        print("Pipeline Stopped")
        print("=" * 60)


async def main():
    """Main entry point."""
    import signal
    
    config = PipelineConfig(
        # Local FastAPI
        ws_url="ws://127.0.0.1:8000/api/v1/agent/check",
        # Or use ngrok
        # ws_url="wss://hewable-wholly-wesley.ngrok-free.dev/api/v1/agent/check",
    )
    
    pipeline = AICCPipeline(config)
    
    # Handle shutdown
    def signal_handler():
        print("\n🛑 Shutdown requested...")
        asyncio.create_task(pipeline.stop())
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await pipeline.start()
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        await pipeline.stop()


if __name__ == "__main__":
    asyncio.run(main())
