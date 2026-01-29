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

1. **ari.conf** - Use Asterisk external secrets:
   ```ini
   ; config/ari.conf:20
   ; Before: password=asterisk_dev_only
   ; After: Use #exec or environment variable
   #exec /etc/asterisk/secrets/get_ari_password.sh
   ```

2. **stasis-app.service** - Use EnvironmentFile:
   ```ini
   ; stasis_app/stasis-app.service
   ; Add after line 12:
   EnvironmentFile=/etc/stasis-app/secrets.env
   ; Remove line 17: Environment="ARI_PASSWORD=asterisk_dev_only"
   ```

3. **app.js** - Remove unsafe fallback:
   ```javascript
   // stasis_app/app.js:19
   // Before: const ARI_PASSWORD = process.env.ARI_PASSWORD || 'asterisk_dev_only';
   // After:
   const ARI_PASSWORD = process.env.ARI_PASSWORD;
   if (!ARI_PASSWORD) {
     console.error('[FATAL] ARI_PASSWORD environment variable is required');
     process.exit(1);
   }
   ```

4. **seed_agents.sql** - Add documentation and script:
   ```sql
   -- sql/seed_agents.sql
   -- Replace static passwords with instruction to use generate script
   -- Create: scripts/generate_agent_passwords.sh
   ```

**Acceptance Criteria:**
- [ ] `grep -r "asterisk_dev_only" .` returns 0 results
- [ ] `grep -r "CHANGE_ME" .` returns 0 results (except documentation)
- [ ] Stasis app starts successfully with env var only
- [ ] Asterisk loads ARI password from external source

**Rollback:**
- Restore backup of original files
- Re-deploy with manual password entry

---

#### T2: Fix Command Injection Vulnerabilities

**Priority:** P0 - CRITICAL
**Effort:** 3 hours
**Risk:** CRITICAL (arbitrary command execution)

**Files to Modify:**

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `deploy.sh` | 166 | `sed "s/__LINPHONE_PASSWORD__/${LINPHONE_PASSWORD}/g"` | Use envsubst or printf |
| `scripts/setup_odbc.sh` | 95 | `sed -i "s/__DB_PASSWORD__/$DB_PASS/g"` | Use envsubst |
| `.github/workflows/deploy.yml` | 50 | `sed "s|__DB_PASSWORD__|$DB_PASSWORD|g"` | Use envsubst |

**Implementation:**

1. **deploy.sh:166** - Replace sed with envsubst:
   ```bash
   # Before:
   # sed -e "s/__LINPHONE_PASSWORD__/${LINPHONE_PASSWORD}/g" \

   # After:
   export LINPHONE_PASSWORD
   envsubst '${LINPHONE_PASSWORD}' < "${CONFIG_DIR}/pjsip.conf.template" > "${ASTERISK_CONFIG_DIR}/pjsip.conf"
   ```

2. **scripts/setup_odbc.sh:95** - Use printf with literal:
   ```bash
   # Before:
   # sudo sed -i "s/__DB_PASSWORD__/$DB_PASS/g" /etc/asterisk/res_odbc.conf

   # After:
   # Create template, use envsubst
   export DB_PASS
   envsubst '${DB_PASS}' < /etc/asterisk/res_odbc.conf.template | sudo tee /etc/asterisk/res_odbc.conf > /dev/null
   ```

3. **.github/workflows/deploy.yml:50** - Use envsubst:
   ```yaml
   # Before:
   # sed "s|__DB_PASSWORD__|$DB_PASSWORD|g" config/res_odbc.conf

   # After:
   export DB_PASSWORD
   envsubst '${DB_PASSWORD}' < config/res_odbc.conf.template | sudo tee /etc/asterisk/res_odbc.conf > /dev/null
   ```

**Why envsubst is safer:**
- Does not interpret special characters in password
- Passwords like `p@ss$word!` will not break
- No risk of shell injection

**Acceptance Criteria:**
- [ ] All sed commands replaced with envsubst
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

**Options:**

| Option | Effort | Risk | Recommendation |
|--------|--------|------|----------------|
| A: Downgrade ari-client to 1.2.0 | Low | Medium | Possible breaking changes |
| B: Fork ari-client, update deps | High | Low | Best long-term solution |
| C: Use npm overrides | Medium | Medium | Quick fix, may break |

**Recommended: Option A with testing**

**Implementation:**

1. **Test ari-client@1.2.0 compatibility:**
   ```bash
   cd stasis_app
   npm install ari-client@1.2.0
   npm audit
   # Test all call flows
   ```

2. **If Option A fails, use npm overrides (package.json):**
   ```json
   {
     "overrides": {
       "request": "npm:@cypress/request@^3.0.0",
       "form-data": "^4.0.0",
       "qs": "^6.14.1",
       "tough-cookie": "^5.0.0"
     }
   }
   ```

3. **If overrides fail, consider alternative ARI client:**
   - `asterisk-ari` (newer, axios-based)
   - Custom minimal ARI client

**Acceptance Criteria:**
- [ ] `npm audit` shows 0 critical/high vulnerabilities
- [ ] Stasis app connects to ARI successfully
- [ ] All call flows work (incoming, snoop, external media)

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

**Options:**

| Option | Description | Risk |
|--------|-------------|------|
| A: Remove anonymous endpoint | Block all unauthenticated calls | May break some SIP flows |
| B: Route to restricted context | Allow but limit functionality | Safer |
| C: Add rate limiting + logging | Monitor and limit | Minimal protection |

**Recommended: Option B**

**Implementation:**

1. **Create restricted context in extensions.conf:**
   ```ini
   ; config/extensions.conf - Add:
   [from-anonymous]
   exten => _X.,1,NoOp(Anonymous call from ${CALLERID(all)})
    same => n,Log(WARNING,Anonymous call attempt: ${CALLERID(num)} -> ${EXTEN})
    same => n,Playback(ss-noservice)
    same => n,Hangup()
   ```

2. **Update anonymous endpoint:**
   ```ini
   ; config/pjsip.conf:95
   ; Before: context=from-linphone
   ; After:
   context=from-anonymous
   ```

**Acceptance Criteria:**
- [ ] Anonymous calls hear "no service" message
- [ ] Anonymous calls logged with CALLERID
- [ ] Authenticated calls (Linphone) work normally

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
- [ ] External origin requests are blocked (test with curl)

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

**Implementation:**

1. **Create environment-specific configs:**
   ```bash
   # config/pjsip.conf.prod
   [global]
   type=global
   debug=no

   # config/pjsip.conf.dev
   [global]
   type=global
   debug=yes
   ```

2. **Update deploy.yml to use correct config:**
   ```yaml
   # Select config based on environment
   if [ "$ENVIRONMENT" = "production" ]; then
     cp config/pjsip.conf.prod config/pjsip.conf
   fi
   ```

**Acceptance Criteria:**
- [ ] Production Asterisk logs do not contain SIP debug info
- [ ] Development still has debug enabled
- [ ] Call quality unaffected

**Rollback:**
- Set `debug=yes` temporarily for troubleshooting

---

#### T7: Enable RDS Deletion Protection

**Priority:** P1 - HIGH
**Effort:** 30 minutes
**Risk:** LOW (prevents accidental deletion)

**File:** `terraform/rds.tf:52`

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
final_snapshot_identifier = "asterisk-db-final-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
```

**Acceptance Criteria:**
- [ ] `terraform plan` shows deletion_protection change
- [ ] Manual `terraform destroy` blocked without disabling
- [ ] Snapshot taken on destroy

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
   ```ini
   ; config/pjsip.conf - For linphone-endpoint and anonymous
   media_encryption=sdes
   media_encryption_optimistic=yes
   ```

2. **Verify Linphone client supports SRTP:**
   - Settings > Network > Media Encryption > SRTP

**Acceptance Criteria:**
- [ ] SRTP negotiated when both endpoints support it
- [ ] Calls still work with non-SRTP endpoints
- [ ] RTP debug shows encrypted media (when SRTP active)

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
| `scripts/setup_odbc.sh` | 105 | Password visible in isql command |

**Implementation:**

1. **app.js - Redact URL:**
   ```javascript
   // stasis_app/app.js:164-166
   // Before: console.log(`ARI URL: ${ARI_URL}`);
   // After:
   console.log(`ARI URL: ${ARI_URL.replace(/\/\/[^:]+:[^@]+@/, '//<redacted>@')}`);
   ```

2. **setup_odbc.sh - Redact isql:**
   ```bash
   # scripts/setup_odbc.sh:105
   # Before: echo "SELECT 1;" | isql -v asterisk-connector $DB_USER $DB_PASS
   # After:
   echo "SELECT 1;" | isql -v asterisk-connector $DB_USER "$DB_PASS" 2>&1 && echo "ODBC connection successful!" || echo "ODBC connection failed!"
   # Note: Still shows password in ps output; consider using .odbc.ini instead
   ```

**Acceptance Criteria:**
- [ ] Logs do not contain passwords
- [ ] `ps aux | grep` does not show passwords
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

**Implementation:**

1. **Generate/obtain TLS certificate**

2. **Add TLS transport:**
   ```ini
   ; config/pjsip.conf - Add after transport-udp
   [transport-tls]
   type=transport
   protocol=tls
   bind=0.0.0.0:5061
   cert_file=/etc/asterisk/certs/asterisk.pem
   priv_key_file=/etc/asterisk/certs/asterisk.key
   ca_list_file=/etc/asterisk/certs/ca.pem
   method=tlsv1_2
   ```

3. **Update Security Group:**
   - Add TCP 5061 inbound

**Acceptance Criteria:**
- [ ] TLS transport loads without errors
- [ ] SIP over TLS works with compatible clients
- [ ] UDP still works for legacy clients

**Rollback:**
- Remove TLS transport section
- Close port 5061

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

### Phase 2 Complete (P1)
- [ ] Anonymous calls rejected with recording
- [ ] `curl -H "Origin: https://evil.com" http://localhost:8088/ari/asterisk` blocked
- [ ] Production logs do not contain SIP debug
- [ ] `terraform state show aws_db_instance.asterisk_mysql | grep deletion_protection` shows true

### Phase 3 Complete (P2)
- [ ] SRTP negotiated for capable endpoints
- [ ] No passwords visible in logs or ps output
- [ ] TLS transport available on 5061 (optional)

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
```

---

## Risk Assessment

| Task | Risk Level | Mitigation |
|------|------------|------------|
| T1 (Passwords) | HIGH | Test in staging, have manual fallback |
| T2 (Injection) | MEDIUM | Test with special characters |
| T3 (npm) | HIGH | Full regression testing |
| T4 (Anonymous) | MEDIUM | May break legitimate anonymous calls |
| T5 (CORS) | LOW | Only affects browser-based clients |
| T6 (Debug) | LOW | Easy to re-enable |
| T7 (RDS) | LOW | Can disable for maintenance |
| T8 (SRTP) | MEDIUM | Optimistic mode for compatibility |
| T9 (Logging) | LOW | Debugging may be harder |
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
**Review:** Pending Critic review
