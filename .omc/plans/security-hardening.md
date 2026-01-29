# Security Hardening Plan - AWS Asterisk

## Context

### Original Request
Comprehensive security hardening for AWS Asterisk AICC pipeline based on security review findings.

### Scope
- **6 CRITICAL vulnerabilities** requiring immediate remediation
- **6 HIGH vulnerabilities** requiring attention within 1 week
- Preserve existing security measures (AWS Secrets Manager, IP whitelisting, etc.)

### Research Findings

**Current Security Posture (Positive):**
- AWS Secrets Manager used for DB password
- IP whitelisting in pjsip.conf (/32 ranges for sip.linphone.org)
- ARI bound to localhost (127.0.0.1:8088)
- .env files properly in .gitignore
- Terraform uses random_password for RDS
- pjsip.conf restricted to 640 permissions

**Identified Vulnerabilities:**

| Severity | Count | Category |
|----------|-------|----------|
| CRITICAL | 6 | Hardcoded secrets, npm vulns, command injection |
| HIGH | 6 | Anonymous SIP, CORS, debug mode, RDS protection |
| MEDIUM | 4 | Logging, encryption, backup |

---

## Work Objectives

### Core Objective
Remediate all CRITICAL and HIGH security vulnerabilities while maintaining system functionality.

### Deliverables
1. Secrets externalized from source code
2. npm dependencies updated/replaced
3. Command injection vulnerabilities fixed
4. SIP/media encryption enabled
5. Infrastructure hardening (RDS, CORS, debug)

### Definition of Done
- [ ] Zero hardcoded passwords in source code
- [ ] npm audit shows 0 CRITICAL/HIGH vulnerabilities
- [ ] All sed commands use safe substitution methods
- [ ] SRTP enabled for media encryption
- [ ] RDS deletion protection enabled
- [ ] Anonymous SIP endpoint removed or restricted

---

## Guardrails

### Must Have
- Backward compatibility with existing Linphone integration
- Zero downtime deployment strategy
- Rollback plan for each change
- Testing on staging before production

### Must NOT Have
- Breaking changes to ARI API
- Removal of agent01-06 functionality
- Changes to port assignments (12345/12346)
- Modifications to WebSocket message format

---

## Task Flow and Dependencies

```
PHASE 1: IMMEDIATE (P0) - Days 1-3
  [T1] Remove hardcoded passwords ──────────┐
  [T2] Fix command injection ───────────────┼── Can run in parallel
  [T3] Update npm dependencies ─────────────┘
                                            │
                                            v
PHASE 2: HIGH PRIORITY (P1) - Days 4-7
  [T4] Restrict anonymous SIP ──────────────┐
  [T5] Fix CORS configuration ──────────────┼── Can run in parallel
  [T6] Disable debug mode (prod) ───────────┤
  [T7] Enable RDS deletion protection ──────┘
                                            │
                                            v
PHASE 3: MEDIUM PRIORITY (P2) - Days 8-14
  [T8] Enable SRTP media encryption ────────┐
  [T9] Redact sensitive logging ────────────┼── Can run in parallel
  [T10] Add TLS transport option ───────────┘
```

---

## Detailed Tasks

### PHASE 1: IMMEDIATE (P0) - Critical Vulnerabilities

---

#### T1: Remove Hardcoded Passwords

**Priority:** P0 - CRITICAL
**Effort:** 4 hours
**Risk:** HIGH (secrets in version control)

**Files to Modify:**

| File | Line | Current | Target |
|------|------|---------|--------|
| `config/ari.conf` | 20 | `password=asterisk_dev_only` | Load from Asterisk secrets file |
| `stasis_app/stasis-app.service` | 17 | `ARI_PASSWORD=asterisk_dev_only` | Use EnvironmentFile directive |
| `stasis_app/app.js` | 19 | Fallback `'asterisk_dev_only'` | Remove fallback, require env var |
| `sql/seed_agents.sql` | 27-32 | `CHANGE_ME_agent0X_dev` | Use placeholder + migration script |

**Implementation:**

**Step 1: Create secrets directory and script**

```bash
# On EC2, create directories:
sudo mkdir -p /etc/asterisk/secrets
sudo chmod 700 /etc/asterisk/secrets
sudo chown asterisk:asterisk /etc/asterisk/secrets
```

**Step 2: Create `/etc/asterisk/secrets/get_ari_password.sh`:**

```bash
#!/bin/bash
# /etc/asterisk/secrets/get_ari_password.sh
# Retrieves ARI password from AWS Secrets Manager or local file

# Try AWS Secrets Manager first
if command -v aws &> /dev/null; then
    SECRET_JSON=$(aws secretsmanager get-secret-value \
        --secret-id asterisk/ari/credentials \
        --query SecretString \
        --output text 2>/dev/null)

    if [ -n "$SECRET_JSON" ]; then
        PASSWORD=$(echo "$SECRET_JSON" | jq -r '.password // empty')
        if [ -n "$PASSWORD" ]; then
            echo "password=$PASSWORD"
            exit 0
        fi
    fi
fi

# Fallback to local file
if [ -f /etc/asterisk/secrets/ari.secret ]; then
    cat /etc/asterisk/secrets/ari.secret
    exit 0
fi

# Critical error - no password source
echo "; ERROR: No ARI password source found!" >&2
exit 1
```

```bash
# Set permissions
sudo chmod 750 /etc/asterisk/secrets/get_ari_password.sh
sudo chown asterisk:asterisk /etc/asterisk/secrets/get_ari_password.sh
```

**Step 3: Create `/etc/asterisk/secrets/ari.secret` (local fallback):**

```ini
password=YOUR_SECURE_PASSWORD_HERE
```

```bash
sudo chmod 600 /etc/asterisk/secrets/ari.secret
sudo chown asterisk:asterisk /etc/asterisk/secrets/ari.secret
```

**Step 4: Create `/etc/stasis-app/secrets.env`:**

```bash
# Create directory
sudo mkdir -p /etc/stasis-app
sudo chmod 700 /etc/stasis-app

# Create secrets file
sudo tee /etc/stasis-app/secrets.env > /dev/null << 'EOF'
# Stasis App Secrets
# Loaded via EnvironmentFile in systemd service
ARI_PASSWORD=YOUR_SECURE_PASSWORD_HERE
EOF

sudo chmod 600 /etc/stasis-app/secrets.env
```

**Step 5: Update ari.conf:**

```ini
; config/ari.conf:20
; Before: password=asterisk_dev_only
; After: Use #exec to load from script
#exec /etc/asterisk/secrets/get_ari_password.sh
```

**Step 6: Update stasis-app.service:**

```ini
; stasis_app/stasis-app.service
; Add after line 12:
EnvironmentFile=/etc/stasis-app/secrets.env

; Remove line 17: Environment="ARI_PASSWORD=asterisk_dev_only"
```

**Full stasis-app.service after changes:**
```ini
[Unit]
Description=Stasis App (Node.js) - Asterisk ARI Application
After=network.target asterisk.service
Requires=asterisk.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/aws_asterisk/stasis_app

# Environment variables
Environment="NODE_ENV=production"
Environment="ARI_HOST=127.0.0.1"
Environment="ARI_PORT=8088"
Environment="ARI_USERNAME=asterisk"
EnvironmentFile=/etc/stasis-app/secrets.env

# ExternalMedia settings
Environment="EXTERNAL_HOST=127.0.0.1"
Environment="CUSTOMER_PORT=12345"
Environment="AGENT_PORT=12346"

# Start command
ExecStart=/usr/bin/node app.js

# Restart policy
Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=stasis-app

[Install]
WantedBy=multi-user.target
```

**Step 7: Update app.js to require env var:**

```javascript
// stasis_app/app.js:19
// Before: const ARI_PASSWORD = process.env.ARI_PASSWORD || 'asterisk_dev_only';
// After:
const ARI_PASSWORD = process.env.ARI_PASSWORD;
if (!ARI_PASSWORD) {
  console.error('[FATAL] ARI_PASSWORD environment variable is required');
  console.error('[FATAL] Set via: export ARI_PASSWORD=xxx or use EnvironmentFile in systemd');
  process.exit(1);
}

// Remove the warning block at lines 156-159 (no longer needed)
```

**Step 8: Create AWS Secrets Manager entry for ARI (optional but recommended):**

```bash
aws secretsmanager create-secret \
    --name asterisk/ari/credentials \
    --secret-string '{"username":"asterisk","password":"YOUR_SECURE_PASSWORD"}'
```

**Acceptance Criteria:**
- [ ] `grep -r "asterisk_dev_only" .` returns 0 results in source code
- [ ] `grep -r "CHANGE_ME" .` returns 0 results (except documentation)
- [ ] Stasis app starts successfully with env var only
- [ ] Asterisk loads ARI password from external source
- [ ] `/etc/asterisk/secrets/get_ari_password.sh` exists and is executable
- [ ] `/etc/stasis-app/secrets.env` exists with proper permissions (600)

**Rollback:**
- Restore backup of original files
- Re-deploy with manual password entry

---

#### T2: Fix Command Injection Vulnerabilities

**Priority:** P0 - CRITICAL
**Effort:** 3 hours
**Risk:** CRITICAL (arbitrary command execution)

**Prerequisites - Install envsubst:**

```bash
# Amazon Linux 2 / RHEL / CentOS
sudo yum install -y gettext

# Ubuntu / Debian
sudo apt install -y gettext-base

# Verify installation
which envsubst
```

**Step 1: Create template files**

Before changing sed to envsubst, create template files from existing configs:

**Create `config/pjsip.conf.template` from `config/pjsip.conf`:**

The template already uses `__LINPHONE_PASSWORD__` placeholder. Additionally ensure these placeholders exist:
- `__LINPHONE_PASSWORD__` - Linphone account password
- `__EC2_PUBLIC_IP__` - EC2 Elastic IP (currently hardcoded as 3.36.250.255)
- `__VPC_CIDR__` - VPC CIDR (currently hardcoded as 172.31.0.0/16)

```bash
# Copy current config as template
cp config/pjsip.conf config/pjsip.conf.template

# Update template to use envsubst-compatible variables
sed -i 's/__LINPHONE_PASSWORD__/${LINPHONE_PASSWORD}/g' config/pjsip.conf.template
sed -i 's/3.36.250.255/${EC2_PUBLIC_IP}/g' config/pjsip.conf.template
sed -i 's|172.31.0.0/16|${VPC_CIDR}|g' config/pjsip.conf.template
```

**Create `config/res_odbc.conf.template` from `config/res_odbc.conf`:**

```bash
# Copy current config as template
cp config/res_odbc.conf config/res_odbc.conf.template

# Update template to use envsubst-compatible variable
sed -i 's/__DB_PASSWORD__/${DB_PASSWORD}/g' config/res_odbc.conf.template
```

**Final `config/res_odbc.conf.template` content:**
```ini
; =============================================================================
; Asterisk ODBC Configuration
; /etc/asterisk/res_odbc.conf
; =============================================================================

[asterisk]
enabled => yes
dsn => asterisk-connector
username => admin
; password is substituted by envsubst during deployment
password => ${DB_PASSWORD}
pre-connect => yes
sanitysql => select 1
idlecheck => 60
connect_timeout => 10
```

**Step 2: Update deploy.sh:161-169**

```bash
# Before:
# sed -e "s/__LINPHONE_PASSWORD__/${LINPHONE_PASSWORD}/g" \
#     -e "s/13.209.97.212/${EC2_PUBLIC_IP}/g" \
#     -e "s|172.31.0.0/16|${VPC_CIDR}|g" \
#     "${CONFIG_DIR}/pjsip.conf" > "${ASTERISK_CONFIG_DIR}/pjsip.conf"

# After:
export LINPHONE_PASSWORD EC2_PUBLIC_IP VPC_CIDR
envsubst '${LINPHONE_PASSWORD} ${EC2_PUBLIC_IP} ${VPC_CIDR}' \
    < "${CONFIG_DIR}/pjsip.conf.template" \
    > "${ASTERISK_CONFIG_DIR}/pjsip.conf"
```

**Full deploy_configs function after fix:**
```bash
deploy_configs() {
    print_header "Deploying Asterisk Configurations"

    # Deploy pjsip.conf with variable substitution using envsubst
    print_info "Deploying pjsip.conf..."
    export LINPHONE_PASSWORD EC2_PUBLIC_IP VPC_CIDR
    envsubst '${LINPHONE_PASSWORD} ${EC2_PUBLIC_IP} ${VPC_CIDR}' \
        < "${CONFIG_DIR}/pjsip.conf.template" \
        > "${ASTERISK_CONFIG_DIR}/pjsip.conf"

    # Deploy other configs as-is
    for conf in extensions.conf rtp.conf ari.conf http.conf; do
        print_info "Deploying ${conf}..."
        cp "${CONFIG_DIR}/${conf}" "${ASTERISK_CONFIG_DIR}/${conf}"
    done

    # Set permissions
    chown asterisk:asterisk "${ASTERISK_CONFIG_DIR}"/*.conf 2>/dev/null || true
    chmod 640 "${ASTERISK_CONFIG_DIR}/pjsip.conf"  # Restrict pjsip.conf (contains password)

    print_info "Configuration files deployed successfully"
}
```

**Step 3: Update scripts/setup_odbc.sh:95**

```bash
# Before:
# sudo sed -i "s/__DB_PASSWORD__/$DB_PASS/g" /etc/asterisk/res_odbc.conf

# After:
export DB_PASSWORD="$DB_PASS"
envsubst '${DB_PASSWORD}' < /etc/asterisk/res_odbc.conf.template \
    | sudo tee /etc/asterisk/res_odbc.conf > /dev/null
sudo chmod 640 /etc/asterisk/res_odbc.conf
```

**Step 4: Update .github/workflows/deploy.yml:48-55**

```yaml
# Before:
# sed "s|__DB_PASSWORD__|$DB_PASSWORD|g" config/res_odbc.conf | sudo tee /etc/asterisk/res_odbc.conf > /dev/null

# After:
export DB_PASSWORD
envsubst '${DB_PASSWORD}' < config/res_odbc.conf.template | sudo tee /etc/asterisk/res_odbc.conf > /dev/null
```

**Full deploy.yml section after fix:**
```yaml
# Deploy res_odbc.conf with DB password using envsubst
if [ -n "$DB_PASSWORD" ]; then
  export DB_PASSWORD
  envsubst '${DB_PASSWORD}' < config/res_odbc.conf.template | sudo tee /etc/asterisk/res_odbc.conf > /dev/null
  echo "res_odbc.conf deployed with DB password"
else
  sudo cp config/res_odbc.conf /etc/asterisk/res_odbc.conf
  echo "WARNING: DB_PASSWORD not set, using placeholder"
fi
```

**Why envsubst is safer:**
- Does not interpret special characters in password
- Passwords like `p@ss$word!` will not break
- No risk of shell injection
- Explicit variable list prevents unintended substitution

**Acceptance Criteria:**
- [ ] All sed commands for password substitution replaced with envsubst
- [ ] Template files exist: `config/pjsip.conf.template`, `config/res_odbc.conf.template`
- [ ] `which envsubst` returns path on EC2 instance
- [ ] Test with password containing special chars: `test$pass'word"!`
- [ ] Deployment succeeds with complex passwords

**Rollback:**
- Revert to sed-based deployment
- Ensure passwords do not contain special characters

---

#### T3: Update npm Dependencies

**Priority:** P0 - CRITICAL
**Effort:** 4 hours
**Risk:** HIGH (known CVEs being exploited)

**Current Vulnerabilities (npm audit):**

| Package | Severity | CVE | Issue |
|---------|----------|-----|-------|
| form-data | CRITICAL | CWE-330 | Weak random boundary |
| request | CRITICAL | CWE-918 | SSRF vulnerability |
| qs | HIGH | CWE-20 | DoS via memory exhaustion |
| tough-cookie | MODERATE | - | ReDoS |
| cookiejar | MODERATE | CWE-1333 | ReDoS |

**Root Cause:** `ari-client@2.2.0` depends on deprecated `request` package.

**Available ari-client versions:** 0.1.0 - 2.2.0 (verified: 1.2.0 EXISTS)

**Strategy: npm overrides (PRIMARY), downgrade (FALLBACK)**

**Step 1: Try npm overrides first (package.json):**

```json
{
  "name": "linphone-stasis-app",
  "version": "1.0.0",
  "description": "Stasis application for Linphone SIP integration with ExternalMedia",
  "main": "app.js",
  "scripts": {
    "start": "node app.js",
    "audit": "npm audit --production"
  },
  "dependencies": {
    "ari-client": "^2.2.0",
    "uuid": "^9.0.0"
  },
  "overrides": {
    "request": "npm:@cypress/request@^3.0.0",
    "form-data": "^4.0.0",
    "qs": "^6.14.0",
    "tough-cookie": "^5.0.0"
  },
  "engines": {
    "node": ">=16.0.0"
  }
}
```

**Step 2: Test overrides:**

```bash
cd stasis_app
rm -rf node_modules package-lock.json
npm install
npm audit --production

# Run functional tests
node app.js &
sleep 5
# Test ARI connection
curl -u asterisk:password http://127.0.0.1:8088/ari/asterisk
kill %1
```

**Step 3: If overrides fail, try ari-client@1.2.0:**

```bash
# Check what changed in 1.2.0 vs 2.2.0
npm view ari-client@1.2.0
npm view ari-client@2.2.0

# Install older version
npm install ari-client@1.2.0
npm audit
```

**Step 4: If 1.2.0 breaks functionality, consider alternatives:**

- `asterisk-ari` package (axios-based, no request dependency)
- Custom minimal ARI client using native fetch (Node 18+)

**Acceptance Criteria:**
- [ ] `npm audit --production` shows 0 critical/high vulnerabilities
- [ ] Stasis app connects to ARI successfully
- [ ] All call flows work (incoming, snoop, external media)
- [ ] Agent routing works (agent01-06)
- [ ] Port allocation works (12345-12400 range)

**Rollback:**
- `npm install ari-client@2.2.0`
- Document known vulnerabilities in SECURITY.md

---

### PHASE 2: HIGH PRIORITY (P1) - Security Hardening

---

#### T4: Restrict Anonymous SIP Endpoint

**Priority:** P1 - HIGH
**Effort:** 2 hours
**Risk:** HIGH (unauthorized calls)

**File:** `config/pjsip.conf:92-106`

**Current State:**
```ini
[anonymous]
type=endpoint
...
context=from-linphone  ; Same context as authenticated calls!
```

**Problem:** Anyone can call without authentication and reach the same dialplan.

**Step 1: Verify sound file exists:**

```bash
# Check if ss-noservice sound exists
sudo asterisk -rx "core show file version ss-noservice"
# Or find manually
find /var/lib/asterisk/sounds -name "ss-noservice*" 2>/dev/null
find /usr/share/asterisk/sounds -name "ss-noservice*" 2>/dev/null
```

**Step 2: Create restricted context in extensions.conf:**

Add to `config/extensions.conf`:

```ini
; =============================================================================
; Context: from-anonymous
; Handles anonymous/unauthenticated SIP calls - reject with message
; =============================================================================
[from-anonymous]
exten => _X.,1,NoOp(=== Anonymous call attempt from ${CALLERID(all)} ===)
 same => n,Log(WARNING,Anonymous call rejected: ${CALLERID(num)} -> ${EXTEN})
 same => n,Set(TIMEOUT(absolute)=30)
 same => n,Answer()
 same => n,Wait(0.5)
 same => n,TryExec(Playback(ss-noservice))
 same => n,GotoIf($["${TRYEXEC_STATUS}" != "SUCCESS"]?hangup)
 same => n,Wait(1)
 same => n(hangup),Hangup(CALL_REJECTED)

; Fallback if sound file missing
exten => _X.,n(hangup),Hangup(CALL_REJECTED)

; Handle 's' extension for anonymous
exten => s,1,Goto(_X.,1)
```

**Note:** Using `TryExec` with `Playback` ensures graceful handling if sound file is missing. If `ss-noservice` doesn't exist, it will still hangup cleanly.

**Step 3: Update anonymous endpoint in pjsip.conf:**

```ini
; config/pjsip.conf:95
; Before: context=from-linphone
; After:
context=from-anonymous
```

**Acceptance Criteria:**
- [ ] Anonymous calls hear "no service" message (or hangup if sound missing)
- [ ] Anonymous calls logged with CALLERID via `asterisk -rx "core show channels"`
- [ ] Authenticated calls (Linphone) work normally
- [ ] Verify: `sudo asterisk -rx "pjsip show endpoint anonymous" | grep context`

**Rollback:**
- Restore `context=from-linphone` for anonymous endpoint

---

#### T5: Restrict CORS Configuration

**Priority:** P1 - HIGH
**Effort:** 1 hour
**Risk:** MEDIUM (cross-origin attacks)

**File:** `config/ari.conf:9`

**Current State:**
```ini
allowed_origins=*
```

**Problem:** Allows any website to make ARI requests.

**Implementation:**

Since ARI is bound to 127.0.0.1, CORS is less critical but should still be restricted.

```ini
; config/ari.conf:9
; Before: allowed_origins=*
; After:
allowed_origins=http://127.0.0.1:8088
; Or remove the line entirely (default is deny)
```

**Acceptance Criteria:**
- [ ] Stasis app connects successfully (localhost)
- [ ] Test: `curl -H "Origin: https://evil.com" http://localhost:8088/ari/asterisk` shows no CORS headers
- [ ] Test: `curl -H "Origin: http://127.0.0.1:8088" http://localhost:8088/ari/asterisk` works

**Rollback:**
- Restore `allowed_origins=*`

---

#### T6: Disable Debug Mode in Production

**Priority:** P1 - HIGH
**Effort:** 1 hour
**Risk:** MEDIUM (information disclosure)

**File:** `config/pjsip.conf:13`

**Current State:**
```ini
[global]
type=global
debug=yes
```

**Problem:** Debug logging exposes SIP headers, credentials, call details.

**Step 1: Create environment-specific config files:**

**Create `config/pjsip.conf.prod.template`:**
Copy `config/pjsip.conf.template` but change:
```ini
[global]
type=global
debug=no
```

**Create `config/pjsip.conf.dev.template`:**
Same as current `config/pjsip.conf.template`:
```ini
[global]
type=global
debug=yes
```

**Step 2: Update .github/workflows/deploy.yml:**

```yaml
# At the start of script section, add environment detection:
# Determine environment from branch or explicit variable
ENVIRONMENT="${ENVIRONMENT:-production}"
if [ "$GITHUB_REF" = "refs/heads/develop" ] || [ "$GITHUB_REF" = "refs/heads/dev" ]; then
  ENVIRONMENT="development"
fi
echo "Deploying to environment: $ENVIRONMENT"

# Later, when deploying pjsip.conf:
echo "=== Deploying Asterisk configs ==="
if [ "$ENVIRONMENT" = "production" ]; then
  PJSIP_TEMPLATE="config/pjsip.conf.prod.template"
else
  PJSIP_TEMPLATE="config/pjsip.conf.dev.template"
fi

# Use envsubst with the appropriate template
export LINPHONE_PASSWORD EC2_PUBLIC_IP VPC_CIDR
envsubst '${LINPHONE_PASSWORD} ${EC2_PUBLIC_IP} ${VPC_CIDR}' \
    < "$PJSIP_TEMPLATE" \
    | sudo tee /etc/asterisk/pjsip.conf > /dev/null
```

**Step 3: Add ENVIRONMENT to GitHub secrets (optional):**

In GitHub repository settings, add secret:
- Name: `ENVIRONMENT`
- Value: `production` (or branch-based logic)

Update deploy.yml env section:
```yaml
env:
  AICC_WS_URL: ${{ secrets.AICC_WS_URL }}
  DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
  ENVIRONMENT: ${{ secrets.ENVIRONMENT || 'production' }}
```

**Acceptance Criteria:**
- [ ] Production Asterisk logs do not contain SIP debug info
- [ ] Development still has debug enabled
- [ ] Call quality unaffected
- [ ] Verify: `sudo asterisk -rx "pjsip show settings" | grep -i debug`

**Rollback:**
- Set `debug=yes` temporarily for troubleshooting

---

#### T7: Enable RDS Deletion Protection

**Priority:** P1 - HIGH
**Effort:** 30 minutes
**Risk:** LOW (prevents accidental deletion)

**File:** `terraform/rds.tf:52-53`

**Current State:**
```hcl
deletion_protection = false
skip_final_snapshot = true
```

**Implementation:**

```hcl
# terraform/rds.tf:52-53
# Before:
# deletion_protection = false
# skip_final_snapshot = true

# After:
deletion_protection = true
skip_final_snapshot = false
final_snapshot_identifier = "asterisk-db-final-snapshot"
```

**Note:** Using static identifier instead of `timestamp()` to avoid Terraform plan differences on every run. If you need unique snapshots, use a manual override or lifecycle rule.

**Apply the change:**

```bash
cd terraform
terraform plan -out=tfplan
# Verify only deletion_protection and snapshot settings change
terraform apply tfplan
```

**Acceptance Criteria:**
- [ ] `terraform plan` shows deletion_protection change
- [ ] `terraform plan` does NOT show changes on subsequent runs (no timestamp drift)
- [ ] Manual `terraform destroy` blocked without disabling protection first
- [ ] Snapshot will be taken on destroy

**Rollback:**
- Set `deletion_protection = false` and apply

---

### PHASE 3: MEDIUM PRIORITY (P2) - Enhanced Security

---

#### T8: Enable SRTP Media Encryption

**Priority:** P2 - MEDIUM
**Effort:** 3 hours
**Risk:** MEDIUM (compatibility concerns)

**Files:** `config/pjsip.conf:76, 105`

**Current State:**
```ini
media_encryption=no
; media_encryption_optimistic=yes
```

**Implementation:**

1. **Enable optimistic SRTP (backward compatible):**

For `linphone-endpoint` (around line 76):
```ini
; Before:
media_encryption=no
; media_encryption_optimistic=yes

; After:
media_encryption=sdes
media_encryption_optimistic=yes
```

For `anonymous` endpoint (around line 105):
```ini
; Before:
media_encryption=no
; media_encryption_optimistic=yes

; After:
media_encryption=sdes
media_encryption_optimistic=yes
```

2. **Verify Linphone client supports SRTP:**
   - Settings > Network > Media Encryption > SRTP

**Acceptance Criteria:**
- [ ] SRTP negotiated when both endpoints support it
- [ ] Calls still work with non-SRTP endpoints (optimistic mode)
- [ ] RTP debug shows encrypted media (when SRTP active)
- [ ] Verify: `sudo asterisk -rx "pjsip show endpoint linphone-endpoint" | grep media_encryption`

**Rollback:**
- Set `media_encryption=no`

---

#### T9: Redact Sensitive Information from Logs

**Priority:** P2 - MEDIUM
**Effort:** 2 hours
**Risk:** LOW

**Files:**

| File | Line | Issue |
|------|------|-------|
| `stasis_app/app.js` | 164-166 | Logs ARI URL with potential credentials |
| `scripts/setup_odbc.sh` | 41-44 | Logs DB host/port (minor) |
| `scripts/setup_odbc.sh` | 105 | Password visible in isql command and ps output |

**Step 1: app.js - Redact URL:**

```javascript
// stasis_app/app.js:164-166
// Before: console.log(`ARI URL: ${ARI_URL}`);
// After:
const redactedUrl = ARI_URL.replace(/\/\/[^:]+:[^@]+@/, '//<credentials-redacted>@');
console.log(`ARI URL: ${redactedUrl}`);
```

**Step 2: setup_odbc.sh - Use DSN-only connection:**

Since the password is already stored in `/etc/odbc.ini`, we can use DSN-only authentication:

```bash
# scripts/setup_odbc.sh:104-106
# Before:
# if command -v isql &> /dev/null; then
#     echo "SELECT 1;" | isql -v asterisk-connector $DB_USER $DB_PASS && echo "ODBC connection successful!" || echo "ODBC connection failed!"
# fi

# After: Use DSN-only (password already in /etc/odbc.ini)
if command -v isql &> /dev/null; then
    echo "Testing ODBC connection (password from DSN)..."
    echo "SELECT 1;" | isql -v asterisk-connector 2>&1 && \
        echo "ODBC connection successful!" || \
        echo "ODBC connection failed! Check /etc/odbc.ini"
fi
```

**Why this works:** The DSN `asterisk-connector` in `/etc/odbc.ini` already contains the User and Password fields, so isql can authenticate without command-line credentials.

**Acceptance Criteria:**
- [ ] Logs do not contain passwords
- [ ] `ps aux | grep isql` does not show passwords
- [ ] ODBC connection test still works
- [ ] Functionality unchanged

**Rollback:**
- Restore original logging (for debugging)

---

#### T10: Add TLS Transport Option

**Priority:** P2 - MEDIUM
**Effort:** 4 hours
**Risk:** MEDIUM (certificate management)

**File:** `config/pjsip.conf:18-25`

**Current State:**
```ini
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060
```

**Step 1: Generate self-signed certificate (or obtain from CA):**

```bash
# Create certificate directory
sudo mkdir -p /etc/asterisk/certs
sudo chmod 700 /etc/asterisk/certs

# Generate self-signed certificate (valid for 365 days)
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/asterisk/certs/asterisk.key \
    -out /etc/asterisk/certs/asterisk.pem \
    -subj "/CN=asterisk.local/O=AICC/C=KR"

# Set proper permissions
sudo chmod 600 /etc/asterisk/certs/asterisk.key
sudo chmod 644 /etc/asterisk/certs/asterisk.pem
sudo chown asterisk:asterisk /etc/asterisk/certs/*

# Create CA file (copy of cert for self-signed)
sudo cp /etc/asterisk/certs/asterisk.pem /etc/asterisk/certs/ca.pem
```

**Step 2: Add TLS transport to pjsip.conf:**

Add after `[transport-udp]` section:

```ini
; =============================================================================
; Transport - TLS for encrypted SIP signaling
; =============================================================================
[transport-tls]
type=transport
protocol=tls
bind=0.0.0.0:5061
cert_file=/etc/asterisk/certs/asterisk.pem
priv_key_file=/etc/asterisk/certs/asterisk.key
ca_list_file=/etc/asterisk/certs/ca.pem
method=tlsv1_2
; NAT Settings - Same as UDP
external_media_address=${EC2_PUBLIC_IP}
external_signaling_address=${EC2_PUBLIC_IP}
local_net=${VPC_CIDR}
```

**Step 3: Update Security Group (Terraform):**

Add to `terraform/ec2.tf` or appropriate security group file:

```hcl
# Add TCP 5061 for SIP over TLS
ingress {
  from_port   = 5061
  to_port     = 5061
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]  # Or restrict to known SIP providers
  description = "SIP over TLS"
}
```

**Acceptance Criteria:**
- [ ] Certificate files exist with correct permissions
- [ ] TLS transport loads without errors: `sudo asterisk -rx "pjsip show transports"`
- [ ] SIP over TLS works with compatible clients
- [ ] UDP still works for legacy clients
- [ ] Security group allows TCP 5061

**Rollback:**
- Remove TLS transport section from pjsip.conf
- Close port 5061 in security group

---

## Commit Strategy

| Phase | Commits |
|-------|---------|
| P0-T1 | `fix(security): externalize hardcoded passwords` |
| P0-T2 | `fix(security): replace sed with envsubst to prevent injection` |
| P0-T3 | `fix(deps): update ari-client to resolve npm audit vulnerabilities` |
| P1-T4 | `fix(security): restrict anonymous SIP endpoint` |
| P1-T5 | `fix(security): restrict CORS to localhost` |
| P1-T6 | `fix(security): disable debug mode in production` |
| P1-T7 | `fix(infra): enable RDS deletion protection` |
| P2-T8 | `feat(security): enable SRTP media encryption` |
| P2-T9 | `fix(security): redact sensitive info from logs` |
| P2-T10 | `feat(security): add TLS transport option` |

---

## Success Criteria

### Phase 1 Complete (P0)
- [ ] `git log --oneline | head -3` shows security commits
- [ ] `grep -r "asterisk_dev_only\|CHANGE_ME" . --include="*.js" --include="*.sql" --include="*.conf" --include="*.service"` returns empty
- [ ] `npm audit --production` shows 0 critical/high
- [ ] Deploy script works with password `test$'pass"word!`
- [ ] Template files exist: `config/pjsip.conf.template`, `config/res_odbc.conf.template`

### Phase 2 Complete (P1)
- [ ] Anonymous calls rejected with recording or clean hangup
- [ ] `curl -H "Origin: https://evil.com" http://localhost:8088/ari/asterisk` blocked
- [ ] Production logs do not contain SIP debug
- [ ] `terraform state show aws_db_instance.asterisk_mysql | grep deletion_protection` shows true
- [ ] `terraform plan` shows no changes after applying (no timestamp drift)

### Phase 3 Complete (P2)
- [ ] SRTP negotiated for capable endpoints
- [ ] No passwords visible in logs or ps output
- [ ] TLS transport available on 5061 (optional)
- [ ] Certificate files exist with proper permissions

---

## Testing Requirements

### Pre-deployment Testing
1. **Unit tests:** Verify env var loading
2. **Integration tests:** Full call flow with dual snoop
3. **Security tests:**
   - Attempt anonymous call
   - Test CORS from external origin
   - Verify SRTP negotiation

### Post-deployment Verification
```bash
# Check for hardcoded secrets
grep -r "asterisk_dev_only" /etc/asterisk/ /home/ubuntu/aws_asterisk/

# Check npm vulnerabilities
cd ~/aws_asterisk/stasis_app && npm audit

# Verify anonymous handling
asterisk -rx "pjsip show endpoint anonymous"

# Verify SRTP
asterisk -rx "pjsip show endpoint linphone-endpoint" | grep media_encryption

# Verify secrets files
ls -la /etc/asterisk/secrets/
ls -la /etc/stasis-app/

# Verify envsubst is available
which envsubst

# Test isql without password in ps
ps aux | grep isql
```

---

## Risk Assessment

| Task | Risk Level | Mitigation |
|------|------------|------------|
| T1 (Passwords) | HIGH | Test in staging, have manual fallback |
| T2 (Injection) | MEDIUM | Test with special characters |
| T3 (npm) | HIGH | Full regression testing |
| T4 (Anonymous) | MEDIUM | TryExec handles missing sound file |
| T5 (CORS) | LOW | Only affects browser-based clients |
| T6 (Debug) | LOW | Easy to re-enable |
| T7 (RDS) | LOW | Static snapshot ID prevents drift |
| T8 (SRTP) | MEDIUM | Optimistic mode for compatibility |
| T9 (Logging) | LOW | DSN-only approach is standard |
| T10 (TLS) | MEDIUM | Certificate management complexity |

---

## Timeline

| Day | Tasks | Milestone |
|-----|-------|-----------|
| 1 | T1 (passwords) | Secrets externalized |
| 2 | T2 (injection) + T3 (npm) | Critical vulns fixed |
| 3 | Testing + verification | P0 COMPLETE |
| 4-5 | T4 (anonymous) + T5 (CORS) | Access restricted |
| 6-7 | T6 (debug) + T7 (RDS) | P1 COMPLETE |
| 8-10 | T8 (SRTP) + T9 (logging) | Encryption enabled |
| 11-14 | T10 (TLS) + final testing | P2 COMPLETE |

---

**Plan Generated:** 2026-01-28
**Author:** Prometheus (Planner Agent)
**Review:** Critic feedback addressed (Iteration 2)
**Status:** READY FOR EXECUTION
