"""
Logging configuration for AICC Pipeline.

Provides structured logging with configurable levels.

Environment Variables:
    AICC_LOG_LEVEL - Log level (DEBUG, INFO, WARNING, ERROR). Default: INFO
"""

import logging
import os
import sys
from typing import Optional


def setup_logging(
    level: Optional[str] = None,
    format_string: Optional[str] = None,
    name: str = "aicc"
) -> logging.Logger:
    """
    Setup logging for AICC Pipeline.

    Args:
        level: Log level. Default from AICC_LOG_LEVEL or INFO.
        format_string: Custom format. Default: timestamp + level + name + message.
        name: Logger name.

    Returns:
        Configured logger instance.
    """
    if level is None:
        level = os.getenv("AICC_LOG_LEVEL", "INFO").upper()

    if format_string is None:
        format_string = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level, logging.INFO))

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level, logging.INFO))
    handler.setFormatter(logging.Formatter(format_string, datefmt="%Y-%m-%d %H:%M:%S"))

    logger.addHandler(handler)

    return logger


def get_logger(name: str = "aicc") -> logging.Logger:
    """
    Get or create a logger.

    Args:
        name: Logger name (prefixed with 'aicc.' if not already)

    Returns:
        Logger instance.
    """
    if not name.startswith("aicc"):
        name = f"aicc.{name}"

    logger = logging.getLogger(name)

    # Initialize if no handlers
    if not logger.handlers and not logging.getLogger("aicc").handlers:
        setup_logging()

    return logger


# Module-level logger
_logger: Optional[logging.Logger] = None


def log() -> logging.Logger:
    """Get the default AICC logger."""
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger
