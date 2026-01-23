# P2-8: Configuration Consolidation

## Problem
- Multiple `.env.example` files (root and python/aicc_pipeline/)
- Different variable naming conventions
- Confusion about which file to edit

## Solution
1. Merge all configurations into single root `.env.example`
2. Remove `python/aicc_pipeline/.env.example`
3. Organize by component with clear sections

## Unified Configuration Structure

```
.env.example
├── Asterisk / Linphone Configuration
│   ├── LINPHONE_PASSWORD
│   ├── ARI_URL, ARI_USERNAME, ARI_PASSWORD
│   ├── EXTERNAL_HOST, CUSTOMER_PORT, AGENT_PORT
│   └── APP_NAME
│
└── AICC Pipeline Configuration
    ├── WebSocket: AICC_WS_URL, AICC_WS_URL_1, ...
    ├── UDP: AICC_CUSTOMER_PORT, AICC_AGENT_PORT
    ├── VAD: AICC_VAD_THRESHOLD, AICC_MIN_SPEECH_MS, ...
    ├── STT: AICC_STT_LANGUAGE, GOOGLE_APPLICATION_CREDENTIALS
    ├── Turn: AICC_TURN_*_WEIGHT, AICC_TURN_COMPLETE_THRESHOLD
    └── Logging: AICC_LOG_LEVEL, AICC_DEBUG
```

## Usage
```bash
# Copy and edit
cp .env.example .env
vim .env

# Load and run
source .env
node app.js &
python run_pipeline.py
```

## Important Notes
- `CUSTOMER_PORT` and `AICC_CUSTOMER_PORT` should match
- `AGENT_PORT` and `AICC_AGENT_PORT` should match

## Status
- [x] Completed
