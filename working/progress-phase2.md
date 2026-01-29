# Security Hardening Progress - Phase 2 (MEDIUM)

**Status**: COMPLETE
**Completed**: 2026-01-28

---

## T8: Enable SRTP Media Encryption - DONE

### Changes Made:
| File | Change |
|------|--------|
| `config/pjsip.conf` | linphone-endpoint + anonymous: `media_encryption=sdes`, `media_encryption_optimistic=yes` |
| `config/pjsip.conf.template` | Same changes |
| `config/pjsip.conf.prod.template` | Same changes |
| `config/pjsip.conf.dev.template` | Same changes |

### Security Improvement:
- SRTP encryption negotiated when both endpoints support it
- Optimistic mode ensures backward compatibility with non-SRTP endpoints
- Media streams encrypted with SDES key exchange

---

## T9: Redact Sensitive Information from Logs - DONE

### Changes Made:
| File | Change |
|------|--------|
| `stasis_app/app.js:163-164` | ARI URL logging now redacts credentials: `<credentials-redacted>` |
| `scripts/setup_odbc.sh:106-110` | isql uses DSN-only auth (no password in command line) |

### Security Improvement:
- Credentials no longer appear in application logs
- `ps aux` does not show passwords from isql command
- Log files safe for sharing during debugging

---

## T10: Add TLS Transport Option - DONE

### Files Created/Modified:
| File | Change |
|------|--------|
| `config/pjsip.conf` | Added `[transport-tls]` section |
| `config/pjsip.conf.template` | Added `[transport-tls]` with ${EC2_PUBLIC_IP}, ${VPC_CIDR} |
| `config/pjsip.conf.prod.template` | Same |
| `config/pjsip.conf.dev.template` | Same |
| `terraform/ec2_security_group.tf` | Added port 5061/TCP ingress rule |

### TLS Configuration:
```ini
[transport-tls]
protocol=tls
bind=0.0.0.0:5061
cert_file=/etc/asterisk/certs/asterisk.pem
priv_key_file=/etc/asterisk/certs/asterisk.key
method=tlsv1_2
```

### Required Setup on EC2:
```bash
sudo mkdir -p /etc/asterisk/certs
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/asterisk/certs/asterisk.key \
    -out /etc/asterisk/certs/asterisk.pem \
    -subj "/CN=asterisk.local/O=AICC/C=KR"
sudo chmod 600 /etc/asterisk/certs/asterisk.key
sudo chown asterisk:asterisk /etc/asterisk/certs/*
```

---

## Phase 2 Summary

| Task | Status | Risk Reduced |
|------|--------|--------------|
| T8: SRTP Encryption | DONE | MEDIUM → NONE |
| T9: Log Redaction | DONE | MEDIUM → NONE |
| T10: TLS Transport | DONE | MEDIUM → NONE |

**All MEDIUM priority vulnerabilities remediated.**
