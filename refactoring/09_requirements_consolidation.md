# P2-9: Consolidate requirements.txt

## Problem
- Duplicate `requirements.txt` files in root and `python/aicc_pipeline/`
- Different version specifications between files
- Confusion about which to update

## Solution
1. Keep only root `requirements.txt`
2. Use latest stable versions
3. Remove `python/aicc_pipeline/requirements.txt`

## Final Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| numpy | >=1.24.0 | Audio array processing |
| websockets | >=12.0 | WebSocket client |
| kiwipiepy | >=0.16.0 | Korean morpheme analysis |
| google-cloud-speech | >=2.21.0 | Speech-to-Text |
| pydub | >=0.25.1 | Audio format conversion |
| pipecat-ai[silero] | >=0.0.40 | Optional: Silero VAD |

## Installation
```bash
# From project root
pip install -r requirements.txt

# Optional: Install Silero VAD
pip install pipecat-ai[silero]>=0.0.40
```

## Status
- [x] Completed
