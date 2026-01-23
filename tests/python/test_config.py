"""Tests for configuration module."""

import os
import pytest
import sys

# Add python directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../python'))

from aicc_pipeline.config import PipelineConfig, get_config, reset_config


class TestPipelineConfig:
    """Test PipelineConfig class."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()
        # Clear relevant env vars
        for key in list(os.environ.keys()):
            if key.startswith('AICC_'):
                del os.environ[key]

    def test_default_values(self):
        """Test default configuration values."""
        config = PipelineConfig()

        assert config.customer_port == 12345
        assert config.agent_port == 12346
        assert config.sample_rate == 8000
        assert config.target_sample_rate == 16000
        assert config.vad_threshold == 0.5

    def test_env_var_override(self):
        """Test environment variable overrides."""
        os.environ['AICC_CUSTOMER_PORT'] = '20000'
        os.environ['AICC_AGENT_PORT'] = '20001'

        config = PipelineConfig()

        assert config.customer_port == 20000
        assert config.agent_port == 20001

    def test_ws_urls_from_env(self):
        """Test WebSocket URL collection from env vars."""
        os.environ['AICC_WS_URL'] = 'wss://main.example.com'
        os.environ['AICC_WS_URL_1'] = 'wss://backup1.example.com'
        os.environ['AICC_WS_URL_2'] = 'wss://backup2.example.com'

        config = PipelineConfig()

        assert len(config.ws_urls) == 3
        assert 'wss://main.example.com' in config.ws_urls

    def test_singleton_get_config(self):
        """Test singleton pattern of get_config."""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_reset_config(self):
        """Test config reset."""
        config1 = get_config()
        reset_config()
        config2 = get_config()

        assert config1 is not config2


class TestTurnDetectorWeights:
    """Test turn detector weight validation."""

    def setup_method(self):
        reset_config()

    def test_default_weights_sum_to_one(self):
        """Test that default weights sum to 1.0."""
        config = PipelineConfig()

        total = (
            config.turn_morpheme_weight +
            config.turn_duration_weight +
            config.turn_silence_weight
        )

        assert abs(total - 1.0) < 0.01


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
