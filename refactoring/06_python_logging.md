# P1-6: Replace print() with logging Module

## Problem
- `print()` used throughout Python codebase
- No log level control
- No timestamps or structured logging

## Solution
1. Create `config/logging.py` with `setup_logging()` and `get_logger()`
2. Replace all `print()` calls with appropriate log levels
3. Support `AICC_LOG_LEVEL` environment variable

## New Logging Module
```python
# config/logging.py
def setup_logging(level=None, format_string=None, name="aicc"):
    # Level from AICC_LOG_LEVEL env var or INFO
    ...

def get_logger(name="aicc"):
    # Get logger with aicc. prefix
    ...
```

## Log Levels Used
| Level | Use Case |
|-------|----------|
| `DEBUG` | Detailed info (WebSocket events, etc.) |
| `INFO` | Normal operation (startup, connections) |
| `WARNING` | Recoverable issues (connection failures, retries) |
| `ERROR` | Errors requiring attention |

## Modified Files
- `config/logging.py` - New logging configuration
- `config/__init__.py` - Export logging functions
- `__main__.py` - Initialize logging
- `core/pipeline.py` - Replace prints
- `core/udp_receiver.py` - Already using logging
- `websocket/manager.py` - Replace prints
- `stt/google_stt.py` - Replace prints
- `vad/detector.py` - Replace prints
- `turn/detector.py` - Replace prints

## Usage
```bash
# Default (INFO)
python -m aicc_pipeline

# Debug mode
AICC_LOG_LEVEL=DEBUG python -m aicc_pipeline

# Warning only
AICC_LOG_LEVEL=WARNING python -m aicc_pipeline
```

## Status
- [x] Completed
