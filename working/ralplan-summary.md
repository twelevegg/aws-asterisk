# RALPLAN Summary - AWS Asterisk Security Hardening

## Final Status: APPROVED

| Metric | Value |
|--------|-------|
| Iterations | 2 |
| Final Verdict | OKAY |
| Plan Location | `.omc/plans/security-hardening.md` |
| Total Tasks | 10 |
| Timeline | 14 days |

## Iteration History

### Iteration 0 → REJECT (9 issues)
1. T1 Missing Script/Secrets Details
2. T3 npm ari-client@1.2.0 verification
3. T2 Template Files Missing
4. T4 Missing Sound File Verification
5. T6 Environment Strategy Incomplete
6. T10 Certificate Generation Missing
7. T7 Terraform timestamp() Issue
8. T9 isql Password in ps Output
9. envsubst Package Dependency

### Iteration 1 → OKAY
All 9 issues addressed with:
- Complete `get_ari_password.sh` script with AWS Secrets Manager
- npm overrides as PRIMARY strategy
- Template file creation steps + envsubst installation
- TryExec fallback for missing sound files
- Complete YAML syntax for deploy.yml
- OpenSSL certificate generation commands
- Static snapshot identifier (no timestamp drift)
- DSN-only isql approach

## Plan Overview

### Phase 1 (P0) - CRITICAL - Days 1-3
| Task | Description |
|------|-------------|
| T1 | Remove hardcoded passwords |
| T2 | Fix command injection (sed → envsubst) |
| T3 | Update npm dependencies |

### Phase 2 (P1) - HIGH - Days 4-7
| Task | Description |
|------|-------------|
| T4 | Restrict anonymous SIP endpoint |
| T5 | Restrict CORS configuration |
| T6 | Disable debug mode in production |
| T7 | Enable RDS deletion protection |

### Phase 3 (P2) - MEDIUM - Days 8-14
| Task | Description |
|------|-------------|
| T8 | Enable SRTP media encryption |
| T9 | Redact sensitive logging |
| T10 | Add TLS transport option |

## Files Modified

### Configuration Files
- `config/ari.conf`
- `config/pjsip.conf` → `pjsip.conf.template`, `pjsip.conf.prod.template`, `pjsip.conf.dev.template`
- `config/res_odbc.conf` → `res_odbc.conf.template`
- `config/extensions.conf`

### Application Files
- `stasis_app/app.js`
- `stasis_app/stasis-app.service`

### Scripts
- `deploy.sh`
- `scripts/setup_odbc.sh`
- `.github/workflows/deploy.yml`

### Infrastructure
- `terraform/rds.tf`
- Security Group (port 5061 for TLS)

### New Files to Create
- `/etc/asterisk/secrets/get_ari_password.sh`
- `/etc/asterisk/secrets/ari.secret`
- `/etc/stasis-app/secrets.env`
- `/etc/asterisk/certs/asterisk.pem`
- `/etc/asterisk/certs/asterisk.key`

## Next Steps

Execute the plan using:
- `/oh-my-claudecode:ralph` for persistent execution
- `/oh-my-claudecode:ultrawork` for parallel execution
- Manual implementation following the task order

## Verification Commands

```bash
# After Phase 1
grep -r "asterisk_dev_only" .
npm audit --production
which envsubst

# After Phase 2
asterisk -rx "pjsip show endpoint anonymous" | grep context
curl -H "Origin: https://evil.com" http://localhost:8088/ari/asterisk
terraform state show aws_db_instance.asterisk_mysql | grep deletion_protection

# After Phase 3
asterisk -rx "pjsip show endpoint linphone-endpoint" | grep media_encryption
ps aux | grep isql
ls -la /etc/asterisk/certs/
```
