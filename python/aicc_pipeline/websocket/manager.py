"""
WebSocket Manager.

Manages multiple WebSocket connections with:
- Queue size limits to prevent memory issues
- Automatic reconnection
- Event batching
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from websockets.legacy.client import WebSocketClientProtocol
    from .auth import WebSocketAuth

logger = logging.getLogger("aicc.websocket")

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    websockets = None  # type: ignore[assignment]
    WEBSOCKETS_AVAILABLE = False


@dataclass
class WebSocketEvent:
    """Event to send via WebSocket."""
    type: str
    call_id: str
    timestamp: str
    data: Dict[str, Any]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.type,
            "call_id": self.call_id,
            "timestamp": self.timestamp,
        }
        result.update(self.data)
        return result


class WebSocketManager:
    """
    Manage multiple WebSocket connections.

    Features:
    - Queue size limit with oldest-event-drop policy
    - Automatic reconnection on disconnect
    - Multiple endpoint support for redundancy
    """

    def __init__(
        self,
        urls: List[str],
        queue_maxsize: int = 1000,
        reconnect_interval: float = 5.0,
        ping_interval: float = 20.0,
        ping_timeout: float = 10.0,
        auth: Optional["WebSocketAuth"] = None
    ):
        """
        Initialize WebSocket manager.

        Args:
            urls: List of WebSocket URLs to connect to
            queue_maxsize: Maximum queue size (older events dropped when full)
            reconnect_interval: Seconds between reconnection attempts
            ping_interval: WebSocket ping interval
            ping_timeout: WebSocket ping timeout
            auth: Optional WebSocketAuth instance for JWT authentication
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets not available. pip install websockets")

        self.urls = [u for u in urls if u and not u.strip().startswith("#")]
        self.queue_maxsize = queue_maxsize
        self.reconnect_interval = reconnect_interval
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.auth = auth

        self._connections: Dict[str, Any] = {}  # WebSocket connections
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        self._running = False
        self._dropped_count = 0
        self._sent_count = 0
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}

    def _is_connected(self, ws: Any) -> bool:
        """Check if WebSocket is connected (compatible with different versions)."""
        try:
            # websockets >= 11.0
            from websockets.protocol import State
            return bool(ws.state == State.OPEN)
        except (ImportError, AttributeError):
            # websockets < 11.0
            return bool(getattr(ws, 'open', False))

    @property
    def connected_count(self) -> int:
        """Number of active connections."""
        return len([ws for ws in self._connections.values() if self._is_connected(ws)])

    @property
    def dropped_count(self) -> int:
        """Number of dropped events due to queue overflow."""
        return self._dropped_count

    @property
    def sent_count(self) -> int:
        """Number of successfully sent events."""
        return self._sent_count

    async def _connect_one(self, url: str) -> bool:
        """
        Connect to a single WebSocket server.

        Args:
            url: WebSocket URL

        Returns:
            True if connection successful
        """
        try:
            logger.info(f"Connecting to: {url}")

            # Get auth headers if authentication is enabled
            extra_headers = None
            if self.auth:
                extra_headers = self.auth.get_auth_headers()
                logger.debug(f"Using JWT authentication for {url}")

            # websockets >= 11.0 uses additional_headers instead of extra_headers
            connect_kwargs = {
                "ping_interval": self.ping_interval,
                "ping_timeout": self.ping_timeout,
            }
            if extra_headers:
                connect_kwargs["additional_headers"] = extra_headers

            ws = await websockets.connect(url, **connect_kwargs)
            self._connections[url] = ws
            logger.info(f"Connected: {url}")
            return True
        except Exception as e:
            logger.warning(f"Connection failed: {url} - {e}")
            return False

    async def _reconnect_loop(self, url: str):
        """
        Reconnection loop for a disconnected URL.

        Args:
            url: WebSocket URL to reconnect
        """
        while self._running and url not in self._connections:
            await asyncio.sleep(self.reconnect_interval)
            if await self._connect_one(url):
                break

    async def connect_all(self):
        """Connect to all WebSocket servers."""
        if not self.urls:
            logger.warning("No WebSocket URLs configured")
            return

        for url in self.urls:
            success = await self._connect_one(url)
            if not success:
                # Schedule reconnection
                task = asyncio.create_task(self._reconnect_loop(url))
                self._reconnect_tasks[url] = task

    async def send(self, event: Any):
        """
        Queue event for sending.

        If queue is full, drops oldest event.
        Filters out turn_complete events with empty transcripts.

        Args:
            event: Event object with to_dict() method, or dict
        """
        if hasattr(event, 'to_dict'):
            event_dict = event.to_dict()
        else:
            event_dict = event

        # Filter out turn_complete events with empty transcript
        if event_dict.get('type') == 'turn_complete':
            transcript = event_dict.get('transcript', '')
            if not transcript or not transcript.strip():
                logger.debug("Filtered out turn_complete with empty transcript")
                return

        try:
            self._queue.put_nowait(event_dict)
        except asyncio.QueueFull:
            # Drop oldest event
            try:
                dropped = self._queue.get_nowait()
                self._dropped_count += 1
                if self._dropped_count % 100 == 1:
                    logger.warning(f"Queue full, dropped {self._dropped_count} events")
                # Now put new event
                self._queue.put_nowait(event_dict)
            except asyncio.QueueEmpty:
                pass

    async def _send_loop(self):
        """Send queued events to all connections."""
        while self._running:
            try:
                event_dict = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                data = json.dumps(event_dict, ensure_ascii=False)

                dead_urls = []
                for url, ws in list(self._connections.items()):
                    try:
                        if self._is_connected(ws):
                            await ws.send(data)
                            self._sent_count += 1
                            # Log abbreviated URL
                            short_url = url.split('//')[1][:25] if '//' in url else url[:25]
                            logger.debug(f"[{short_url}] {event_dict.get('type', 'unknown')}")
                        else:
                            dead_urls.append(url)
                    except Exception as e:
                        logger.error(f"Send error ({url}): {e}")
                        dead_urls.append(url)

                # Handle dead connections
                for url in dead_urls:
                    if url in self._connections:
                        del self._connections[url]
                    # Schedule reconnection if not already running
                    if url not in self._reconnect_tasks or self._reconnect_tasks[url].done():
                        task = asyncio.create_task(self._reconnect_loop(url))
                        self._reconnect_tasks[url] = task

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Send loop error: {e}")

    async def start(self):
        """Start WebSocket manager."""
        self._running = True
        asyncio.create_task(self._send_loop())
        await self.connect_all()

    async def stop(self):
        """Stop WebSocket manager and close connections."""
        self._running = False

        # Cancel reconnect tasks
        for task in self._reconnect_tasks.values():
            task.cancel()
        self._reconnect_tasks.clear()

        # Close connections
        for url, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass

        self._connections.clear()

        logger.info(f"WebSocket manager stopped. Sent: {self._sent_count}, Dropped: {self._dropped_count}")

    def get_stats(self) -> dict:
        """Get manager statistics."""
        return {
            "connected": self.connected_count,
            "total_urls": len(self.urls),
            "queue_size": self._queue.qsize(),
            "queue_maxsize": self.queue_maxsize,
            "sent_count": self._sent_count,
            "dropped_count": self._dropped_count,
        }
