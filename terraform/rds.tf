# =============================================================================
# RDS MySQL Instance for Asterisk Realtime
# =============================================================================

# RDS Subnet Group
resource "aws_db_subnet_group" "asterisk_subnet_group" {
  name       = "asterisk-rds-subnet-group"
  subnet_ids = var.subnet_ids

  tags = {
    Name        = "asterisk-rds-subnet-group"
    Environment = var.environment
    Project     = var.project_name
  }
}

# RDS MySQL Instance
resource "aws_db_instance" "asterisk_mysql" {
  identifier = "asterisk-realtime-db"

  # Engine
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = var.db_instance_class
  allocated_storage    = var.db_allocated_storage
  storage_type         = "gp2"
  storage_encrypted    = true

  # Database
  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password.result

  # Network
  db_subnet_group_name   = aws_db_subnet_group.asterisk_subnet_group.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  publicly_accessible    = false
  port                   = 3306

  # Availability
  multi_az = false # 비용 절감, 필요 시 true로 변경

  # Backup (프리티어 제한: 최대 1일)
  backup_retention_period = 1
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  # Performance Insights (프리티어에서는 비활성화)
  performance_insights_enabled = false

  # Deletion Protection (프로덕션에서는 true 권장)
  deletion_protection = false
  skip_final_snapshot = true

  # Parameter Group (기본 사용)
  parameter_group_name = "default.mysql8.0"

  tags = {
    Name        = "asterisk-realtime-db"
    Environment = var.environment
    Project     = var.project_name
  }
}
