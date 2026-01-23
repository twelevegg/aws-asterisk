"""Tests for pipeline module."""

import os
import sys
import pytest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))

from aicc_pipeline.core.pipeline import TurnEvent, _safe_task
from aicc_pipeline.config import PipelineConfig


class TestTurnEvent:
    """Test TurnEvent dataclass."""

    def test_metadata_start_event(self):
        """Test metadata_start event serialization."""
        event = TurnEvent(
            type="metadata_start",
            call_id="test-123",
            customer_number="+821012345678",
            agent_id="agent01"
        )

        result = event.to_dict()

        assert result["type"] == "metadata_start"
        assert result["customer_number"] == "+821012345678"
        assert result["agent_id"] == "agent01"
        assert "speaker" not in result

    def test_turn_complete_event(self):
        """Test turn_complete event serialization."""
        event = TurnEvent(
            type="turn_complete",
            call_id="test-123",
            speaker="customer",
            start_time=0.0,
            end_time=1.5,
            transcript="안녕하세요",
            decision="complete",
            fusion_score=0.85
        )

        result = event.to_dict()

        assert result["type"] == "turn_complete"
        assert result["speaker"] == "customer"
        assert result["transcript"] == "안녕하세요"
        assert result["fusion_score"] == 0.85

    def test_metadata_end_event(self):
        """Test metadata_end event serialization."""
        event = TurnEvent(
            type="metadata_end",
            call_id="test-123",
            total_duration=120.5,
            turn_count=15,
            speech_ratio=0.65,
            complete_turns=10,
            incomplete_turns=5
        )

        result = event.to_dict()

        assert result["total_duration"] == 120.5
        assert result["turn_count"] == 15
        assert result["complete_turns"] == 10

    def test_timestamp_auto_generated(self):
        """Test timestamp is auto-generated."""
        event = TurnEvent(type="test", call_id="123")

        assert event.timestamp is not None
        assert event.timestamp.endswith("Z")


class TestSafeTask:
    """Test _safe_task helper."""

    @pytest.mark.asyncio
    async def test_successful_task(self):
        """Test successful async task."""
        async def success():
            return "done"

        task = _safe_task(success(), "test_success")
        result = await task

        assert result == "done"

    @pytest.mark.asyncio
    async def test_failing_task_logged(self):
        """Test that failing task is logged, not raised."""
        async def fail():
            raise ValueError("Test error")

        task = _safe_task(fail(), "test_fail")

        # Should not raise
        await task


class TestPipelineConfig:
    """Test pipeline configuration integration."""

    def test_config_used_in_pipeline(self):
        """Test that config values are properly used."""
        config = PipelineConfig()

        # These are the defaults
        assert config.customer_port == 12345
        assert config.agent_port == 12346
        assert config.target_sample_rate == 16000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
