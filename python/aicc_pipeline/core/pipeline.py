"""
AICC Pipeline Orchestrator.

Main entry point that coordinates all components:
- UDP receivers for customer/agent audio
- VAD for speech detection
- STT for transcription
- Turn detection for conversation analysis
- WebSocket for event output
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional
from uuid import uuid4

import numpy as np

from ..config import PipelineConfig, get_config

logger = logging.getLogger("aicc.pipeline")


def _safe_task(coro, name: str = "task"):
    """Create an asyncio task with error handling."""
    async def wrapper():
        try:
            return await coro
        except Exception as e:
            logger.error(f"Async task '{name}' failed: {e}")
    return asyncio.create_task(wrapper())
from ..vad import create_vad, BaseVAD
from ..stt import GoogleCloudSTT
from ..turn import TurnDetector, TurnDecision
from ..websocket import WebSocketManager
from .udp_receiver import UDPReceiver


@dataclass
class TurnEvent:
    """Turn event for WebSocket transmission."""
    type: str
    call_id: str
    speaker: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    # Turn data
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    transcript: Optional[str] = None
    decision: Optional[str] = None
    fusion_score: Optional[float] = None

    # Metadata fields
    customer_number: Optional[str] = None
    agent_id: Optional[str] = None
    total_duration: Optional[float] = None
    turn_count: Optional[int] = None
    speech_ratio: Optional[float] = None
    complete_turns: Optional[int] = None
    incomplete_turns: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.type,
            "call_id": self.call_id,
            "timestamp": self.timestamp
        }

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
        self._vad: BaseVAD = create_vad(
            threshold=config.vad_threshold,
            sample_rate=config.target_sample_rate,
            min_speech_ms=config.min_speech_ms,
            min_silence_ms=config.min_silence_ms,
        )

        # STT (async)
        self._stt = GoogleCloudSTT(
            credentials_path=config.gcp_credentials_path,
            language=config.stt_language,
            sample_rate=config.target_sample_rate,
        )

        # Turn detector (improved weighted fusion)
        self._turn_detector = TurnDetector(
            morpheme_weight=config.turn_morpheme_weight,
            duration_weight=config.turn_duration_weight,
            silence_weight=config.turn_silence_weight,
            complete_threshold=config.turn_complete_threshold,
        )

        # State
        self._audio_buffer = np.array([], dtype=np.int16)
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

        window_size = self._vad.window_size

        while len(self._audio_buffer) >= window_size:
            window = self._audio_buffer[:window_size]
            self._audio_buffer = self._audio_buffer[window_size:]

            window_bytes = window.tobytes()
            is_speech = self._vad.is_speech(window_bytes)

            self._process_vad_state(is_speech, window_bytes)
            self._current_time += window_size / self.config.target_sample_rate

    def _process_vad_state(self, is_speech: bool, audio_bytes: bytes):
        """Process VAD state and detect turns."""
        min_silence_frames = int(
            self.config.min_silence_ms * self.config.target_sample_rate /
            (self._vad.window_size * 1000)
        )

        if is_speech:
            self._silence_frames = 0

            if not self._is_speaking:
                self._is_speaking = True
                self._speech_start_time = self._current_time

            self._stt.add_audio(audio_bytes)
        else:
            if self._is_speaking:
                self._silence_frames += 1

                if self._silence_frames >= min_silence_frames:
                    _safe_task(self._finalize_turn(), "finalize_turn")

    async def _finalize_turn(self):
        """Finalize current turn and emit event."""
        # Capture state immediately to avoid race condition
        speech_start_time = self._speech_start_time
        silence_frames = self._silence_frames
        current_time = self._current_time

        if speech_start_time is None:
            return

        # Reset state immediately to prevent duplicate calls
        self._reset_state()

        end_time = current_time - (
            silence_frames * self._vad.window_size / self.config.target_sample_rate
        )
        duration = end_time - speech_start_time

        if duration < 0.1:
            return

        # Get transcript (async, non-blocking)
        result = await self._stt.transcribe()
        transcript = result.text

        # Calculate silence duration for turn detection
        silence_duration_ms = silence_frames * self._vad.window_size / self.config.target_sample_rate * 1000

        # Detect turn with improved fusion scoring
        turn_result = self._turn_detector.detect(
            transcript=transcript,
            duration=duration,
            silence_duration_ms=silence_duration_ms
        )

        # Update stats
        self.turn_count += 1
        self.total_speech_time += duration

        if turn_result.decision == TurnDecision.COMPLETE:
            self.complete_turns += 1
        else:
            self.incomplete_turns += 1

        # Emit turn event
        event = TurnEvent(
            type="turn_complete",
            call_id=self.call_id,
            speaker=self.speaker,
            start_time=round(speech_start_time, 3),
            end_time=round(end_time, 3),
            transcript=transcript,
            decision=turn_result.decision.value,
            fusion_score=turn_result.fusion_score,
        )
        self.on_turn(event)

    def _reset_state(self):
        """Reset turn state."""
        self._is_speaking = False
        self._speech_start_time = None
        self._silence_frames = 0
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

    def shutdown(self):
        """Shutdown processor."""
        self._stt.shutdown()


class AICCPipeline:
    """Main AICC Pipeline orchestrator."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or get_config()
        self._ws_manager: Optional[WebSocketManager] = None
        self._call_id: Optional[str] = None
        self._customer_processor: Optional[SpeakerProcessor] = None
        self._agent_processor: Optional[SpeakerProcessor] = None
        self._customer_receiver: Optional[UDPReceiver] = None
        self._agent_receiver: Optional[UDPReceiver] = None
        self._start_time: Optional[float] = None
        self._running = False

    async def _on_turn(self, event: TurnEvent):
        """Handle turn event."""
        if self._ws_manager:
            await self._ws_manager.send(event)

    def _on_audio(self, pcm_bytes: bytes, speaker: str):
        """Handle received audio."""
        processor = (
            self._customer_processor
            if speaker == "customer"
            else self._agent_processor
        )
        if processor:
            processor.process_audio(pcm_bytes)

    def _on_first_packet(self, speaker: str):
        """Handle first packet (send metadata_start)."""
        if speaker == "customer" and self._ws_manager:
            event = TurnEvent(
                type="metadata_start",
                call_id=self._call_id,
                customer_number="incoming",
                agent_id="agent01",
            )
            _safe_task(self._ws_manager.send(event), "send_metadata_start")

    async def start(self):
        """Start the pipeline."""
        self._running = True
        self._call_id = str(uuid4())
        self._start_time = time.time()

        logger.info("=" * 60)
        logger.info("AICC Pipeline Starting")
        logger.info("=" * 60)
        logger.info(f"Call ID: {self._call_id}")
        logger.info(f"Customer port: UDP {self.config.customer_port}")
        logger.info(f"Agent port: UDP {self.config.agent_port}")
        if self.config.ws_urls:
            logger.info(f"WebSocket: {self.config.ws_urls[0]}")
        logger.info("=" * 60)

        # Initialize WebSocket manager
        if self.config.ws_urls:
            self._ws_manager = WebSocketManager(
                urls=self.config.ws_urls,
                queue_maxsize=self.config.ws_queue_maxsize,
                reconnect_interval=self.config.ws_reconnect_interval,
            )
            await self._ws_manager.start()

        # Initialize processors
        self._customer_processor = SpeakerProcessor(
            speaker="customer",
            config=self.config,
            on_turn=lambda e: _safe_task(self._on_turn(e), "customer_turn"),
            call_id=self._call_id,
        )

        self._agent_processor = SpeakerProcessor(
            speaker="agent",
            config=self.config,
            on_turn=lambda e: _safe_task(self._on_turn(e), "agent_turn"),
            call_id=self._call_id,
        )

        # Initialize UDP receivers
        self._customer_receiver = UDPReceiver(
            port=self.config.customer_port,
            speaker="customer",
            on_audio=self._on_audio,
            on_first_packet=self._on_first_packet,
        )

        self._agent_receiver = UDPReceiver(
            port=self.config.agent_port,
            speaker="agent",
            on_audio=self._on_audio,
        )

        # Start UDP receivers
        await asyncio.gather(
            self._customer_receiver.start(),
            self._agent_receiver.start(),
        )

    async def stop(self):
        """Stop the pipeline and send final metadata."""
        self._running = False

        # Stop receivers
        if self._customer_receiver:
            self._customer_receiver.stop()
        if self._agent_receiver:
            self._agent_receiver.stop()

        # Send metadata_end
        if self._start_time and self._ws_manager:
            total_duration = time.time() - self._start_time

            customer_stats = (
                self._customer_processor.get_stats()
                if self._customer_processor else {}
            )
            agent_stats = (
                self._agent_processor.get_stats()
                if self._agent_processor else {}
            )

            total_turns = customer_stats.get("turn_count", 0) + agent_stats.get("turn_count", 0)
            total_complete = customer_stats.get("complete_turns", 0) + agent_stats.get("complete_turns", 0)
            total_incomplete = customer_stats.get("incomplete_turns", 0) + agent_stats.get("incomplete_turns", 0)
            total_speech = customer_stats.get("total_speech_time", 0) + agent_stats.get("total_speech_time", 0)

            event = TurnEvent(
                type="metadata_end",
                call_id=self._call_id,
                total_duration=round(total_duration, 2),
                turn_count=total_turns,
                speech_ratio=round(total_speech / total_duration, 3) if total_duration > 0 else 0,
                complete_turns=total_complete,
                incomplete_turns=total_incomplete,
            )
            await self._ws_manager.send(event)
            await asyncio.sleep(0.5)

        # Shutdown processors
        if self._customer_processor:
            self._customer_processor.shutdown()
        if self._agent_processor:
            self._agent_processor.shutdown()

        # Stop WebSocket
        if self._ws_manager:
            await self._ws_manager.stop()

        logger.info("=" * 60)
        logger.info("Pipeline Stopped")
        logger.info("=" * 60)
