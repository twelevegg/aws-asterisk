"""
Turn Detector with Weighted Fusion.

Improved turn detection using weighted combination of:
- Morpheme analysis (ending patterns)
- Duration scoring
- Silence duration
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .morpheme import KoreanMorphemeAnalyzer

logger = logging.getLogger("aicc.turn")


class TurnDecision(Enum):
    """Turn decision types."""
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass
class TurnResult:
    """Turn detection result."""
    decision: TurnDecision
    fusion_score: float
    morpheme_score: float
    duration_score: float
    silence_score: float
    transcript: str
    duration: float


class TurnDetector:
    """
    Turn detector with weighted fusion scoring.

    Replaces simple OR condition (score >= 0.7 OR duration > 2s) with
    weighted combination for more nuanced detection.
    """

    def __init__(
        self,
        morpheme_weight: float = 0.6,
        duration_weight: float = 0.2,
        silence_weight: float = 0.2,
        complete_threshold: float = 0.65
    ):
        """
        Initialize turn detector.

        Args:
            morpheme_weight: Weight for morpheme analysis (0-1)
            duration_weight: Weight for duration scoring (0-1)
            silence_weight: Weight for silence scoring (0-1)
            complete_threshold: Threshold for complete turn decision
        """
        self.morpheme_weight = morpheme_weight
        self.duration_weight = duration_weight
        self.silence_weight = silence_weight
        self.complete_threshold = complete_threshold

        self._morpheme_analyzer = KoreanMorphemeAnalyzer()

        # Validate weights
        total = morpheme_weight + duration_weight + silence_weight
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Turn detector weights sum to {total}, not 1.0")

    def _compute_duration_score(self, duration: float) -> float:
        """
        Compute duration-based score.

        Logic:
        - < 0.5s: 0.3 (too short, likely incomplete)
        - 0.5-2s: 0.7 (typical complete utterance)
        - 2-5s: 0.5 (neutral, could go either way)
        - > 5s: 0.4 (long utterance often incomplete mid-sentence)

        Args:
            duration: Speech duration in seconds

        Returns:
            Duration score (0-1)
        """
        if duration < 0.5:
            return 0.3
        elif duration < 2.0:
            # Linear interpolation from 0.5 to 0.7
            return 0.5 + (duration - 0.5) * (0.2 / 1.5)
        elif duration < 5.0:
            # Linear interpolation from 0.7 to 0.5
            return 0.7 - (duration - 2.0) * (0.2 / 3.0)
        else:
            return 0.4

    def _compute_silence_score(self, silence_duration_ms: float) -> float:
        """
        Compute silence-based score.

        Longer silence after speech suggests turn completion.

        Args:
            silence_duration_ms: Silence duration in milliseconds

        Returns:
            Silence score (0-1)
        """
        if silence_duration_ms < 200:
            return 0.3
        elif silence_duration_ms < 400:
            return 0.5
        elif silence_duration_ms < 800:
            return 0.7
        else:
            return 0.85

    def detect(
        self,
        transcript: str,
        duration: float,
        silence_duration_ms: float = 400.0
    ) -> TurnResult:
        """
        Detect turn completeness using weighted fusion.

        Args:
            transcript: Transcribed text
            duration: Speech duration in seconds
            silence_duration_ms: Post-speech silence in milliseconds

        Returns:
            TurnResult with decision and scores
        """
        # Get individual scores
        morpheme_score = self._morpheme_analyzer.analyze(transcript)
        duration_score = self._compute_duration_score(duration)
        silence_score = self._compute_silence_score(silence_duration_ms)

        # Compute fusion score
        fusion_score = (
            self.morpheme_weight * morpheme_score +
            self.duration_weight * duration_score +
            self.silence_weight * silence_score
        )

        # Special case: Long duration with connecting ending
        # Even if > 5 seconds, if ends with connecting ending -> incomplete
        if duration > 5.0 and morpheme_score < 0.4:
            decision = TurnDecision.INCOMPLETE
        else:
            decision = (
                TurnDecision.COMPLETE
                if fusion_score >= self.complete_threshold
                else TurnDecision.INCOMPLETE
            )

        return TurnResult(
            decision=decision,
            fusion_score=round(fusion_score, 3),
            morpheme_score=round(morpheme_score, 3),
            duration_score=round(duration_score, 3),
            silence_score=round(silence_score, 3),
            transcript=transcript,
            duration=round(duration, 3)
        )
