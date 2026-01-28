"""
Call Metadata REST API.

Provides endpoints for Node.js to register calls and receive port assignments.
"""

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("aicc.api")

try:
    from aiohttp import web
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None

if TYPE_CHECKING:
    from ..core.pipeline import AICCPipeline


class CallMetadataAPI:
    """
    REST API for call metadata synchronization.

    Node.js calls this API to:
    1. Register a new call and get assigned UDP ports
    2. End a call and release resources
    """

    def __init__(self, pipeline: "AICCPipeline", port: int = 8081, host: str = "127.0.0.1"):
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp required for API. pip install aiohttp")

        self.pipeline = pipeline
        self.port = port
        self.host = host
        self._runner = None
        self._started = False

    async def register_call(self, request: web.Request) -> web.Response:
        """
        Register a new call with metadata.

        POST /api/calls
        Body: {"call_id": "...", "customer_number": "...", "agent_id": "..."}

        Returns: {"status": "registered", "customer_port": 20000, "agent_port": 20001}
        """
        try:
            data = await request.json()
            call_id = data.get('call_id')

            if not call_id:
                return web.json_response(
                    {"error": "call_id is required"},
                    status=400
                )

            # Check if call already exists
            if hasattr(self.pipeline, '_sessions') and call_id in self.pipeline._sessions:
                session = self.pipeline._sessions[call_id]
                return web.json_response({
                    "status": "already_registered",
                    "customer_port": session.customer_port,
                    "agent_port": session.agent_port
                })

            # Allocate ports from pool
            customer_port, agent_port = self.pipeline._port_pool.allocate(call_id)

            # Import here to avoid circular imports
            from ..core.call_session import CallSession

            # Create session with metadata
            session = CallSession(
                call_id=call_id,
                customer_port=customer_port,
                agent_port=agent_port,
                customer_number=data.get('customer_number'),
                agent_id=data.get('agent_id'),
            )

            # Store session
            if not hasattr(self.pipeline, '_sessions'):
                self.pipeline._sessions = {}
            self.pipeline._sessions[call_id] = session

            logger.info(f"Call registered: {call_id} -> ports {customer_port}/{agent_port}")

            return web.json_response({
                "status": "registered",
                "call_id": call_id,
                "customer_port": customer_port,
                "agent_port": agent_port
            })

        except ValueError as e:
            # Port pool exhausted
            logger.error(f"Failed to register call: {e}")
            return web.json_response(
                {"error": str(e)},
                status=503
            )
        except Exception as e:
            logger.error(f"Error registering call: {e}")
            return web.json_response(
                {"error": "Internal server error"},
                status=500
            )

    async def end_call(self, request: web.Request) -> web.Response:
        """
        End a call and release resources.

        DELETE /api/calls/{call_id}

        Returns: {"status": "ended"}
        """
        call_id = request.match_info.get('call_id')

        if not call_id:
            return web.json_response(
                {"error": "call_id is required"},
                status=400
            )

        try:
            # Release ports
            self.pipeline._port_pool.release(call_id)

            # Remove session
            if hasattr(self.pipeline, '_sessions'):
                self.pipeline._sessions.pop(call_id, None)

            logger.info(f"Call ended: {call_id}")

            return web.json_response({
                "status": "ended",
                "call_id": call_id
            })

        except Exception as e:
            logger.error(f"Error ending call: {e}")
            return web.json_response(
                {"error": "Internal server error"},
                status=500
            )

    async def get_call(self, request: web.Request) -> web.Response:
        """
        Get call info.

        GET /api/calls/{call_id}
        """
        call_id = request.match_info.get('call_id')

        if not hasattr(self.pipeline, '_sessions') or call_id not in self.pipeline._sessions:
            return web.json_response(
                {"error": "Call not found"},
                status=404
            )

        session = self.pipeline._sessions[call_id]
        return web.json_response({
            "call_id": session.call_id,
            "customer_port": session.customer_port,
            "agent_port": session.agent_port,
            "customer_number": session.customer_number,
            "agent_id": session.agent_id,
            "start_time": session.start_time.isoformat()
        })

    async def list_calls(self, request: web.Request) -> web.Response:
        """
        List all active calls.

        GET /api/calls
        """
        if not hasattr(self.pipeline, '_sessions'):
            return web.json_response({"calls": [], "count": 0})

        calls = [
            {
                "call_id": s.call_id,
                "customer_port": s.customer_port,
                "agent_port": s.agent_port,
            }
            for s in self.pipeline._sessions.values()
        ]

        return web.json_response({
            "calls": calls,
            "count": len(calls)
        })

    async def start(self) -> None:
        """Start the API server."""
        if self._started:
            return

        app = web.Application()
        app.router.add_post('/api/calls', self.register_call)
        app.router.add_get('/api/calls', self.list_calls)
        app.router.add_get('/api/calls/{call_id}', self.get_call)
        app.router.add_delete('/api/calls/{call_id}', self.end_call)

        self._runner = web.AppRunner(app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

        self._started = True
        logger.info(f"Call Metadata API started on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the API server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._started = False
        logger.info("Call Metadata API stopped")
