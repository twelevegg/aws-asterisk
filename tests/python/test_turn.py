"""Tests for turn detection module."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))

from aicc_pipeline.turn import TurnDetector, TurnDecision
from aicc_pipeline.turn.morpheme import KoreanMorphemeAnalyzer


class TestKoreanMorphemeAnalyzer:
    """Test Korean morpheme analysis."""

    def setup_method(self):
        self.analyzer = KoreanMorphemeAnalyzer()

    def test_complete_ending_formal(self):
        """Test formal complete endings."""
        score = self.analyzer.analyze("감사합니다")
        assert score >= 0.9

    def test_complete_ending_informal(self):
        """Test informal complete endings."""
        score = self.analyzer.analyze("알겠어요")
        assert score >= 0.7

    def test_question_ending(self):
        """Test question endings."""
        score = self.analyzer.analyze("뭐 드릴까요")
        assert score >= 0.9

    def test_continuing_ending(self):
        """Test continuing/connecting endings."""
        score = self.analyzer.analyze("그래서")
        assert score < 0.5

    def test_short_affirmative(self):
        """Test short affirmative responses."""
        score = self.analyzer.analyze("네")
        assert score >= 0.9

    def test_empty_text(self):
        """Test empty text."""
        score = self.analyzer.analyze("")
        assert score == 0.5


class TestTurnDetector:
    """Test turn detector."""

    def setup_method(self):
        self.detector = TurnDetector()

    def test_complete_turn(self):
        """Test detecting complete turn."""
        result = self.detector.detect(
            transcript="네, 감사합니다",
            duration=1.5,
            silence_duration_ms=500
        )

        assert result.decision == TurnDecision.COMPLETE
        assert result.fusion_score > 0.6

    def test_incomplete_turn_connecting(self):
        """Test detecting incomplete turn with connecting ending."""
        result = self.detector.detect(
            transcript="그래서",
            duration=0.5,
            silence_duration_ms=300
        )

        assert result.decision == TurnDecision.INCOMPLETE

    def test_duration_scoring(self):
        """Test duration score calculation."""
        # Short duration should have lower score
        result_short = self.detector.detect("", 0.3, 400)
        result_medium = self.detector.detect("", 1.5, 400)

        assert result_short.duration_score < result_medium.duration_score

    def test_silence_scoring(self):
        """Test silence score calculation."""
        # Longer silence suggests turn completion
        result_short_silence = self.detector.detect("", 1.0, 200)
        result_long_silence = self.detector.detect("", 1.0, 800)

        assert result_short_silence.silence_score < result_long_silence.silence_score

    def test_weights_applied(self):
        """Test that weights are applied correctly."""
        detector = TurnDetector(
            morpheme_weight=1.0,
            duration_weight=0.0,
            silence_weight=0.0
        )

        result = detector.detect("감사합니다", 0.3, 100)

        # With only morpheme weight, score should equal morpheme score
        assert abs(result.fusion_score - result.morpheme_score) < 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
