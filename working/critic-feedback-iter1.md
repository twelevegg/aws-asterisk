# Critic Feedback - Iteration 1

## VERDICT: REJECT

## Critical Issues to Fix

### 1. T1 Missing Script/Secrets Details
- Need complete `get_ari_password.sh` script
- Need `/etc/stasis-app/secrets.env` format
- Need AWS Secrets Manager integration instructions

### 2. T3 npm - ari-client@1.2.0 Does Not Exist
- Must verify available versions with `npm view ari-client versions`
- Likely need npm overrides approach instead

### 3. T2 Template Files Not Created
- Need to create `pjsip.conf.template` from existing config
- Need to create `res_odbc.conf.template`
- Need envsubst package installation step

### 4. T4 Missing Sound File Verification
- Verify `ss-noservice` sound exists
- Add fallback if missing

### 5. T6 Environment Strategy Incomplete
- Need exact file paths
- Need actual YAML syntax
- Need ENVIRONMENT variable setup

### 6. T10 Certificate Generation Missing
- Need openssl commands for self-signed cert
- Need file permissions

### 7. T7 Terraform timestamp() Issue
- Will cause plan diff on every run
- Use static identifier instead

### 8. T9 isql Fix Fails Its Own Criteria
- Password still visible in ps output
- Need proper DSN-based connection

### 9. envsubst Package Dependency
- Add installation step for gettext package

## Action Required
Planner must revise plan addressing all 7 critical issues before next Critic review.
