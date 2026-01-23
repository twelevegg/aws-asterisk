#!/usr/bin/env python3
"""
AICC Pipeline Runner.

Convenience script to run the modular pipeline.

Usage:
    python run_pipeline.py

Or run as module:
    python -m python.aicc_pipeline
"""

import sys
import os

# Add python directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python'))

if __name__ == "__main__":
    from aicc_pipeline.__main__ import main
    import asyncio
    asyncio.run(main())
