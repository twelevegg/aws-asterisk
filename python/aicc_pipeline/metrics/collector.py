"""
Prometheus Metrics Collector for AICC Pipeline.

Provides metrics for monitoring:
- Active calls and call duration
- STT processing latency
- UDP packet statistics
- WebSocket message counts
- Port pool utilization
"""

import logging
from typing import Optional

logger = logging.getLogger("aicc.metrics")

try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server, REGISTRY
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed, metrics disabled. pip install prometheus-client")


# Define metrics (only if prometheus available)
if PROMETHEUS_AVAILABLE:
    # Call metrics
    CALLS_TOTAL = Counter(
        'aicc_calls_total',
        'Total number of calls processed',
        ['status']  # 'completed', 'failed', 'dropped'
    )
    CALL_DURATION = Histogram(
        'aicc_call_duration_seconds',
        'Duration of calls in seconds',
        buckets=[10, 30, 60, 120, 300, 600, 1800, 3600]
    )
    ACTIVE_CALLS = Gauge(
        'aicc_active_calls',
        'Number of currently active calls'
    )

    # STT metrics
    STT_REQUESTS_TOTAL = Counter(
        'aicc_stt_requests_total',
        'Total STT requests',
        ['status']  # 'success', 'error'
    )
    STT_LATENCY = Histogram(
        'aicc_stt_latency_seconds',
        'STT processing latency',
        buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
    )
    STT_AUDIO_DURATION = Histogram(
        'aicc_stt_audio_duration_seconds',
        'Duration of audio sent to STT',
        buckets=[0.5, 1, 2, 5, 10, 30, 60]
    )

    # UDP metrics
    UDP_PACKETS_TOTAL = Counter(
        'aicc_udp_packets_total',
        'Total UDP packets received',
        ['speaker']  # 'customer', 'agent'
    )
    UDP_PACKETS_DROPPED = Counter(
        'aicc_udp_packets_dropped_total',
        'UDP packets dropped due to backpressure or validation'
    )
    UDP_BYTES_TOTAL = Counter(
        'aicc_udp_bytes_total',
        'Total bytes received via UDP',
        ['speaker']
    )

    # WebSocket metrics
    WS_MESSAGES_TOTAL = Counter(
        'aicc_ws_messages_total',
        'Total WebSocket messages sent',
        ['type']  # 'metadata_start', 'turn_complete', 'metadata_end'
    )
    WS_CONNECTIONS = Gauge(
        'aicc_ws_connections',
        'Number of active WebSocket connections'
    )
    WS_SEND_LATENCY = Histogram(
        'aicc_ws_send_latency_seconds',
        'WebSocket message send latency',
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
    )

    # Port pool metrics
    PORT_POOL_AVAILABLE = Gauge(
        'aicc_port_pool_available',
        'Number of available port pairs in the pool'
    )
    PORT_POOL_ALLOCATED = Gauge(
        'aicc_port_pool_allocated',
        'Number of allocated port pairs'
    )

    # Task registry metrics
    TASKS_ACTIVE = Gauge(
        'aicc_tasks_active',
        'Number of active background tasks'
    )
    TASKS_FAILED_TOTAL = Counter(
        'aicc_tasks_failed_total',
        'Total number of failed tasks'
    )


class MetricsCollector:
    """
    Centralized metrics collector for AICC Pipeline.

    Provides convenient methods for recording metrics
    and starts the Prometheus HTTP server.
    """

    def __init__(self, port: int = 9090, host: str = "0.0.0.0"):
        """
        Initialize metrics collector.

        Args:
            port: Port for Prometheus HTTP server
            host: Host to bind to
        """
        self.port = port
        self.host = host
        self._started = False

    def start(self) -> bool:
        """
        Start the Prometheus HTTP server.

        Returns:
            True if started successfully, False if prometheus not available
        """
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus not available, metrics server not started")
            return False

        if self._started:
            return True

        try:
            start_http_server(self.port, addr=self.host)
            self._started = True
            logger.info(f"Prometheus metrics server started on {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            return False

    # Call metrics
    def call_started(self) -> None:
        """Record a call start."""
        if PROMETHEUS_AVAILABLE:
            ACTIVE_CALLS.inc()

    def call_ended(self, duration: float, status: str = "completed") -> None:
        """Record a call end."""
        if PROMETHEUS_AVAILABLE:
            ACTIVE_CALLS.dec()
            CALLS_TOTAL.labels(status=status).inc()
            CALL_DURATION.observe(duration)

    # STT metrics
    def stt_request(self, latency: float, audio_duration: float, success: bool = True) -> None:
        """Record an STT request."""
        if PROMETHEUS_AVAILABLE:
            status = "success" if success else "error"
            STT_REQUESTS_TOTAL.labels(status=status).inc()
            STT_LATENCY.observe(latency)
            STT_AUDIO_DURATION.observe(audio_duration)

    # UDP metrics
    def udp_packet_received(self, speaker: str, bytes_count: int) -> None:
        """Record a UDP packet received."""
        if PROMETHEUS_AVAILABLE:
            UDP_PACKETS_TOTAL.labels(speaker=speaker).inc()
            UDP_BYTES_TOTAL.labels(speaker=speaker).inc(bytes_count)

    def udp_packet_dropped(self) -> None:
        """Record a dropped UDP packet."""
        if PROMETHEUS_AVAILABLE:
            UDP_PACKETS_DROPPED.inc()

    # WebSocket metrics
    def ws_message_sent(self, message_type: str, latency: float) -> None:
        """Record a WebSocket message sent."""
        if PROMETHEUS_AVAILABLE:
            WS_MESSAGES_TOTAL.labels(type=message_type).inc()
            WS_SEND_LATENCY.observe(latency)

    def ws_connection_change(self, delta: int) -> None:
        """Record WebSocket connection change (+1 or -1)."""
        if PROMETHEUS_AVAILABLE:
            WS_CONNECTIONS.inc(delta)

    # Port pool metrics
    def update_port_pool(self, available: int, allocated: int) -> None:
        """Update port pool metrics."""
        if PROMETHEUS_AVAILABLE:
            PORT_POOL_AVAILABLE.set(available)
            PORT_POOL_ALLOCATED.set(allocated)

    # Task metrics
    def update_tasks(self, active: int, failed_delta: int = 0) -> None:
        """Update task metrics."""
        if PROMETHEUS_AVAILABLE:
            TASKS_ACTIVE.set(active)
            if failed_delta > 0:
                TASKS_FAILED_TOTAL.inc(failed_delta)

    @property
    def is_available(self) -> bool:
        """Check if Prometheus is available."""
        return PROMETHEUS_AVAILABLE


# Global instance
_metrics: Optional[MetricsCollector] = None


def get_metrics() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
