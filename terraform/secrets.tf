# =============================================================================
# AWS Secrets Manager - RDS Credentials
# =============================================================================

# 랜덤 비밀번호 생성
resource "random_password" "db_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Secrets Manager Secret
resource "aws_secretsmanager_secret" "rds_credentials" {
  name        = "asterisk/rds/credentials"
  description = "Asterisk RDS MySQL credentials"

  tags = {
    Name        = "${var.project_name}-rds-credentials"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Secret 값 저장
resource "aws_secretsmanager_secret_version" "rds_credentials" {
  secret_id = aws_secretsmanager_secret.rds_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db_password.result
    host     = aws_db_instance.asterisk_mysql.address
    port     = aws_db_instance.asterisk_mysql.port
    database = var.db_name
  })
}

# EC2에서 Secrets Manager 접근을 위한 IAM Policy (필요 시)
resource "aws_iam_policy" "secrets_read_policy" {
  name        = "${var.project_name}-secrets-read"
  description = "Allow reading Asterisk RDS credentials from Secrets Manager"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = aws_secretsmanager_secret.rds_credentials.arn
      }
    ]
  })
}
