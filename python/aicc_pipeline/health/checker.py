"""
Health Check HTTP Server.

Provides endpoints for liveness and readiness probes:
- /health/live - Returns 200 if process is running
- /health/ready - Returns 200 only when all components are healthy
- /health - Alias for /health/ready with detailed component status
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("aicc.health")

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None  # type: ignore


class HealthChecker:
    """
    Health check server for pipeline components.

    Provides HTTP endpoints for Kubernetes/ALB health probes.
    """

    def __init__(
        self,
        port: int = 8080,
        host: str = "0.0.0.0",
    ):
        """
        Initialize health checker.

        Args:
            port: HTTP port to listen on
            host: Host to bind to
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp is required for health checks. pip install aiohttp")

        self.port = port
        self.host = host
        self._checks: Dict[str, Callable[[], bool]] = {}
        self._async_checks: Dict[str, Callable[[], Any]] = {}
        self._runner: Optional[web.AppRunner] = None
        self._started = False

    def register_check(self, name: str, check_fn: Callable[[], bool]) -> None:
        """
        Register a synchronous health check.

        Args:
            name: Component name
            check_fn: Function that returns True if healthy
        """
        self._checks[name] = check_fn

    def register_async_check(self, name: str, check_fn: Callable[[], Any]) -> None:
        """
        Register an async health check.

        Args:
            name: Component name
            check_fn: Async function that returns True if healthy
        """
        self._async_checks[name] = check_fn

    async def _check_all_components(self) -> Dict[str, bool]:
        """Run all health checks and return results."""
        results = {}

        # Run sync checks
        for name, check_fn in self._checks.items():
            try:
                results[name] = bool(check_fn())
            except Exception as e:
                logger.warning(f"Health check '{name}' failed: {e}")
                results[name] = False

        # Run async checks
        for name, check_fn in self._async_checks.items():
            try:
                result = await check_fn()
                results[name] = bool(result)
            except Exception as e:
                logger.warning(f"Async health check '{name}' failed: {e}")
                results[name] = False

        return results

    async def _live_handler(self, request: web.Request) -> web.Response:
        """Liveness probe - just returns OK if process is running."""
        return web.Response(text="OK", status=200)

    async def _ready_handler(self, request: web.Request) -> web.Response:
        """Readiness probe - returns OK only if all components are healthy."""
        results = await self._check_all_components()
        all_healthy = all(results.values()) if results else True

        status = 200 if all_healthy else 503
        return web.json_response(
            {
                "status": "healthy" if all_healthy else "unhealthy",
                "components": results,
            },
            status=status,
        )

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Detailed health check with component status."""
        return await self._ready_handler(request)

    async def start(self) -> None:
        """Start the health check HTTP server."""
        if self._started:
            return

        app = web.Application()
        app.router.add_get("/health", self._health_handler)
        app.router.add_get("/health/live", self._live_handler)
        app.router.add_get("/health/ready", self._ready_handler)

        self._runner = web.AppRunner(app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        self._started = True
        logger.info(f"Health check server started on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the health check server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._started = False
        logger.info("Health check server stopped")
