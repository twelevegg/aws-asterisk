#!/bin/bash
# =============================================================================
# Asterisk ODBC Setup Script for Amazon Linux 2 / RHEL
# EC2에서 SSM으로 접속하여 실행
# =============================================================================

set -e

echo "=== Asterisk ODBC Setup Script ==="

# -----------------------------------------------------------------------------
# 1. 패키지 설치
# -----------------------------------------------------------------------------
echo "[1/5] Installing ODBC packages..."

# Amazon Linux 2 / RHEL
if command -v yum &> /dev/null; then
    sudo yum install -y unixODBC unixODBC-devel mysql-connector-odbc
# Ubuntu / Debian
elif command -v apt &> /dev/null; then
    sudo apt update
    sudo apt install -y unixodbc unixodbc-dev odbc-mariadb
fi

# -----------------------------------------------------------------------------
# 2. Secrets Manager에서 DB 정보 가져오기
# -----------------------------------------------------------------------------
echo "[2/5] Fetching credentials from Secrets Manager..."

SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id asterisk/rds/credentials \
    --query SecretString \
    --output text)

DB_HOST=$(echo $SECRET_JSON | jq -r '.host')
DB_PORT=$(echo $SECRET_JSON | jq -r '.port')
DB_NAME=$(echo $SECRET_JSON | jq -r '.database')
DB_USER=$(echo $SECRET_JSON | jq -r '.username')
DB_PASS=$(echo $SECRET_JSON | jq -r '.password')

echo "DB Host: $DB_HOST"
echo "DB Port: $DB_PORT"
echo "DB Name: $DB_NAME"

# -----------------------------------------------------------------------------
# 3. ODBC Driver 확인
# -----------------------------------------------------------------------------
echo "[3/5] Configuring ODBC driver..."

# MySQL ODBC 드라이버 경로 찾기
MYSQL_DRIVER=$(find /usr -name "libmyodbc*.so" 2>/dev/null | head -1)

if [ -z "$MYSQL_DRIVER" ]; then
    # 대체 경로 시도
    MYSQL_DRIVER="/usr/lib64/libmyodbc8w.so"
fi

echo "MySQL Driver: $MYSQL_DRIVER"

# /etc/odbcinst.ini 설정
sudo tee /etc/odbcinst.ini > /dev/null << EOF
[MySQL ODBC 8.0 Unicode Driver]
Description = MySQL ODBC 8.0 Unicode Driver
Driver = $MYSQL_DRIVER
Setup = $MYSQL_DRIVER
UsageCount = 1
EOF

# -----------------------------------------------------------------------------
# 4. ODBC DSN 설정
# -----------------------------------------------------------------------------
echo "[4/5] Configuring ODBC DSN..."

sudo tee /etc/odbc.ini > /dev/null << EOF
[asterisk-connector]
Description = Asterisk MySQL Connection
Driver = MySQL ODBC 8.0 Unicode Driver
Server = $DB_HOST
Port = $DB_PORT
Database = $DB_NAME
User = $DB_USER
Password = $DB_PASS
Option = 3
EOF

# 파일 권한 설정 (비밀번호 포함)
sudo chmod 600 /etc/odbc.ini

# -----------------------------------------------------------------------------
# 5. Asterisk res_odbc.conf 업데이트
# -----------------------------------------------------------------------------
echo "[5/5] Updating Asterisk res_odbc.conf..."

# res_odbc.conf에서 password 치환 using envsubst
export DB_PASSWORD="$DB_PASS"
envsubst '${DB_PASSWORD}' < /etc/asterisk/res_odbc.conf.template \
    | sudo tee /etc/asterisk/res_odbc.conf > /dev/null
sudo chmod 640 /etc/asterisk/res_odbc.conf

# -----------------------------------------------------------------------------
# 검증
# -----------------------------------------------------------------------------
echo ""
echo "=== ODBC Configuration Complete ==="
echo ""
echo "Testing ODBC connection (password from DSN)..."
if command -v isql &> /dev/null; then
    echo "SELECT 1;" | isql -v asterisk-connector 2>&1 && \
        echo "ODBC connection successful!" || \
        echo "ODBC connection failed! Check /etc/odbc.ini"
fi

echo ""
echo "Reload Asterisk modules:"
echo "  sudo asterisk -rx 'module reload res_odbc.so'"
echo "  sudo asterisk -rx 'module reload res_config_odbc.so'"
echo "  sudo asterisk -rx 'module reload res_pjsip.so'"
echo ""
echo "Verify with:"
echo "  sudo asterisk -rx 'odbc show'"
echo "  sudo asterisk -rx 'pjsip show endpoints'"
