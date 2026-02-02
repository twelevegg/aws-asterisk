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
from ..vad import create_vad, BaseVAD, AdaptiveEnergyVAD
from ..stt import StreamingSTT, StreamingSTTSession, StreamingResult, ContinuousSTTSession
from ..turn import TurnDetector, TurnDecision, TurnBoundaryDetector
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

    def to_dict(self) -> Dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, object] = {
            "type": self.type,
            "call_id": self.call_id,
            "timestamp": self.timestamp
        }

        if self.type == "metadata_start":
            result["customer_number"] = self.customer_number
            result["agent_id"] = self.agent_id
        elif self.type == "metadata_end":
            result["total_duration"] = self.total_duration
            result["turn_count"] = self.turn_count
            result["speech_ratio"] = self.speech_ratio
            result["complete_turns"] = self.complete_turns
            result["incomplete_turns"] = self.incomplete_turns
        elif self.type == "turn_complete":
            result["speaker"] = self.speaker
            result["start_time"] = self.start_time
            result["end_time"] = self.end_time
            result["transcript"] = self.transcript
            result["decision"] = self.decision
            result["fusion_score"] = self.fusion_score

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

        # Streaming STT
        self._streaming_stt = StreamingSTT(
            project_id=config.gcp_project_id,
            language_code=config.stt_language,
            model="telephony",
            sample_rate=config.target_sample_rate,
        )
        self._continuous_session: Optional[ContinuousSTTSession] = None

        # Turn detector (improved weighted fusion)
        self._turn_detector = TurnDetector(
            morpheme_weight=config.turn_morpheme_weight,
            duration_weight=config.turn_duration_weight,
            silence_weight=config.turn_silence_weight,
            complete_threshold=config.turn_complete_threshold,
        )

        # Turn boundary detector for continuous streaming
        self._turn_boundary_detector: Optional[TurnBoundaryDetector] = None

        # State
        self._audio_buffer = np.array([], dtype=np.int16)
        self._current_time = 0.0
        self._is_speaking = False
        self._speech_start_time: Optional[float] = None
        self._silence_frames = 0
        self._vad_frame_count = 0  # For debugging

        # Streaming STT state
        self._interim_transcript = ""
        self._final_transcript = ""
        self._waiting_for_final = False
        self._startup_audio_buffer: list[bytes] = []

        # Lock to prevent duplicate finalize calls
        self._finalize_lock = asyncio.Lock()

        # Stats
        self.turn_count = 0
        self.complete_turns = 0
        self.incomplete_turns = 0
        self.total_speech_time = 0.0

    async def start_session(self) -> None:
        """STT 세션 시작. UDP receiver 준비 후 호출."""
        self._continuous_session = ContinuousSTTSession(
            stt=self._streaming_stt,
            call_id=self.call_id,
            speaker=self.speaker,
        )
        self._turn_boundary_detector = TurnBoundaryDetector(
            turn_detector=self._turn_detector,
            min_silence_ms=self.config.turn_boundary_min_silence_ms if hasattr(self.config, 'turn_boundary_min_silence_ms') else 500,
        )
        await self._continuous_session.start(self._on_streaming_result)
        logger.info(f"[{self.speaker}] Continuous STT session started")

    async def _on_streaming_result(self, result: StreamingResult):
        """Handle streaming STT results."""
        if result.is_final:
            self._final_transcript = result.transcript
            logger.debug(f"[{self.speaker}] Final STT result: '{result.transcript}'")
        else:
            self._interim_transcript = result.transcript
            logger.debug(f"[{self.speaker}] Interim STT result: '{result.transcript}'")

        # Feed result to turn boundary detector
        if self._turn_boundary_detector:
            self._turn_boundary_detector.on_stt_result(result, self._current_time)

    def process_audio(self, pcm_bytes: bytes):
        """Process PCM audio chunk."""
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        self._audio_buffer = np.concatenate([self._audio_buffer, samples])

        window_size = self._vad.window_size

        # Log first audio receipt
        if self._vad_frame_count == 0 and len(self._audio_buffer) >= window_size:
            logger.info(f"[{self.speaker}] First audio chunk received, buffer={len(self._audio_buffer)} samples")

        while len(self._audio_buffer) >= window_size:
            window = self._audio_buffer[:window_size]
            self._audio_buffer = self._audio_buffer[window_size:]

            window_bytes = window.tobytes()
            is_speech = self._vad.is_speech(window_bytes)

            # Track VAD frame count for debugging
            self._vad_frame_count += 1

            # Log VAD state changes
            if is_speech and not self._is_speaking:
                rms = np.sqrt(np.mean(window.astype(np.float32) ** 2))
                logger.info(f"[{self.speaker}] Speech START at {self._current_time:.2f}s (RMS={rms:.0f})")
            elif not is_speech and self._is_speaking and self._silence_frames == 0:
                logger.debug(f"[{self.speaker}] Silence detected at {self._current_time:.2f}s")

            self._process_vad_state(is_speech, window_bytes)
            self._current_time += window_size / self.config.target_sample_rate

    def _get_adaptive_silence_ms(self) -> float:
        """
        Get adaptive silence threshold based on speech duration.

        Uses AdaptiveEnergyVAD if available, otherwise falls back to config.
        """
        if self._speech_start_time is None:
            return self.config.min_silence_ms

        speech_duration = self._current_time - self._speech_start_time

        # Use adaptive VAD method if available
        if isinstance(self._vad, AdaptiveEnergyVAD):
            return self._vad.get_adaptive_silence_ms(speech_duration)

        # Fallback: simple adaptive logic
        # Increased thresholds to prevent false turn endings in telephony audio
        if speech_duration < 0.5:
            return 350.0  # Short response (was 200ms, too aggressive)
        elif speech_duration < 2.0:
            return 450.0  # Normal utterance (was 300ms)
        else:
            return self.config.min_silence_ms  # Long, use default

    def _process_vad_state(self, is_speech: bool, audio_bytes: bytes):
        """Process VAD state and detect turns with adaptive silence detection."""
        # Always feed audio to continuous session
        if self._continuous_session:
            _safe_task(self._continuous_session.feed_audio(audio_bytes), "feed_audio")

        if is_speech:
            self._silence_frames = 0

            if not self._is_speaking:
                self._is_speaking = True
                self._speech_start_time = self._current_time
        else:
            if self._is_speaking:
                self._silence_frames += 1

                # Calculate silence duration in ms
                window_ms = (self._vad.window_size / self.config.target_sample_rate) * 1000
                silence_ms = self._silence_frames * window_ms

                # Check turn boundary via detector
                if self._turn_boundary_detector:
                    turn_result = self._turn_boundary_detector.on_vad_silence(
                        silence_ms, self._current_time
                    )
                    if turn_result:
                        # Turn boundary detected, emit turn event
                        self._is_speaking = False
                        _safe_task(self._emit_turn(turn_result), "emit_turn")

    async def _emit_turn(self, turn_result):
        """Emit turn event without stopping session."""
        async with self._finalize_lock:
            # Capture state immediately to avoid race condition
            speech_start_time = self._speech_start_time
            silence_frames = self._silence_frames
            current_time = self._current_time

            if speech_start_time is None:
                return

            end_time = current_time - (
                silence_frames * self._vad.window_size / self.config.target_sample_rate
            )
            duration = end_time - speech_start_time

            if duration < (self.config.min_speech_ms / 1000):
                await self._reset_state()
                return

            # Get transcript snapshot from continuous session
            transcript = turn_result.transcript if hasattr(turn_result, 'transcript') else (self._final_transcript or self._interim_transcript)

            # Skip empty turns
            if not transcript.strip():
                await self._reset_state()
                return

            # Now safe to reset state
            await self._reset_state()

            # Log speech end for debugging
            logger.info(f"[{self.speaker}] Speech END at {end_time:.2f}s, duration={duration:.2f}s, transcript='{transcript[:50]}...' " if len(transcript) > 50 else f"[{self.speaker}] Speech END at {end_time:.2f}s, duration={duration:.2f}s, transcript='{transcript}'")

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

    async def _reset_state(self):
        """Reset turn state."""
        self._is_speaking = False
        self._speech_start_time = None
        self._silence_frames = 0

        # Clean up streaming state
        self._interim_transcript = ""
        self._final_transcript = ""
        self._waiting_for_final = False

        # Reset turn boundary detector state
        if self._turn_boundary_detector:
            self._turn_boundary_detector.reset()

    def get_stats(self) -> dict:
        """Get processing stats."""
        return {
            "speaker": self.speaker,
            "turn_count": self.turn_count,
            "complete_turns": self.complete_turns,
            "incomplete_turns": self.incomplete_turns,
            "total_speech_time": round(self.total_speech_time, 2),
        }

    async def shutdown(self):
        """Shutdown processor and flush pending turn data."""
        # Flush pending turn if speaker was mid-speech
        if self._is_speaking and self._speech_start_time is not None:
            logger.info(f"[{self.speaker}] Flushing pending turn on shutdown")
            # Check if there's a pending turn in the boundary detector
            if self._turn_boundary_detector and self._turn_boundary_detector.has_pending_turn():
                # Force emit with current silence
                window_ms = (self._vad.window_size / self.config.target_sample_rate) * 1000
                silence_ms = self._silence_frames * window_ms
                turn_result = self._turn_boundary_detector.on_vad_silence(silence_ms, self._current_time)
                if turn_result:
                    await self._emit_turn(turn_result)

        if self._continuous_session:
            await self._continuous_session.stop()
        await self._streaming_stt.close()


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
        else:
            logger.warning(f"No processor for speaker: {speaker}")

    def _on_first_packet(self, speaker: str):
        """Handle first packet (send metadata_start)."""
        if speaker == "customer" and self._ws_manager and self._call_id:
            event = TurnEvent(
                type="metadata_start",
                call_id=self._call_id,
                customer_number=self.config.customer_number or "unknown",
                agent_id=self.config.agent_id or "unknown",
            )
            _safe_task(self._ws_manager.send(event), "send_metadata_start")

    async def start(self):
        """Start the pipeline."""
        self._running = True
        self._call_id = self.config.call_id or str(uuid4())
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

        # Start continuous STT sessions before receiving audio
        await asyncio.gather(
            self._customer_processor.start_session(),
            self._agent_processor.start_session(),
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
        if self._start_time and self._ws_manager and self._call_id:
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
            await self._customer_processor.shutdown()
        if self._agent_processor:
            await self._agent_processor.shutdown()

        # Stop WebSocket
        if self._ws_manager:
            await self._ws_manager.stop()

        logger.info("=" * 60)
        logger.info("Pipeline Stopped")
        logger.info("=" * 60)
