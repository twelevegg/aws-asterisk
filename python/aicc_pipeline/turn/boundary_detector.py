"""
Turn Boundary Detector for Continuous STT Streaming.

Combines STT final results with VAD silence detection to determine turn boundaries
without stopping the STT session.
"""

import logging
from typing import Optional
from dataclasses import dataclass

from .detector import TurnDetector, TurnDecision

logger = logging.getLogger("aicc.turn_boundary")


@dataclass
class StreamingResult:
    """Streaming STT result (minimal type definition for compatibility)."""
    transcript: str
    is_final: bool
    confidence: float = 0.0
    stability: float = 0.0


@dataclass
class TurnResult:
    """Turn boundary detection result."""
    transcript: str
    decision: TurnDecision
    fusion_score: float


class TurnBoundaryDetector:
    """
    Detects turn boundaries by combining STT final results with VAD silence.

    State Diagram:
        IDLE → (STT final result) → ACCUMULATING
        ACCUMULATING → (more finals) → ACCUMULATING
        ACCUMULATING → (VAD silence >= threshold) → EMIT_TURN → IDLE

    Key Features:
    - Accumulates multiple final results before silence threshold
    - Validates minimum transcript length (filters empty turns)
    - Uses existing TurnDetector for morpheme analysis
    - Does NOT stop STT session on turn boundary
    """

    def __init__(
        self,
        turn_detector: TurnDetector,
        min_silence_ms: float = 500,
        min_transcript_chars: int = 1
    ):
        """
        Initialize turn boundary detector.

        Args:
            turn_detector: Existing TurnDetector for morpheme analysis
            min_silence_ms: Minimum silence duration to consider turn boundary
            min_transcript_chars: Minimum characters in transcript (after strip)
        """
        self._turn_detector = turn_detector
        self._min_silence_ms = min_silence_ms
        self._min_chars = min_transcript_chars

        # State tracking
        self._pending_transcript = ""
        self._last_final_time: Optional[float] = None
        self._speech_start_time: Optional[float] = None

        # Waiting for final result state (race condition fix)
        self._waiting_for_final: bool = False
        self._silence_detected_time: Optional[float] = None
        self._pending_silence_ms: float = 0

    def on_stt_result(self, result: StreamingResult, current_time: float) -> Optional[TurnResult]:
        """
        Process STT result (interim or final).

        Only final results are accumulated. Interim results are ignored
        (they're used for UI display elsewhere).

        Args:
            result: Streaming STT result
            current_time: Current timestamp in seconds

        Returns:
            TurnResult if deferred turn can now be emitted, None otherwise
        """
        if not result.is_final:
            # Interim results: ignore (used for display only)
            return None

        # Final result: accumulate
        if self._pending_transcript:
            # Multiple finals before silence - concatenate with space
            self._pending_transcript += " " + result.transcript
        else:
            # First final result
            self._pending_transcript = result.transcript
            # Mark speech start time (for duration calculation)
            if self._speech_start_time is None:
                self._speech_start_time = current_time

        self._last_final_time = current_time
        logger.debug(
            f"Accumulated final result: '{result.transcript}' "
            f"(total pending: '{self._pending_transcript}')"
        )

        # Check if we were waiting for final result after silence detection
        if self._waiting_for_final:
            elapsed = current_time - self._silence_detected_time if self._silence_detected_time else float('inf')
            if elapsed < 1.0:  # 1 second grace period
                logger.debug(
                    f"Final result received within grace period ({elapsed:.3f}s), "
                    f"emitting deferred turn"
                )
                # Emit the deferred turn immediately
                deferred_turn = self._emit_deferred_turn(current_time)
                # Reset waiting state
                self._waiting_for_final = False
                self._silence_detected_time = None
                self._pending_silence_ms = 0
                return deferred_turn
            else:
                # Too late, silence ended
                logger.debug(
                    f"Final result received after grace period ({elapsed:.3f}s), "
                    f"continuing normal flow"
                )
                self._waiting_for_final = False
                self._silence_detected_time = None
                self._pending_silence_ms = 0

        return None

    def on_vad_silence(
        self,
        silence_ms: float,
        current_time: float
    ) -> Optional[TurnResult]:
        """
        Process VAD silence event.

        Checks if accumulated transcript + silence duration indicate turn boundary.

        Args:
            silence_ms: Current accumulated silence duration in milliseconds
            current_time: Current timestamp in seconds

        Returns:
            TurnResult if turn boundary detected, None otherwise

        Edge Cases Handled:
        - Silence before any final result → defer decision (wait for final)
        - Silence below threshold → return None
        - Empty/whitespace-only transcript → reset and return None
        - Transcript too short → reset and return None
        """
        # Silence threshold not met
        if silence_ms < self._min_silence_ms:
            return None

        # No final results yet - defer decision and wait for final result
        if self._last_final_time is None:
            if not self._waiting_for_final:
                self._waiting_for_final = True
                self._silence_detected_time = current_time
                self._pending_silence_ms = silence_ms
                logger.debug(
                    f"Waiting for STT final result (silence={silence_ms}ms)"
                )
            return None

        # Validate transcript (strip whitespace)
        stripped = self._pending_transcript.strip()
        if len(stripped) < self._min_chars:
            logger.debug(
                f"Ignoring turn: transcript too short ({len(stripped)} chars)"
            )
            self.reset()
            return None

        # Calculate speech duration
        speech_duration_sec = (
            current_time - self._speech_start_time
            if self._speech_start_time
            else 0.0
        )

        # Analyze with existing TurnDetector (morpheme fusion)
        detector_result = self._turn_detector.detect(
            transcript=stripped,
            duration=speech_duration_sec,
            silence_duration_ms=silence_ms
        )

        # Prepare result
        result = TurnResult(
            transcript=stripped,
            decision=detector_result.decision,
            fusion_score=detector_result.fusion_score
        )

        logger.info(
            f"Turn boundary detected: '{stripped}' "
            f"(decision={result.decision.value}, score={result.fusion_score:.3f}, "
            f"duration={speech_duration_sec:.1f}s, silence={silence_ms:.0f}ms)"
        )

        # Reset state for next turn
        self.reset()

        return result

    def _emit_deferred_turn(self, current_time: float) -> Optional[TurnResult]:
        """
        Helper method to emit a deferred turn when final result arrives.

        Args:
            current_time: Current timestamp in seconds

        Returns:
            TurnResult if valid turn, None if invalid (empty/too short)
        """
        # Validate transcript (strip whitespace)
        stripped = self._pending_transcript.strip()
        if len(stripped) < self._min_chars:
            logger.debug(
                f"Ignoring deferred turn: transcript too short ({len(stripped)} chars)"
            )
            self.reset()
            return None

        # Calculate speech duration
        speech_duration_sec = (
            current_time - self._speech_start_time
            if self._speech_start_time
            else 0.0
        )

        # Analyze with existing TurnDetector (morpheme fusion)
        detector_result = self._turn_detector.detect(
            transcript=stripped,
            duration=speech_duration_sec,
            silence_duration_ms=self._pending_silence_ms
        )

        # Prepare result
        result = TurnResult(
            transcript=stripped,
            decision=detector_result.decision,
            fusion_score=detector_result.fusion_score
        )

        logger.info(
            f"Deferred turn boundary detected: '{stripped}' "
            f"(decision={result.decision.value}, score={result.fusion_score:.3f}, "
            f"duration={speech_duration_sec:.1f}s, silence={self._pending_silence_ms:.0f}ms)"
        )

        # Reset state for next turn
        self.reset()

        return result

    def has_pending_turn(self) -> bool:
        """
        Check if there's a pending turn waiting for silence threshold.

        Returns:
            True if final result received but not yet emitted
        """
        return (
            self._last_final_time is not None
            and len(self._pending_transcript.strip()) > 0
        )

    def reset(self) -> None:
        """
        Reset internal state after turn emission.

        Called automatically after turn boundary detection.
        """
        self._pending_transcript = ""
        self._last_final_time = None
        self._speech_start_time = None
        self._waiting_for_final = False
        self._silence_detected_time = None
        self._pending_silence_ms = 0
        logger.debug("Turn boundary detector reset")

    def get_pending_transcript(self) -> str:
        """
        Get current pending transcript (for debugging/monitoring).

        Returns:
            Current accumulated transcript (may be empty)
        """
        return self._pending_transcript.strip()
