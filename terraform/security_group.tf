# =============================================================================
# RDS Security Group
# =============================================================================

resource "aws_security_group" "rds_sg" {
  name        = "asterisk-rds-sg"
  description = "Security group for Asterisk RDS MySQL - EC2 access only"
  vpc_id      = var.vpc_id

  # Inbound: EC2 Security Group에서만 MySQL 접근 허용
  ingress {
    description     = "MySQL from Asterisk EC2"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [var.ec2_security_group_id]
  }

  # Outbound: 기본적으로 필요 없음 (응답은 자동 허용)
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "asterisk-rds-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}
