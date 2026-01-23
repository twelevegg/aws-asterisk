# P1-4: Extract app.js Settings to Environment Variables

## Problem
- All settings hardcoded in `app.js:10-16`
- Required code changes for different environments

## Solution
Replace hardcoded values with `process.env` lookups with defaults:

```javascript
// Before
const ARI_URL = 'http://127.0.0.1:8088/ari';
const CUSTOMER_PORT = '12345';

// After
const ARI_URL = process.env.ARI_URL || 'http://127.0.0.1:8088/ari';
const CUSTOMER_PORT = process.env.CUSTOMER_PORT || '12345';
```

## Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `ARI_URL` | `http://127.0.0.1:8088/ari` | ARI endpoint |
| `ARI_USERNAME` | `asterisk` | ARI username |
| `ARI_PASSWORD` | `asterisk` | ARI password |
| `EXTERNAL_HOST` | `127.0.0.1` | External media host |
| `CUSTOMER_PORT` | `12345` | Customer audio UDP port |
| `AGENT_PORT` | `12346` | Agent audio UDP port |
| `APP_NAME` | `linphone-handler` | Stasis app name |

## Usage
```bash
# Use defaults
node app.js

# Override specific settings
CUSTOMER_PORT=20000 AGENT_PORT=20001 node app.js

# Full custom config
ARI_URL=http://asterisk.local:8088/ari \
EXTERNAL_HOST=192.168.1.100 \
node app.js
```

## Status
- [x] Completed
