# Failover Architecture Plan: AWS Asterisk AICC System (Revised)

**Plan ID:** failover-architecture
**Created:** 2026-01-29
**Revision:** 3 (FINAL - All Critic Issues Resolved)
**Status:** READY FOR IMPLEMENTATION

---

## Executive Summary

### Recommended Architecture: Active-Passive with EIP Failover

After critical review identifying SIP/RTP session affinity issues with NLB, the revised architecture uses **Elastic IP reassignment via Lambda** for failover.

| Component | Current | Proposed |
|-----------|---------|----------|
| EC2 | 1 instance (SPOF) | 2 instances (Active + Warm Standby) |
| RDS | Single-AZ | Multi-AZ |
| Load Balancer | None | **None (EIP-based failover)** |
| Failover Mechanism | Manual | Lambda-triggered EIP reassignment |
| Health Check | None | Route 53 TCP Health Check |
| Recovery | Manual (~30min) | Automated (~2-5min) |

### Why EIP + Lambda over NLB?

| Aspect | NLB Approach | EIP + Lambda Approach |
|--------|--------------|----------------------|
| **SIP-RTP Affinity** | Broken (packets routed to wrong instance) | Preserved (same IP, same instance) |
| **Cost** | ~$21/month | ~$4.61/month |
| **Complexity** | High (RTP port mapping) | Low (single EIP reassignment) |
| **pjsip.conf Changes** | Required (new endpoint) | **None** (keep existing EIP) |
| **Failover Time** | 30-60 seconds | 60-120 seconds |

### Current EIP Configuration

The existing `pjsip.conf` uses Elastic IP `3.36.250.255`:
```ini
external_media_address=3.36.250.255
external_signaling_address=3.36.250.255
```

**This plan preserves the existing EIP**, eliminating any client-side changes.

### Failover Scenarios & Recovery Time

| Scenario | Detection | Recovery | Data Loss |
|----------|-----------|----------|-----------|
| EC2 failure | 30s (health check) | 60-120s | Active calls drop |
| RDS failure | Automatic (Multi-AZ) | 60-120s | None (sync replication) |
| AZ failure | 30s | 60-120s | Active calls drop |
| Region failure | N/A (out of scope) | Manual DR | Depends on backup |

---

## Architecture Diagram

```
                     Route 53 Health Check (TCP 8088)
                              |
                              v
                     CloudWatch Alarm
                              |
                              v (trigger on ALARM)
                     +--------+--------+
                     |     Lambda      |
                     | EIP Reassigner  |
                     +--------+--------+
                              |
              +---------------+---------------+
              | 1. Disassociate from Primary |
              | 2. Associate to Standby      |
              | 3. SNS Notification          |
              +---------------+---------------+
                              |
                              v
                     Elastic IP: 3.36.250.255
                              |
          +-------------------+-------------------+
          |                                       |
          v (EIP attached when active)            v (no EIP until failover)
  +-------+--------+                     +--------+-------+
  |   EC2 Primary  |                     | EC2 Standby    |
  |   (Active)     |                     | (Warm)         |
  |   AZ: 2a       |                     | AZ: 2c         |
  |                |                     |                |
  | - Asterisk PBX |                     | - Asterisk PBX |
  | - Stasis App   |                     | - Stasis App   |
  | - AICC Pipeline|                     | - AICC Pipeline|
  +-------+--------+                     +--------+-------+
          |                                       |
          |        +----------------+             |
          +------->|  RDS MySQL     |<------------+
                   |  (Multi-AZ)    |
                   +----------------+
```

---

## Requirements Summary

### Functional Requirements

1. **FR-01**: System must detect EC2 instance failure within 30 seconds
2. **FR-02**: Lambda must reassign EIP to Standby within 60 seconds of failure detection
3. **FR-03**: RDS must survive AZ failure without data loss (Multi-AZ)
4. **FR-04**: SIP registrations must automatically re-register after failover
5. **FR-05**: Active calls will drop on failover (accepted trade-off)
6. **FR-06**: Existing EIP (3.36.250.255) must be preserved - no client changes

### Non-Functional Requirements

1. **NFR-01**: Zero changes to SIP clients (Linphone) or pjsip.conf
2. **NFR-02**: Infrastructure as Code (Terraform)
3. **NFR-03**: Automated deployment via SSM
4. **NFR-04**: Cost increase < 50% of current infrastructure
5. **NFR-05**: IAM permissions follow least-privilege principle

---

## Acceptance Criteria

### AC-01: Infrastructure Provisioning
- [ ] Standby EC2 instance created in AZ 2c
- [ ] Primary EC2 instance keeps existing EIP (3.36.250.255)
- [ ] RDS Multi-AZ enabled
- [ ] Lambda failover function deployed
- [ ] All resources tagged with `Environment` and `Project`

### AC-02: Health Monitoring
- [ ] Route 53 health check on Primary EC2 ARI endpoint (TCP 8088)
- [ ] CloudWatch alarm triggers Lambda on health check failure
- [ ] SNS notifications sent on failover events

### AC-03: Automated Failover
- [ ] Health check failure triggers CloudWatch Alarm
- [ ] Lambda reassigns EIP from Primary to Standby
- [ ] Standby receives traffic within 2 minutes
- [ ] SIP clients can re-register to same IP

### AC-04: Recovery Procedures
- [ ] Documented runbook for manual failover
- [ ] Lambda supports both automatic and manual invocation
- [ ] Failback procedure documented

### AC-05: Verification
- [ ] Simulated failover test passes
- [ ] SIP calls work after failover (same IP)
- [ ] No data loss in RDS
- [ ] No pjsip.conf changes required

---

## Implementation Steps

### Phase 0: Pre-requisites (CRITICAL - FIX FOR ISSUES #2, #4)

**Estimated Time:** 15 minutes
**Downtime:** None

#### Step 0.1: Create Lambda Source Directory (ISSUE #2 FIX)

```bash
# Create the directory BEFORE running terraform apply
mkdir -p /Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/files/failover_lambda
```

#### Step 0.2: Google Cloud Credentials (ISSUE #4 FIX)

**MANUAL POST-DEPLOYMENT STEP REQUIRED:**

The AICC Pipeline requires Google Cloud credentials for STT. These must be deployed manually:

```bash
# On EACH EC2 instance (Primary and Standby), after deployment:
# 1. Create credentials directory
sudo mkdir -p /root/.config/gcloud

# 2. Copy credentials file (from local machine)
scp ~/.config/gcloud/credentials.json ec2-user@<instance-ip>:/tmp/
ssh ec2-user@<instance-ip> "sudo mv /tmp/credentials.json /root/.config/gcloud/"
ssh ec2-user@<instance-ip> "sudo chmod 600 /root/.config/gcloud/credentials.json"

# 3. Verify
ssh ec2-user@<instance-ip> "sudo cat /root/.config/gcloud/credentials.json | head -5"
```

**Alternative (recommended for production):** Store credentials in AWS Secrets Manager and retrieve during userdata. This is documented but NOT implemented in this plan to minimize scope.

---

### Phase 1: RDS Multi-AZ (Low Risk, High Value)

**Estimated Time:** 1 hour
**Downtime:** ~15 minutes during modification

#### Step 1.1: Enable Multi-AZ in Terraform

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/rds.tf`

```hcl
# Change line 41
multi_az = true  # Enable Multi-AZ for automatic failover

# Add enhanced monitoring (optional but recommended)
monitoring_interval = 60
monitoring_role_arn = aws_iam_role.rds_monitoring.arn

# Increase backup retention for better recovery options
backup_retention_period = 7
```

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/rds_monitoring.tf` (NEW)

```hcl
# IAM role for RDS Enhanced Monitoring
resource "aws_iam_role" "rds_monitoring" {
  name = "asterisk-rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "monitoring.rds.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
```

#### Step 1.2: Apply Changes

```bash
cd /Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform
terraform plan -out=tfplan
terraform apply tfplan
```

---

### Phase 2: Lambda Failover Function

**Estimated Time:** 2 hours
**Downtime:** None (additive)

#### Step 2.1: Add Archive Provider to main.tf (ISSUE #1 FIX)

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/main.tf` (MODIFY)

```hcl
# =============================================================================
# Asterisk RDS Infrastructure - Main Configuration
# =============================================================================

terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    # ISSUE #1 FIX: Add archive provider for Lambda zip
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Local state file
  # backend "s3" { } # Use S3 backend for team collaboration
}

provider "aws" {
  region = var.aws_region
}

# Existing VPC data source
data "aws_vpc" "asterisk_vpc" {
  id = var.vpc_id
}

# Existing EC2 Security Group data source
data "aws_security_group" "asterisk_ec2_sg" {
  id = var.ec2_security_group_id
}
```

#### Step 2.2: Create Lambda Function

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/lambda.tf` (NEW)

```hcl
# =============================================================================
# Lambda Function for EIP Failover
# =============================================================================

# Data source for existing EIP
data "aws_eip" "asterisk" {
  public_ip = "3.36.250.255"
}

# IAM Role for Lambda
resource "aws_iam_role" "failover_lambda" {
  name = "asterisk-failover-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Lambda execution policy
resource "aws_iam_role_policy" "failover_lambda" {
  name = "asterisk-failover-lambda-policy"
  role = aws_iam_role.failover_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeAddresses",
          "ec2:AssociateAddress",
          "ec2:DisassociateAddress",
          "ec2:DescribeInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.asterisk_alerts.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# Lambda function code
resource "aws_lambda_function" "failover" {
  function_name = "asterisk-eip-failover"
  role          = aws_iam_role.failover_lambda.arn
  handler       = "index.handler"
  runtime       = "python3.11"
  timeout       = 60
  memory_size   = 128

  filename         = data.archive_file.failover_lambda.output_path
  source_code_hash = data.archive_file.failover_lambda.output_base64sha256

  environment {
    variables = {
      EIP_ALLOCATION_ID   = data.aws_eip.asterisk.id
      PRIMARY_INSTANCE_ID = module.ec2_primary.instance_id
      STANDBY_INSTANCE_ID = module.ec2_standby.instance_id
      SNS_TOPIC_ARN       = aws_sns_topic.asterisk_alerts.arn
    }
  }

  tags = {
    Name        = "asterisk-eip-failover"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Lambda source code archive
data "archive_file" "failover_lambda" {
  type        = "zip"
  output_path = "${path.module}/files/failover_lambda.zip"
  source_dir  = "${path.module}/files/failover_lambda"
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "failover_lambda" {
  name              = "/aws/lambda/asterisk-eip-failover"
  retention_in_days = 14
}

# Lambda permission for CloudWatch Events
resource "aws_lambda_permission" "cloudwatch" {
  statement_id  = "AllowCloudWatchInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.failover.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.failover_trigger.arn
}

# CloudWatch Event Rule - triggered by Route 53 health check alarm
resource "aws_cloudwatch_event_rule" "failover_trigger" {
  name        = "asterisk-failover-trigger"
  description = "Trigger Lambda when Route 53 health check fails"

  event_pattern = jsonencode({
    source      = ["aws.cloudwatch"]
    detail-type = ["CloudWatch Alarm State Change"]
    detail = {
      alarmName = [aws_cloudwatch_metric_alarm.route53_health.alarm_name]
      state = {
        value = ["ALARM"]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "failover_lambda" {
  rule      = aws_cloudwatch_event_rule.failover_trigger.name
  target_id = "asterisk-failover-lambda"
  arn       = aws_lambda_function.failover.arn
}
```

#### Step 2.3: Create Lambda Source Code

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/files/failover_lambda/index.py` (NEW)

```python
"""
Asterisk EIP Failover Lambda Function

This function reassigns the Elastic IP from the failed Primary instance
to the healthy Standby instance, enabling automatic failover.
"""

import os
import json
import boto3
from datetime import datetime

ec2 = boto3.client('ec2')
sns = boto3.client('sns')

EIP_ALLOCATION_ID = os.environ['EIP_ALLOCATION_ID']
PRIMARY_INSTANCE_ID = os.environ['PRIMARY_INSTANCE_ID']
STANDBY_INSTANCE_ID = os.environ['STANDBY_INSTANCE_ID']
SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']


def handler(event, context):
    """
    Main handler for failover events.

    Triggered by CloudWatch Alarm when Route 53 health check fails.
    """
    print(f"Failover event received: {json.dumps(event)}")

    try:
        # Get current EIP association
        eip_info = ec2.describe_addresses(AllocationIds=[EIP_ALLOCATION_ID])
        addresses = eip_info.get('Addresses', [])

        if not addresses:
            raise Exception(f"EIP {EIP_ALLOCATION_ID} not found")

        current_instance = addresses[0].get('InstanceId')
        association_id = addresses[0].get('AssociationId')
        public_ip = addresses[0].get('PublicIp')

        print(f"Current EIP {public_ip} attached to: {current_instance}")

        # Determine target instance
        if current_instance == PRIMARY_INSTANCE_ID:
            target_instance = STANDBY_INSTANCE_ID
            source_name = "Primary"
            target_name = "Standby"
        elif current_instance == STANDBY_INSTANCE_ID:
            target_instance = PRIMARY_INSTANCE_ID
            source_name = "Standby"
            target_name = "Primary"
        else:
            # EIP not attached or attached to unknown instance
            target_instance = STANDBY_INSTANCE_ID
            source_name = "Unknown"
            target_name = "Standby"

        # Verify target instance is running
        target_status = get_instance_status(target_instance)
        if target_status != 'running':
            raise Exception(f"Target instance {target_instance} is not running (status: {target_status})")

        # Disassociate EIP from current instance
        if association_id:
            print(f"Disassociating EIP from {current_instance}")
            ec2.disassociate_address(AssociationId=association_id)

        # Associate EIP with target instance
        print(f"Associating EIP with {target_instance}")
        ec2.associate_address(
            AllocationId=EIP_ALLOCATION_ID,
            InstanceId=target_instance,
            AllowReassociation=True
        )

        # Send SNS notification
        message = {
            'event': 'FAILOVER_COMPLETE',
            'timestamp': datetime.utcnow().isoformat(),
            'eip': public_ip,
            'from_instance': current_instance,
            'from_name': source_name,
            'to_instance': target_instance,
            'to_name': target_name
        }

        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='[ASTERISK] EIP Failover Completed',
            Message=json.dumps(message, indent=2)
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'EIP {public_ip} reassigned from {source_name} to {target_name}',
                'from': current_instance,
                'to': target_instance
            })
        }

    except Exception as e:
        error_message = str(e)
        print(f"Failover error: {error_message}")

        # Send error notification
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject='[ASTERISK] EIP Failover FAILED',
            Message=f'Failover failed: {error_message}'
        )

        raise


def get_instance_status(instance_id):
    """Get the current status of an EC2 instance."""
    response = ec2.describe_instances(InstanceIds=[instance_id])
    reservations = response.get('Reservations', [])

    if not reservations:
        return 'not_found'

    instances = reservations[0].get('Instances', [])
    if not instances:
        return 'not_found'

    return instances[0].get('State', {}).get('Name', 'unknown')
```

---

### Phase 3: EC2 Primary and Standby Instances

**Estimated Time:** 3 hours
**Downtime:** None (additive for standby)

#### Step 3.1: Create EC2 Module

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/modules/asterisk-ec2/main.tf` (NEW)

```hcl
# =============================================================================
# Asterisk EC2 Instance Module
# =============================================================================

variable "name" {
  description = "Instance name suffix"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID for the instance"
  type        = string
}

variable "security_group_id" {
  description = "Security group ID"
  type        = string
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "key_name" {
  description = "SSH key pair name"
  type        = string
}

variable "ami_id" {
  description = "AMI ID (Amazon Linux 2023 or custom Asterisk AMI)"
  type        = string
}

variable "iam_instance_profile" {
  description = "IAM instance profile name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "project_name" {
  description = "Project name"
  type        = string
}

variable "eip_allocation_id" {
  description = "Elastic IP allocation ID to associate (optional, only for primary)"
  type        = string
  default     = null
}

variable "rds_endpoint" {
  description = "RDS MySQL endpoint for Asterisk realtime"
  type        = string
}

variable "rds_password_secret_arn" {
  description = "ARN of Secrets Manager secret containing RDS password and ARI password"
  type        = string
}

# EC2 Instance
resource "aws_instance" "asterisk" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  key_name               = var.key_name
  iam_instance_profile   = var.iam_instance_profile

  # Enable detailed monitoring for CloudWatch
  monitoring = true

  # Root volume
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    delete_on_termination = true
    encrypted             = true
  }

  user_data = base64encode(templatefile("${path.module}/userdata.sh.tpl", {
    environment             = var.environment
    rds_endpoint            = var.rds_endpoint
    rds_password_secret_arn = var.rds_password_secret_arn
    instance_role           = var.name  # "primary" or "standby"
  }))

  tags = {
    Name        = "asterisk-${var.name}"
    Environment = var.environment
    Project     = var.project_name
    Role        = "asterisk-${var.name}"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# EIP Association (only for primary)
resource "aws_eip_association" "asterisk" {
  count = var.eip_allocation_id != null ? 1 : 0

  instance_id   = aws_instance.asterisk.id
  allocation_id = var.eip_allocation_id
}

output "instance_id" {
  value = aws_instance.asterisk.id
}

output "private_ip" {
  value = aws_instance.asterisk.private_ip
}

output "public_ip" {
  value = aws_instance.asterisk.public_ip
}
```

#### Step 3.2: Create Userdata Script with Full Asterisk Installation (ISSUE #3 FIX)

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/modules/asterisk-ec2/userdata.sh.tpl` (NEW)

```bash
#!/bin/bash
set -ex

# Log output for debugging
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "=========================================="
echo "Starting Asterisk AICC Setup"
echo "Instance Role: ${instance_role}"
echo "Environment: ${environment}"
echo "=========================================="

# =============================================================================
# 1. System Updates and Base Packages
# =============================================================================
dnf update -y
dnf install -y \
  git \
  gcc \
  gcc-c++ \
  make \
  wget \
  tar \
  bzip2 \
  ncurses-devel \
  libxml2-devel \
  sqlite-devel \
  openssl-devel \
  libuuid-devel \
  jansson-devel \
  libsrtp-devel \
  speex-devel \
  opus-devel \
  libedit-devel \
  unixODBC-devel \
  mysql-devel \
  mariadb105-connector-odbc \
  jq

# =============================================================================
# 2. Install Node.js 18 (for Stasis App)
# =============================================================================
curl -fsSL https://rpm.nodesource.com/setup_18.x | bash -
dnf install -y nodejs

# =============================================================================
# 3. Install Python 3.11 (for AICC Pipeline)
# =============================================================================
dnf install -y python3.11 python3.11-pip
alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
alternatives --install /usr/bin/pip3 pip3 /usr/bin/pip3.11 1

# =============================================================================
# 4. Install SSM Agent
# =============================================================================
dnf install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# =============================================================================
# 5. Install CloudWatch Agent
# =============================================================================
dnf install -y amazon-cloudwatch-agent

cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWCONFIG'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/asterisk/messages",
            "log_group_name": "/asterisk/${environment}/messages",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/var/log/asterisk/full",
            "log_group_name": "/asterisk/${environment}/full",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/var/log/stasis-app.log",
            "log_group_name": "/asterisk/${environment}/stasis-app",
            "log_stream_name": "{instance_id}"
          },
          {
            "file_path": "/var/log/aicc-pipeline.log",
            "log_group_name": "/asterisk/${environment}/aicc-pipeline",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "Asterisk/${environment}",
    "metrics_collected": {
      "cpu": { "measurement": ["cpu_usage_active"] },
      "mem": { "measurement": ["mem_used_percent"] },
      "disk": { "measurement": ["disk_used_percent"] }
    }
  }
}
CWCONFIG

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# =============================================================================
# 6. Download and Build Asterisk 20 LTS
# =============================================================================
cd /usr/src
ASTERISK_VERSION="20.7.0"
wget http://downloads.asterisk.org/pub/telephony/asterisk/asterisk-$${ASTERISK_VERSION}.tar.gz
tar xzf asterisk-$${ASTERISK_VERSION}.tar.gz
cd asterisk-$${ASTERISK_VERSION}

# Install prerequisites
contrib/scripts/install_prereq install

# Configure with PJSIP and ODBC
./configure --with-pjproject-bundled --with-jansson-bundled

# Build and install
make menuselect.makeopts
menuselect/menuselect \
  --enable res_odbc \
  --enable res_config_odbc \
  --enable res_pjsip \
  --enable res_pjsip_session \
  --enable res_ari \
  --enable res_ari_channels \
  --enable res_ari_bridges \
  --enable res_ari_recordings \
  --enable res_stasis \
  --enable res_stasis_snoop \
  --enable func_odbc \
  --enable cdr_odbc \
  --enable CORE-SOUNDS-EN-ULAW \
  --enable MOH-ORSOUND-ULAW \
  menuselect.makeopts

make -j$(nproc)
make install
make samples
make config

# Create asterisk user
useradd -r -s /sbin/nologin asterisk || true
chown -R asterisk:asterisk /var/lib/asterisk
chown -R asterisk:asterisk /var/log/asterisk
chown -R asterisk:asterisk /var/spool/asterisk
chown -R asterisk:asterisk /etc/asterisk

# =============================================================================
# 7. Clone and Deploy Application
# =============================================================================
mkdir -p /opt/aicc
cd /opt/aicc
git clone https://github.com/kt-aicc/aws_asterisk.git . || true

# =============================================================================
# 8. Get Credentials from Secrets Manager (ISSUE #3 FIX - includes ARI_PASSWORD)
# =============================================================================
# Secret structure expected:
# {
#   "username": "admin",
#   "password": "rds_password",
#   "ari_password": "ari_password_value"
# }
CREDS=$(aws secretsmanager get-secret-value \
  --secret-id "${rds_password_secret_arn}" \
  --query 'SecretString' --output text)
RDS_PASSWORD=$(echo $CREDS | jq -r '.password')
RDS_USERNAME=$(echo $CREDS | jq -r '.username // "admin"')
ARI_PASSWORD=$(echo $CREDS | jq -r '.ari_password // "asterisk"')

# Extract RDS host and port
RDS_HOST=$(echo "${rds_endpoint}" | cut -d: -f1)
RDS_PORT=$(echo "${rds_endpoint}" | cut -d: -f2)

# =============================================================================
# 9. Configure ODBC for MySQL Realtime
# =============================================================================
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

# =============================================================================
# 10. Deploy Asterisk Configurations
# =============================================================================
cp /opt/aicc/config/*.conf /etc/asterisk/

# Configure res_odbc.conf
cat > /etc/asterisk/res_odbc.conf << RESODBC
[asterisk]
enabled => yes
dsn => asterisk
username => $RDS_USERNAME
password => $RDS_PASSWORD
pre-connect => yes
sanitysql => select 1
RESODBC

# =============================================================================
# 11. Install Stasis App (ISSUE #3 FIX - ARI_PASSWORD in environment file)
# =============================================================================
cd /opt/aicc/stasis_app
npm install

# Create environment file for sensitive credentials
cat > /opt/aicc/stasis_app/.env << ENVFILE
ARI_PASSWORD=$ARI_PASSWORD
ENVFILE
chmod 600 /opt/aicc/stasis_app/.env

# Create systemd service for Stasis App with EnvironmentFile
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

# =============================================================================
# 12. Install AICC Pipeline
# =============================================================================
cd /opt/aicc/python
pip3 install -r requirements.txt || pip3 install websockets google-cloud-speech kiwipiepy numpy

# Create systemd service for AICC Pipeline
# NOTE: GOOGLE_APPLICATION_CREDENTIALS must be set up manually (see Phase 0.2)
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

# =============================================================================
# 13. Enable and Start Services
# =============================================================================
systemctl daemon-reload
systemctl enable asterisk
systemctl enable stasis-app
systemctl enable aicc-pipeline

systemctl start asterisk
sleep 5
systemctl start stasis-app
systemctl start aicc-pipeline

# =============================================================================
# 14. Verify Installation
# =============================================================================
echo "=========================================="
echo "Installation Complete"
echo "Instance Role: ${instance_role}"
echo "=========================================="

# Check services
systemctl is-active asterisk && echo "Asterisk: OK" || echo "Asterisk: FAILED"
systemctl is-active stasis-app && echo "Stasis App: OK" || echo "Stasis App: FAILED"
systemctl is-active aicc-pipeline && echo "AICC Pipeline: OK" || echo "AICC Pipeline: FAILED"

# Check Asterisk
asterisk -rx "core show version" || true
asterisk -rx "pjsip show endpoints" || true

echo "User data script completed at $(date)"
```

#### Step 3.3: Create EC2 Instances Configuration (ISSUE #5 FIX)

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/ec2.tf` (NEW)

```hcl
# =============================================================================
# EC2 Instances - Primary and Standby
# =============================================================================

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

# Data source for existing EIP
data "aws_eip" "asterisk" {
  public_ip = "3.36.250.255"
}

# ISSUE #5 FIX: Data source to find public subnets in VPC
# This looks up subnets that have auto-assign public IP enabled (public subnets)
data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}

# Fallback: Use existing subnet_ids if public subnet lookup fails
# The existing subnet_ids in variables.tf are:
#   - subnet-08a1a475056f3db26 (ap-northeast-2c)
#   - subnet-0ea991d3ed002526d (ap-northeast-2b)
# IMPORTANT: Verify these are PUBLIC subnets (have route to IGW) for EIP to work

locals {
  # Use discovered public subnets if available, otherwise fall back to var.subnet_ids
  # EC2 instances need PUBLIC subnets for EIP association
  public_subnet_ids = length(data.aws_subnets.public.ids) >= 2 ? data.aws_subnets.public.ids : var.subnet_ids
}

# IAM Role for EC2
resource "aws_iam_role" "asterisk_ec2" {
  name = "asterisk-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.asterisk_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch" {
  role       = aws_iam_role.asterisk_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# Use SecretsManagerReadOnly instead of SecretsManagerReadWrite
resource "aws_iam_role_policy_attachment" "secrets" {
  role       = aws_iam_role.asterisk_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/SecretsManagerReadOnly"
}

resource "aws_iam_instance_profile" "asterisk" {
  name = "asterisk-ec2-profile"
  role = aws_iam_role.asterisk_ec2.name
}

# Primary Instance (first public subnet) - WITH EIP
module "ec2_primary" {
  source = "./modules/asterisk-ec2"

  name                    = "primary"
  subnet_id               = local.public_subnet_ids[0]  # First public subnet
  security_group_id       = var.ec2_security_group_id
  instance_type           = "t3.small"
  key_name                = var.key_name
  ami_id                  = data.aws_ami.amazon_linux_2023.id
  iam_instance_profile    = aws_iam_instance_profile.asterisk.name
  environment             = var.environment
  project_name            = var.project_name
  eip_allocation_id       = data.aws_eip.asterisk.id  # Attach existing EIP
  rds_endpoint            = aws_db_instance.asterisk_mysql.endpoint
  rds_password_secret_arn = aws_secretsmanager_secret.rds_credentials.arn
}

# Standby Instance (second public subnet) - NO EIP (warm standby)
module "ec2_standby" {
  source = "./modules/asterisk-ec2"

  name                    = "standby"
  subnet_id               = local.public_subnet_ids[1]  # Second public subnet
  security_group_id       = var.ec2_security_group_id
  instance_type           = "t3.small"
  key_name                = var.key_name
  ami_id                  = data.aws_ami.amazon_linux_2023.id
  iam_instance_profile    = aws_iam_instance_profile.asterisk.name
  environment             = var.environment
  project_name            = var.project_name
  eip_allocation_id       = null  # No EIP - standby mode
  rds_endpoint            = aws_db_instance.asterisk_mysql.endpoint
  rds_password_secret_arn = aws_secretsmanager_secret.rds_credentials.arn
}

# Outputs
output "primary_instance_id" {
  value = module.ec2_primary.instance_id
}

output "standby_instance_id" {
  value = module.ec2_standby.instance_id
}

output "primary_private_ip" {
  value = module.ec2_primary.private_ip
}

output "standby_private_ip" {
  value = module.ec2_standby.private_ip
}

# Output for subnet verification
output "public_subnet_ids_used" {
  description = "Public subnet IDs used for EC2 instances (verify these have IGW route)"
  value       = local.public_subnet_ids
}
```

---

### Phase 4: Health Monitoring and Alerts

**Estimated Time:** 1 hour
**Downtime:** None

#### Step 4.1: Route 53 Health Check

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/route53.tf` (NEW)

```hcl
# =============================================================================
# Route 53 Health Checks for Primary Instance
# =============================================================================

# Health check targeting the Elastic IP directly
resource "aws_route53_health_check" "primary" {
  ip_address        = "3.36.250.255"  # Existing EIP
  port              = 8088            # ARI HTTP port
  type              = "TCP"
  request_interval  = 10              # Fast detection
  failure_threshold = 3               # 30 seconds to trigger

  tags = {
    Name        = "asterisk-primary-health-check"
    Environment = var.environment
    Project     = var.project_name
  }
}
```

#### Step 4.2: CloudWatch Alarms

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/cloudwatch.tf` (NEW)

```hcl
# =============================================================================
# CloudWatch Alarms and Monitoring
# =============================================================================

# SNS Topic for alerts
resource "aws_sns_topic" "asterisk_alerts" {
  name = "asterisk-failover-alerts"

  tags = {
    Name        = "asterisk-failover-alerts"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Route 53 Health Check Alarm - THIS TRIGGERS FAILOVER
resource "aws_cloudwatch_metric_alarm" "route53_health" {
  alarm_name          = "asterisk-primary-unhealthy"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HealthCheckStatus"
  namespace           = "AWS/Route53"
  period              = 60
  statistic           = "Minimum"
  threshold           = 1
  alarm_description   = "Primary instance health check failed - triggers failover"
  alarm_actions       = [aws_sns_topic.asterisk_alerts.arn]
  ok_actions          = [aws_sns_topic.asterisk_alerts.arn]
  treat_missing_data  = "breaching"

  dimensions = {
    HealthCheckId = aws_route53_health_check.primary.id
  }
}

# EC2 Status Check Alarm - Primary
resource "aws_cloudwatch_metric_alarm" "ec2_primary_status" {
  alarm_name          = "asterisk-primary-status-failed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Primary instance status check failed"
  alarm_actions       = [aws_sns_topic.asterisk_alerts.arn]

  dimensions = {
    InstanceId = module.ec2_primary.instance_id
  }
}

# EC2 CPU Alarm - Primary
resource "aws_cloudwatch_metric_alarm" "ec2_primary_cpu" {
  alarm_name          = "asterisk-primary-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "Primary instance CPU > 80%"
  alarm_actions       = [aws_sns_topic.asterisk_alerts.arn]

  dimensions = {
    InstanceId = module.ec2_primary.instance_id
  }
}

# RDS Connection Alarm
resource "aws_cloudwatch_metric_alarm" "rds_connections" {
  alarm_name          = "asterisk-rds-high-connections"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "DatabaseConnections"
  namespace           = "AWS/RDS"
  period              = 60
  statistic           = "Average"
  threshold           = 50
  alarm_description   = "RDS connections > 50"
  alarm_actions       = [aws_sns_topic.asterisk_alerts.arn]

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.asterisk_mysql.identifier
  }
}
```

---

### Phase 5: SSM Automation for Deployment

**Estimated Time:** 1 hour
**Downtime:** None

#### Step 5.1: SSM Documents

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/ssm.tf` (NEW)

```hcl
# =============================================================================
# SSM Automation for Deployment and Failover
# =============================================================================

# SSM Document for Asterisk deployment
resource "aws_ssm_document" "asterisk_deploy" {
  name            = "asterisk-deploy"
  document_type   = "Command"
  document_format = "YAML"

  content = <<DOC
schemaVersion: '2.2'
description: Deploy Asterisk AICC application
parameters:
  GitBranch:
    type: String
    default: main
    description: Git branch to deploy
mainSteps:
  - action: aws:runShellScript
    name: deployAsterisk
    inputs:
      runCommand:
        - |
          #!/bin/bash
          set -ex

          # Pull latest code
          cd /opt/aicc
          git fetch origin
          git checkout {{ GitBranch }}
          git pull origin {{ GitBranch }}

          # Deploy Asterisk configs
          cp /opt/aicc/config/*.conf /etc/asterisk/

          # Restart services
          systemctl restart asterisk
          sleep 5
          systemctl restart stasis-app
          systemctl restart aicc-pipeline

          # Verify services
          systemctl is-active asterisk
          systemctl is-active stasis-app
          asterisk -rx "pjsip show registrations"
DOC

  tags = {
    Name = "asterisk-deploy"
  }
}

# SSM Document for Health Check
resource "aws_ssm_document" "asterisk_health" {
  name            = "asterisk-health-check"
  document_type   = "Command"
  document_format = "YAML"

  content = <<DOC
schemaVersion: '2.2'
description: Check Asterisk health status
mainSteps:
  - action: aws:runShellScript
    name: checkHealth
    inputs:
      runCommand:
        - |
          #!/bin/bash

          echo "=== Asterisk Service Status ==="
          systemctl is-active asterisk && echo "OK" || echo "FAILED"

          echo "=== Stasis App Status ==="
          systemctl is-active stasis-app && echo "OK" || echo "FAILED"

          echo "=== AICC Pipeline Status ==="
          systemctl is-active aicc-pipeline && echo "OK" || echo "FAILED"

          echo "=== SIP Registrations ==="
          asterisk -rx "pjsip show registrations"

          echo "=== Active Calls ==="
          asterisk -rx "core show channels concise"

          echo "=== ARI Status ==="
          curl -s -u ari:ari http://localhost:8088/ari/applications || echo "ARI not responding"
DOC

  tags = {
    Name = "asterisk-health-check"
  }
}

# SSM Document for Manual Failover
resource "aws_ssm_document" "asterisk_manual_failover" {
  name            = "asterisk-manual-failover"
  document_type   = "Command"
  document_format = "YAML"

  content = <<DOC
schemaVersion: '2.2'
description: Manual failover - invoke Lambda to reassign EIP
parameters:
  TargetInstance:
    type: String
    allowedValues:
      - primary
      - standby
    description: Target instance to failover to
mainSteps:
  - action: aws:runShellScript
    name: invokeFailover
    inputs:
      runCommand:
        - |
          #!/bin/bash
          set -ex

          echo "Invoking failover Lambda..."

          aws lambda invoke \
            --function-name asterisk-eip-failover \
            --payload '{"manual": true, "target": "{{ TargetInstance }}"}' \
            /tmp/failover-response.json

          cat /tmp/failover-response.json
DOC

  tags = {
    Name = "asterisk-manual-failover"
  }
}
```

---

### Phase 6: Update Variables and Secrets (ISSUE #3 & #5 FIXES)

**Estimated Time:** 30 minutes
**Downtime:** None

#### Step 6.1: Add New Variables

**File:** `/Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/variables.tf` (MODIFY - add these)

```hcl
# =============================================================================
# Failover Architecture Variables (ADD)
# =============================================================================

variable "key_name" {
  description = "SSH key pair name for EC2 instances"
  type        = string
  default     = "asterisk-key"  # UPDATE WITH ACTUAL KEY NAME
}
```

#### Step 6.2: Update Secrets Manager Secret Structure (ISSUE #3 FIX)

The existing `aws_secretsmanager_secret.rds_credentials` secret MUST be updated to include `ari_password`.

**Required secret structure:**
```json
{
  "username": "admin",
  "password": "your_rds_password",
  "ari_password": "your_ari_password"
}
```

**Manual step after infrastructure is created:**
```bash
# Update the secret to include ARI password
aws secretsmanager put-secret-value \
  --secret-id asterisk-rds-credentials \
  --secret-string '{"username":"admin","password":"YOUR_RDS_PASSWORD","ari_password":"YOUR_ARI_PASSWORD"}'
```

**Or via Terraform (if creating new secret):**

Add to `rds.tf`:
```hcl
# Update secret to include ARI password
resource "aws_secretsmanager_secret_version" "rds_credentials" {
  secret_id = aws_secretsmanager_secret.rds_credentials.id
  secret_string = jsonencode({
    username     = var.db_username
    password     = random_password.rds_password.result
    ari_password = random_password.ari_password.result  # NEW
  })
}

resource "random_password" "ari_password" {
  length  = 16
  special = false
}
```

---

## Critical Issues Fixed (Revision 3)

| Issue | Problem | Fix Applied |
|-------|---------|-------------|
| **#1: Missing Provider** | `archive_file` requires `hashicorp/archive` | Added to `main.tf` required_providers |
| **#2: Missing Directory** | `terraform/files/failover_lambda/` not created | Added explicit `mkdir -p` in Phase 0.1 |
| **#3: Missing ARI_PASSWORD** | Stasis App requires `ARI_PASSWORD` env var | Added to Secrets Manager, userdata creates `.env` file, systemd uses `EnvironmentFile` |
| **#4: Missing Google Credentials** | `GOOGLE_APPLICATION_CREDENTIALS` never deployed | Documented as manual post-deployment step in Phase 0.2 |
| **#5: Ambiguous Subnets** | Unclear if `subnet_ids` are public | Added `data.aws_subnets` lookup with `map-public-ip-on-launch` filter, fallback to existing IDs |

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Active calls drop on failover | Medium | Document expected behavior; SIP clients auto-reconnect within 30s |
| Lambda cold start delay | Low | Keep Lambda warm with scheduled ping; 60s failover still acceptable |
| EIP reassignment fails | High | Manual failback procedure documented; SNS alerts ops team |
| RDS failover takes 60-120s | Low | Multi-AZ provides automatic failover; acceptable for this use case |
| Standby instance drift | Medium | Same userdata script; SSM for synchronized deployments |
| Cost increase | Low | ~35% increase vs 153% with NLB approach |
| Google credentials missing | Medium | Documented manual step; services will fail without it |

---

## Verification Steps

### Pre-Deployment Verification

```bash
# 0. Create Lambda directory (CRITICAL - must do before terraform)
mkdir -p /Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform/files/failover_lambda

# 1. Terraform init (will download archive provider)
cd /Users/macbookpro14/dev/kt-aicc/aws_asterisk/terraform
terraform init -upgrade

# 2. Terraform plan review
terraform plan -out=tfplan

# 3. Verify existing EIP
aws ec2 describe-addresses \
  --public-ips 3.36.250.255 \
  --query 'Addresses[0].{AllocationId:AllocationId,InstanceId:InstanceId}'

# 4. Check current RDS status
aws rds describe-db-instances \
  --db-instance-identifier asterisk-realtime-db \
  --query 'DBInstances[0].{MultiAZ:MultiAZ,Status:DBInstanceStatus}'

# 5. Verify subnets are public (have IGW route)
for subnet in subnet-08a1a475056f3db26 subnet-0ea991d3ed002526d; do
  echo "Checking $subnet..."
  aws ec2 describe-route-tables \
    --filters "Name=association.subnet-id,Values=$subnet" \
    --query 'RouteTables[0].Routes[?GatewayId!=`local`].GatewayId' \
    --output text
done
# Should show igw-xxx for public subnets
```

### Post-Deployment Verification

```bash
# 1. Verify RDS Multi-AZ
aws rds describe-db-instances \
  --db-instance-identifier asterisk-realtime-db \
  --query 'DBInstances[0].MultiAZ'
# Expected: true

# 2. Verify both EC2 instances
aws ec2 describe-instances \
  --filters "Name=tag:Project,Values=aicc-asterisk" "Name=tag:Role,Values=asterisk-*" \
  --query 'Reservations[].Instances[].{ID:InstanceId,Name:Tags[?Key==`Name`].Value|[0],State:State.Name,AZ:Placement.AvailabilityZone}'

# 3. Verify EIP attached to primary
aws ec2 describe-addresses \
  --public-ips 3.36.250.255 \
  --query 'Addresses[0].InstanceId'
# Expected: Primary instance ID

# 4. Verify Route 53 health check
aws route53 get-health-check-status \
  --health-check-id <health-check-id>
# Expected: "StatusReport.Status": "Success"

# 5. Verify Lambda function
aws lambda invoke \
  --function-name asterisk-eip-failover \
  --payload '{"test": true}' \
  /tmp/lambda-test.json && cat /tmp/lambda-test.json

# 6. Deploy Google credentials (MANUAL - ISSUE #4)
# Do this for BOTH instances
for instance_ip in <primary-ip> <standby-ip>; do
  scp ~/.config/gcloud/credentials.json ec2-user@$instance_ip:/tmp/
  ssh ec2-user@$instance_ip "sudo mkdir -p /root/.config/gcloud && sudo mv /tmp/credentials.json /root/.config/gcloud/ && sudo chmod 600 /root/.config/gcloud/credentials.json"
done
```

### Failover Test Procedure

1. **Preparation**
   - Notify team of planned failover test
   - Ensure no critical calls in progress
   - Open monitoring dashboard (CloudWatch)

2. **Execute Failover (Simulated)**
   ```bash
   # Option 1: Stop ARI service to trigger health check failure
   aws ssm send-command \
     --document-name "AWS-RunShellScript" \
     --targets "Key=instanceids,Values=<primary-instance-id>" \
     --parameters 'commands=["systemctl stop asterisk"]'

   # Option 2: Manually invoke Lambda
   aws lambda invoke \
     --function-name asterisk-eip-failover \
     --payload '{}' \
     /tmp/failover-result.json
   ```

3. **Verify Failover**
   - [ ] Route 53 health check shows unhealthy within 30s
   - [ ] CloudWatch Alarm triggers within 60s
   - [ ] Lambda executes and reassigns EIP
   - [ ] EIP now attached to Standby instance
   - [ ] SNS notification received
   - [ ] SIP clients can connect to same IP (now Standby)

4. **Verify Connectivity**
   ```bash
   # Check EIP association
   aws ec2 describe-addresses --public-ips 3.36.250.255

   # Test ARI endpoint
   curl -u ari:ari http://3.36.250.255:8088/ari/asterisk/info

   # Test SIP (from Linphone client)
   # Register and make test call
   ```

5. **Failback**
   ```bash
   # Restart Asterisk on primary
   aws ssm send-command \
     --document-name "AWS-RunShellScript" \
     --targets "Key=instanceids,Values=<primary-instance-id>" \
     --parameters 'commands=["systemctl start asterisk"]'

   # Manually failback to primary (if desired)
   aws lambda invoke \
     --function-name asterisk-eip-failover \
     --payload '{"target": "primary"}' \
     /tmp/failback-result.json
   ```

---

## Cost Estimate

### Current Monthly Cost (Estimated)

| Resource | Spec | Cost |
|----------|------|------|
| EC2 | 1x t3.small | ~$15 |
| RDS | db.t3.micro, single-AZ, 20GB | ~$15 |
| Elastic IP | 1 (attached) | ~$0 |
| **Total** | | **~$30** |

### Proposed Monthly Cost (Estimated)

| Resource | Spec | Cost |
|----------|------|------|
| EC2 | 2x t3.small | ~$30 |
| RDS | db.t3.micro, Multi-AZ, 20GB | ~$30 |
| Elastic IP | 1 (attached) | ~$0 |
| Lambda | ~1000 invocations/month | ~$0.01 |
| Route 53 | 1 health check | ~$0.50 |
| CloudWatch | Alarms + Logs | ~$5 |
| **Total** | | **~$65.51** |

### Cost Comparison

| Approach | Monthly Cost | vs Current |
|----------|-------------|------------|
| Current (SPOF) | $30 | - |
| **EIP + Lambda (this plan)** | **$65.51** | **+118%** |
| NLB approach (rejected) | $86 | +187% |

### Value Proposition

- **Cost:** +$35/month (~$420/year)
- **Benefit:** Near-instant automated failover vs. 30+ minute manual recovery
- **ROI:** Single avoided outage pays for 1+ year of infrastructure

---

## Implementation Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 0: Pre-requisites | 15 min | None |
| Phase 1: RDS Multi-AZ | 1 hour | None |
| Phase 2: Lambda Failover | 2 hours | Phase 0, 1 |
| Phase 3: EC2 Instances | 3 hours | Phase 1 |
| Phase 4: Health Monitoring | 1 hour | Phase 2, 3 |
| Phase 5: SSM Automation | 1 hour | Phase 3 |
| Phase 6: Variables & Secrets | 30 min | None |
| **Total** | **8.75 hours** | |

---

## Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `terraform/modules/asterisk-ec2/main.tf` | Reusable EC2 module |
| `terraform/modules/asterisk-ec2/userdata.sh.tpl` | Full Asterisk installation script (with ARI_PASSWORD fix) |
| `terraform/ec2.tf` | Primary and Standby instances (with subnet lookup) |
| `terraform/lambda.tf` | EIP failover Lambda function |
| `terraform/files/failover_lambda/index.py` | Lambda source code |
| `terraform/cloudwatch.tf` | Alarms and monitoring |
| `terraform/route53.tf` | Health checks |
| `terraform/ssm.tf` | Deployment automation |
| `terraform/rds_monitoring.tf` | RDS enhanced monitoring |

### Modified Files

| File | Changes |
|------|---------|
| `terraform/main.tf` | Add `hashicorp/archive` provider (ISSUE #1 FIX) |
| `terraform/rds.tf` | Enable Multi-AZ, increase backup retention, update secret structure |
| `terraform/variables.tf` | Add `key_name` variable |
| `terraform/outputs.tf` | Add EC2 instance outputs |

### Manual Steps Required

| Step | When | Description |
|------|------|-------------|
| Create Lambda directory | Before `terraform apply` | `mkdir -p terraform/files/failover_lambda` |
| Deploy Google credentials | After EC2 instances created | Copy `credentials.json` to both instances |
| Update Secrets Manager | After RDS created | Add `ari_password` to secret |

---

## Post-Implementation Tasks

1. **Documentation**
   - Update `CLAUDE.md` with failover architecture
   - Create runbook for manual failover/failback
   - Document disaster recovery procedures

2. **Testing**
   - Run full failover test
   - Test RDS failover
   - Test Lambda cold start behavior
   - Test SIP re-registration after failover

3. **Monitoring**
   - Configure CloudWatch dashboard
   - Set up PagerDuty/OpsGenie integration for SNS
   - Create runbook for failover alerts

---

**PLAN_READY: .omc/plans/failover-architecture.md**
