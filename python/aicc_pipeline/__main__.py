"""
AICC Pipeline entry point.

Usage:
    python -m aicc_pipeline

Environment Variables:
    AICC_WS_URL - WebSocket endpoint URL
    AICC_CUSTOMER_PORT - Customer audio UDP port (default: 12345)
    AICC_AGENT_PORT - Agent audio UDP port (default: 12346)
    GOOGLE_APPLICATION_CREDENTIALS - GCP credentials path
    AICC_LOG_LEVEL - Log level (DEBUG, INFO, WARNING, ERROR)
"""

import asyncio
import signal
import sys

from .config import get_config, setup_logging
from .core import AICCPipeline

# Initialize logging
logger = setup_logging()


async def main():
    """Main entry point."""
    config = get_config()

    # Validate configuration
    if not config.ws_urls:
        logger.error("No WebSocket URL configured.")
        logger.error("Set AICC_WS_URL environment variable.")
        logger.error("Example: export AICC_WS_URL='wss://your-server.com/api/v1/agent/check'")
        sys.exit(1)

    pipeline = AICCPipeline(config)

    # Handle shutdown signals
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown requested...")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: signal_handler())

    # Start pipeline
    try:
        # Run pipeline in background
        pipeline_task = asyncio.create_task(pipeline.start())

        # Wait for shutdown signal
        await shutdown_event.wait()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await pipeline.stop()


if __name__ == "__main__":
    asyncio.run(main())
