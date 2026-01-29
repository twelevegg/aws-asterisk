#!/bin/bash
set -ex

exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "=========================================="
echo "Starting Asterisk AICC Setup"
echo "Instance Role: ${instance_role}"
echo "Environment: ${environment}"
echo "=========================================="

# 1. System Updates and Base Packages
dnf update -y
dnf install -y \
  git gcc gcc-c++ make wget tar bzip2 \
  ncurses-devel libxml2-devel sqlite-devel openssl-devel \
  libuuid-devel jansson-devel libsrtp-devel speex-devel opus-devel \
  libedit-devel unixODBC-devel mysql-devel mariadb105-connector-odbc jq

# 2. Install Node.js 18
curl -fsSL https://rpm.nodesource.com/setup_18.x | bash -
dnf install -y nodejs

# 3. Install Python 3.11
dnf install -y python3.11 python3.11-pip
alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 1

# 4. Install SSM Agent
dnf install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# 5. Install CloudWatch Agent
dnf install -y amazon-cloudwatch-agent

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWCONFIG'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {"file_path": "/var/log/asterisk/messages", "log_group_name": "/asterisk/${environment}/messages", "log_stream_name": "{instance_id}"},
          {"file_path": "/var/log/asterisk/full", "log_group_name": "/asterisk/${environment}/full", "log_stream_name": "{instance_id}"},
          {"file_path": "/var/log/stasis-app.log", "log_group_name": "/asterisk/${environment}/stasis-app", "log_stream_name": "{instance_id}"},
          {"file_path": "/var/log/aicc-pipeline.log", "log_group_name": "/asterisk/${environment}/aicc-pipeline", "log_stream_name": "{instance_id}"}
        ]
      }
    }
  },
  "metrics": {
    "namespace": "Asterisk/${environment}",
    "metrics_collected": {
      "cpu": {"measurement": ["cpu_usage_active"]},
      "mem": {"measurement": ["mem_used_percent"]},
      "disk": {"measurement": ["disk_used_percent"]}
    }
  }
}
CWCONFIG

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# 6. Download and Build Asterisk 20 LTS
cd /usr/src
ASTERISK_VERSION="20.7.0"
wget http://downloads.asterisk.org/pub/telephony/asterisk/asterisk-$${ASTERISK_VERSION}.tar.gz
tar xzf asterisk-$${ASTERISK_VERSION}.tar.gz
cd asterisk-$${ASTERISK_VERSION}

contrib/scripts/install_prereq install

./configure --with-pjproject-bundled --with-jansson-bundled

make menuselect.makeopts
menuselect/menuselect \
  --enable res_odbc --enable res_config_odbc \
  --enable res_pjsip --enable res_pjsip_session \
  --enable res_ari --enable res_ari_channels --enable res_ari_bridges --enable res_ari_recordings \
  --enable res_stasis --enable res_stasis_snoop \
  --enable func_odbc --enable cdr_odbc \
  --enable CORE-SOUNDS-EN-ULAW --enable MOH-ORSOUND-ULAW \
  menuselect.makeopts

make -j$(nproc)
make install
make samples
make config

useradd -r -s /sbin/nologin asterisk || true
chown -R asterisk:asterisk /var/lib/asterisk /var/log/asterisk /var/spool/asterisk /etc/asterisk

# 7. Clone Application
mkdir -p /opt/aicc
cd /opt/aicc
git clone https://github.com/kt-aicc/aws_asterisk.git . || true

# 8. Get Credentials from Secrets Manager
CREDS=$(aws secretsmanager get-secret-value \
  --secret-id "${rds_password_secret_arn}" \
  --query 'SecretString' --output text)
RDS_PASSWORD=$(echo $CREDS | jq -r '.password')
RDS_USERNAME=$(echo $CREDS | jq -r '.username // "admin"')
ARI_PASSWORD=$(echo $CREDS | jq -r '.ari_password // "asterisk"')

RDS_HOST=$(echo "${rds_endpoint}" | cut -d: -f1)
RDS_PORT=$(echo "${rds_endpoint}" | cut -d: -f2)

# 9. Configure ODBC
cat > /etc/odbc.ini << ODBCINI
[asterisk]
Description = MySQL connection to Asterisk Realtime
Driver = MariaDB Unicode
Server = $RDS_HOST
Port = $RDS_PORT
Database = asterisk
User = $RDS_USERNAME
Password = $RDS_PASSWORD
Option = 3
ODBCINI

cat > /etc/odbcinst.ini << ODBCINST
[MariaDB Unicode]
Description = MariaDB Connector/ODBC
Driver = /usr/lib64/libmaodbc.so
ODBCINST

# 10. Deploy Asterisk Configs
cp /opt/aicc/config/*.conf /etc/asterisk/

cat > /etc/asterisk/res_odbc.conf << RESODBC
[asterisk]
enabled => yes
dsn => asterisk
username => $RDS_USERNAME
password => $RDS_PASSWORD
pre-connect => yes
sanitysql => select 1
RESODBC

# 11. Install Stasis App
cd /opt/aicc/stasis_app
npm install

cat > /opt/aicc/stasis_app/.env << ENVFILE
ARI_PASSWORD=$ARI_PASSWORD
ENVFILE
chmod 600 /opt/aicc/stasis_app/.env

cat > /etc/systemd/system/stasis-app.service << 'STASIS'
[Unit]
Description=Asterisk Stasis Application
After=network.target asterisk.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aicc/stasis_app
EnvironmentFile=/opt/aicc/stasis_app/.env
ExecStart=/usr/bin/node app.js
Restart=always
RestartSec=5
StandardOutput=append:/var/log/stasis-app.log
StandardError=append:/var/log/stasis-app.log

[Install]
WantedBy=multi-user.target
STASIS

# 12. Install AICC Pipeline
cd /opt/aicc/python
pip3 install -r requirements.txt || pip3 install websockets google-cloud-speech kiwipiepy numpy

cat > /etc/systemd/system/aicc-pipeline.service << 'PIPELINE'
[Unit]
Description=AICC Audio Pipeline
After=network.target asterisk.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/aicc/python
ExecStart=/usr/bin/python3 -m aicc_pipeline
Restart=always
RestartSec=5
StandardOutput=append:/var/log/aicc-pipeline.log
StandardError=append:/var/log/aicc-pipeline.log
Environment=GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud/credentials.json

[Install]
WantedBy=multi-user.target
PIPELINE

# 13. Enable and Start Services
systemctl daemon-reload
systemctl enable asterisk stasis-app aicc-pipeline
systemctl start asterisk
sleep 5
systemctl start stasis-app aicc-pipeline

# 14. Verify
echo "=========================================="
echo "Installation Complete - ${instance_role}"
echo "=========================================="
systemctl is-active asterisk && echo "Asterisk: OK" || echo "Asterisk: FAILED"
systemctl is-active stasis-app && echo "Stasis App: OK" || echo "Stasis App: FAILED"
systemctl is-active aicc-pipeline && echo "AICC Pipeline: OK" || echo "AICC Pipeline: FAILED"
asterisk -rx "core show version" || true
echo "User data script completed at $(date)"
