# P2-11: Add Test Suite

## Problem
- No automated tests
- Regressions not caught early
- Difficult to refactor safely

## Solution
1. Add pytest for Python tests
2. Create test structure under `tests/`
3. Add configuration in `pytest.ini`

## Test Structure
```
tests/
├── python/
│   ├── conftest.py        # Pytest configuration
│   ├── test_config.py     # Configuration tests
│   ├── test_audio.py      # RTP/Audio converter tests
│   └── test_turn.py       # Turn detection tests
└── node/
    └── (future Jest tests)
```

## Test Coverage

### test_config.py
- Default configuration values
- Environment variable overrides
- WebSocket URL collection
- Singleton pattern
- Config reset

### test_audio.py
- RTP packet parsing (valid, too small, marker bit)
- u-law to PCM conversion
- 8kHz to 16kHz resampling
- Full conversion pipeline

### test_turn.py
- Korean morpheme analysis (formal, informal, questions)
- Continuing endings detection
- Complete turn detection
- Duration/silence scoring
- Weight application

## Running Tests
```bash
# Install pytest
pip install pytest

# Run all tests
pytest

# Run with coverage
pip install pytest-cov
pytest --cov=python/aicc_pipeline

# Run specific test file
pytest tests/python/test_turn.py

# Run specific test
pytest tests/python/test_turn.py::TestTurnDetector::test_complete_turn
```

## Adding New Tests
1. Create `test_<module>.py` in `tests/python/`
2. Use `Test*` class naming convention
3. Use `test_*` function naming convention
4. Import modules via conftest.py path setup

## Status
- [x] Completed
