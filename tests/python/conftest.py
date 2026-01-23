"""Pytest configuration and fixtures."""

import os
import sys

# Add python directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))


def pytest_configure(config):
    """Configure pytest."""
    # Set test environment
    os.environ['AICC_LOG_LEVEL'] = 'WARNING'
