# Security Hardening Progress - Phase 0 (CRITICAL)

**Status**: COMPLETE
**Completed**: 2026-01-28

---

## T1: Remove Hardcoded Passwords - DONE

### Changes Made:
| File | Change |
|------|--------|
| `config/ari.conf:20` | `password=asterisk_dev_only` → `#exec /etc/asterisk/secrets/get_ari_password.sh` |
| `stasis_app/app.js:19-24` | Removed fallback, added mandatory env var check with fatal error |
| `stasis_app/app.js:156-159` | Removed warning block about default password |
| `stasis_app/stasis-app.service:17` | Removed hardcoded ARI_PASSWORD, added `EnvironmentFile=/etc/stasis-app/secrets.env` |

### Verification:
```bash
grep -r "asterisk_dev_only" config/ stasis_app/
# Result: NO MATCHES
```

---

## T2: Fix Command Injection Vulnerabilities - DONE

### Files Created:
- `config/pjsip.conf.template` - Uses ${LINPHONE_PASSWORD}, ${EC2_PUBLIC_IP}, ${VPC_CIDR}
- `config/res_odbc.conf.template` - Uses ${DB_PASSWORD}

### Files Modified:
| File | Change |
|------|--------|
| `deploy.sh` | Replaced sed with envsubst for pjsip.conf |
| `scripts/setup_odbc.sh` | Replaced sed with envsubst for res_odbc.conf |
| `.github/workflows/deploy.yml` | Replaced sed with envsubst for res_odbc.conf |

### Security Improvement:
- Passwords with special characters (e.g., `test$'pass"word!`) no longer cause injection
- Template-based substitution is shell-safe

---

## T3: Update npm Dependencies - DONE

### Changes Made (stasis_app/package.json):
```json
"overrides": {
  "request": "npm:@cypress/request@^3.0.0",
  "form-data": "^4.0.0",
  "qs": "^6.14.0",
  "tough-cookie": "^5.0.0",
  "cookiejar": "^2.1.4"
}
```

### Verification:
```bash
npm audit --production
# Result: 0 vulnerabilities
```

---

## Phase 0 Summary

| Task | Status | Risk Reduced |
|------|--------|--------------|
| T1: Hardcoded Passwords | DONE | CRITICAL → NONE |
| T2: Command Injection | DONE | CRITICAL → NONE |
| T3: npm Vulnerabilities | DONE | CRITICAL → NONE |

**All CRITICAL vulnerabilities remediated.**
