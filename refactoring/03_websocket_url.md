# P0-3: Remove Hardcoded WebSocket URLs

## Problem
- Legacy `aicc_pipeline.py` had hardcoded ngrok URLs
- URLs change frequently, requiring code changes for each deployment

## Solution
The modular version (`python/aicc_pipeline/`) already uses environment variables:

```python
# config/settings.py
ws_urls: List[str] = field(default_factory=_get_ws_urls_from_env)

def _get_ws_urls_from_env() -> List[str]:
    urls = []
    main_url = os.getenv("AICC_WS_URL")
    if main_url:
        urls.append(main_url)
    # Additional URLs: AICC_WS_URL_1, AICC_WS_URL_2, ...
    ...
```

## Environment Variables
```bash
# Primary WebSocket URL (required)
export AICC_WS_URL="wss://your-server.com/api/v1/agent/check"

# Additional URLs (optional, for redundancy)
export AICC_WS_URL_1="wss://backup-server.com/api/v1/agent/check"
```

## Files with Hardcoded URLs (Legacy Only)
- `aicc_pipeline_legacy.py:91,796` - ngrok URL (legacy, not used)
- `.env.example` - Example URLs (expected)
- `test01.changelog.md` - Documentation (expected)

## Status
- [x] Completed - Modular version uses env vars exclusively
