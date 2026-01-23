"""Tests for WebSocket manager module."""

import os
import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))

from aicc_pipeline.websocket.manager import WebSocketManager, WebSocketEvent


class TestWebSocketEvent:
    """Test WebSocketEvent dataclass."""

    def test_to_dict_basic(self):
        """Test basic event serialization."""
        event = WebSocketEvent(
            type="test",
            call_id="123",
            timestamp="2024-01-24T00:00:00Z",
            data={"key": "value"}
        )
        result = event.to_dict()

        assert result["type"] == "test"
        assert result["call_id"] == "123"
        assert result["key"] == "value"

    def test_to_dict_empty_data(self):
        """Test event with empty data."""
        event = WebSocketEvent(
            type="ping",
            call_id="456",
            timestamp="2024-01-24T00:00:00Z",
            data={}
        )
        result = event.to_dict()

        assert len(result) == 3


class TestWebSocketManager:
    """Test WebSocketManager class."""

    def test_init_with_urls(self):
        """Test initialization with URLs."""
        manager = WebSocketManager(
            urls=["wss://test1.com", "wss://test2.com"],
            queue_maxsize=100
        )

        assert len(manager.urls) == 2
        assert manager.queue_maxsize == 100

    def test_init_filters_comments(self):
        """Test that commented URLs are filtered."""
        manager = WebSocketManager(
            urls=["wss://valid.com", "# wss://commented.com", ""],
        )

        assert len(manager.urls) == 1
        assert manager.urls[0] == "wss://valid.com"

    def test_init_empty_urls(self):
        """Test initialization with empty URLs."""
        manager = WebSocketManager(urls=[])
        assert len(manager.urls) == 0

    @pytest.mark.asyncio
    async def test_send_queues_event(self):
        """Test that send() queues events."""
        manager = WebSocketManager(urls=["wss://test.com"])

        event = WebSocketEvent(
            type="test",
            call_id="123",
            timestamp="now",
            data={}
        )

        await manager.send(event)

        assert manager._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_queue_overflow_drops_oldest(self):
        """Test queue overflow behavior."""
        manager = WebSocketManager(
            urls=["wss://test.com"],
            queue_maxsize=2
        )

        # Fill queue
        for i in range(3):
            await manager.send({"type": f"event_{i}"})

        # Should have dropped first event
        assert manager._queue.qsize() == 2
        assert manager.dropped_count == 1

    def test_stats(self):
        """Test get_stats() method."""
        manager = WebSocketManager(
            urls=["wss://test.com"],
            queue_maxsize=500
        )

        stats = manager.get_stats()

        assert stats["total_urls"] == 1
        assert stats["queue_maxsize"] == 500
        assert stats["sent_count"] == 0


class TestWebSocketManagerConnection:
    """Test WebSocket connection handling."""

    @pytest.mark.asyncio
    async def test_connect_failure_logged(self):
        """Test that connection failures are logged."""
        manager = WebSocketManager(urls=["wss://invalid.test"])

        with patch('aicc_pipeline.websocket.manager.websockets') as mock_ws:
            mock_ws.connect = AsyncMock(side_effect=Exception("Connection refused"))

            result = await manager._connect_one("wss://invalid.test")

            assert result is False

    @pytest.mark.asyncio
    async def test_stop_clears_connections(self):
        """Test that stop() clears all connections."""
        manager = WebSocketManager(urls=["wss://test.com"])
        manager._running = True

        await manager.stop()

        assert manager._running is False
        assert len(manager._connections) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
