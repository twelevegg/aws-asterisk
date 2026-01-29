# Security Hardening Progress - Phase 1 (HIGH)

**Status**: COMPLETE
**Completed**: 2026-01-28

---

## T4: Restrict Anonymous SIP Endpoint - DONE

### Changes Made:
| File | Change |
|------|--------|
| `config/extensions.conf` | Added `[from-anonymous]` context with TryExec Playback + CALL_REJECTED hangup |
| `config/pjsip.conf:95` | `context=from-linphone` → `context=from-anonymous` |
| `config/pjsip.conf.template:95` | Same change |

### Security Improvement:
- Anonymous/unauthenticated SIP calls now rejected with logging
- Uses TryExec for graceful handling if sound file missing
- Authenticated Linphone calls unaffected

---

## T5: Restrict CORS Configuration - DONE

### Changes Made:
| File | Change |
|------|--------|
| `config/ari.conf:9` | `allowed_origins=*` → `allowed_origins=http://127.0.0.1:8088` |

### Security Improvement:
- Cross-origin ARI requests now blocked except from localhost
- Prevents browser-based CSRF attacks

---

## T6: Disable Debug Mode in Production - DONE

### Files Created:
- `config/pjsip.conf.prod.template` - debug=no
- `config/pjsip.conf.dev.template` - debug=yes

### Files Modified:
| File | Change |
|------|--------|
| `.github/workflows/deploy.yml` | Environment detection + template selection logic |

### Deployment Behavior:
- **main branch** → Production template (debug=no)
- **develop/dev branches** → Development template (debug=yes)

---

## T7: Enable RDS Deletion Protection - DONE

### Changes Made (terraform/rds.tf):
```hcl
deletion_protection = true
skip_final_snapshot = false
final_snapshot_identifier = "asterisk-db-final-snapshot"
```

### Security Improvement:
- Accidental `terraform destroy` now blocked
- Final snapshot created before any deletion

---

## Phase 1 Summary

| Task | Status | Risk Reduced |
|------|--------|--------------|
| T4: Anonymous SIP | DONE | HIGH → NONE |
| T5: CORS | DONE | MEDIUM → NONE |
| T6: Debug Mode | DONE | MEDIUM → NONE |
| T7: RDS Protection | DONE | HIGH → NONE |

**All HIGH priority vulnerabilities remediated.**
