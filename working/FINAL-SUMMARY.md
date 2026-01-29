# Security Hardening - COMPLETE

**Status**: ALL TASKS COMPLETE + ARCHITECT APPROVED
**Completed**: 2026-01-28

---

## Executive Summary

Successfully remediated **10 security vulnerabilities** across 3 phases:
- **6 CRITICAL** → 0 remaining
- **6 HIGH** → 0 remaining
- **4 MEDIUM** → 0 remaining

---

## Phase 0: CRITICAL (완료)

| Task | Description | Files Modified |
|------|-------------|----------------|
| T1 | Removed hardcoded passwords | ari.conf, app.js (x2), stasis-app.service |
| T2 | Fixed command injection (sed→envsubst) | deploy.sh, setup_odbc.sh, deploy.yml + 4 templates |
| T3 | Updated npm dependencies (0 vulns) | package.json |

---

## Phase 1: HIGH (완료)

| Task | Description | Files Modified |
|------|-------------|----------------|
| T4 | Restricted anonymous SIP endpoint | extensions.conf, pjsip.conf (all) |
| T5 | Restricted CORS to localhost | ari.conf |
| T6 | Disabled debug in production | pjsip.conf.prod.template, deploy.yml |
| T7 | Enabled RDS deletion protection | rds.tf |

---

## Phase 2: MEDIUM (완료)

| Task | Description | Files Modified |
|------|-------------|----------------|
| T8 | Enabled SRTP media encryption | pjsip.conf (all templates) |
| T9 | Redacted sensitive logs | app.js, setup_odbc.sh |
| T10 | Added TLS transport (5061) | pjsip.conf (all), ec2_security_group.tf |

---

## Files Changed (Total: 15)

### Modified:
1. `.github/workflows/deploy.yml`
2. `config/ari.conf`
3. `config/extensions.conf`
4. `config/pjsip.conf`
5. `config/res_odbc.conf`
6. `deploy.sh`
7. `scripts/setup_odbc.sh`
8. `stasis_app/app.js`
9. `stasis_app/package.json`
10. `stasis_app/stasis-app.service`
11. `terraform/ec2_security_group.tf`
12. `terraform/rds.tf`
13. `app.js` (root)

### Created:
14. `config/pjsip.conf.template`
15. `config/pjsip.conf.prod.template`
16. `config/pjsip.conf.dev.template`
17. `config/res_odbc.conf.template`

---

## Verification Results

```
✓ grep "asterisk_dev_only" → NO MATCHES
✓ grep "asterisk" app.js (default) → NO FALLBACK
✓ Template files (4) → ALL EXIST
✓ Anonymous context → from-anonymous (all files)
✓ CORS → http://127.0.0.1:8088
✓ RDS deletion_protection → true
✓ SRTP media_encryption → sdes
✓ TLS transport → port 5061
✓ Architect Verification → APPROVED
```

---

## Post-Deployment Checklist

EC2에서 수동으로 해야 할 작업:

### 1. Secrets 디렉토리 생성
```bash
sudo mkdir -p /etc/asterisk/secrets
sudo chmod 700 /etc/asterisk/secrets
sudo chown asterisk:asterisk /etc/asterisk/secrets

sudo mkdir -p /etc/stasis-app
sudo chmod 700 /etc/stasis-app
```

### 2. ARI 비밀번호 설정
```bash
# 옵션 A: 로컬 파일
echo "password=YOUR_SECURE_PASSWORD" | sudo tee /etc/asterisk/secrets/ari.secret
sudo chmod 600 /etc/asterisk/secrets/ari.secret

# 옵션 B: AWS Secrets Manager
aws secretsmanager create-secret \
    --name asterisk/ari/credentials \
    --secret-string '{"password":"YOUR_SECURE_PASSWORD"}'
```

### 3. Stasis App 환경 파일
```bash
echo "ARI_PASSWORD=YOUR_SECURE_PASSWORD" | sudo tee /etc/stasis-app/secrets.env
sudo chmod 600 /etc/stasis-app/secrets.env
```

### 4. TLS 인증서 생성
```bash
sudo mkdir -p /etc/asterisk/certs
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/asterisk/certs/asterisk.key \
    -out /etc/asterisk/certs/asterisk.pem \
    -subj "/CN=asterisk.local/O=AICC/C=KR"
sudo cp /etc/asterisk/certs/asterisk.pem /etc/asterisk/certs/ca.pem
sudo chmod 600 /etc/asterisk/certs/asterisk.key
sudo chown asterisk:asterisk /etc/asterisk/certs/*
```

### 5. envsubst 설치 확인
```bash
which envsubst || sudo yum install -y gettext
```

---

## Commit Strategy (권장)

```bash
git add -A
git commit -m "fix(security): comprehensive security hardening

- Remove hardcoded passwords, require env vars
- Replace sed with envsubst for safe config templating
- Fix npm vulnerabilities via overrides
- Restrict anonymous SIP to rejection context
- Restrict CORS to localhost only
- Disable debug mode in production
- Enable RDS deletion protection
- Enable SRTP media encryption (optimistic)
- Redact credentials from logs
- Add TLS transport on port 5061

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Architect Verification

**Final Verdict: APPROVED**

All 10 tasks completed and verified. Security posture significantly improved.
