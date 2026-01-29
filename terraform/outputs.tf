# =============================================================================
# Terraform Outputs
# =============================================================================

output "rds_endpoint" {
  description = "RDS MySQL endpoint"
  value       = aws_db_instance.asterisk_mysql.endpoint
}

output "rds_address" {
  description = "RDS MySQL address (without port)"
  value       = aws_db_instance.asterisk_mysql.address
}

output "rds_port" {
  description = "RDS MySQL port"
  value       = aws_db_instance.asterisk_mysql.port
}

output "rds_database_name" {
  description = "RDS database name"
  value       = aws_db_instance.asterisk_mysql.db_name
}

output "rds_security_group_id" {
  description = "RDS Security Group ID"
  value       = aws_security_group.rds_sg.id
}

output "secrets_manager_secret_arn" {
  description = "Secrets Manager secret ARN for RDS credentials"
  value       = aws_secretsmanager_secret.rds_credentials.arn
}

output "secrets_manager_secret_name" {
  description = "Secrets Manager secret name"
  value       = aws_secretsmanager_secret.rds_credentials.name
}

# ODBC 설정에 필요한 정보 출력
output "odbc_connection_info" {
  description = "ODBC connection information for Asterisk"
  value = {
    driver   = "MySQL ODBC 8.0 Unicode Driver"
    server   = aws_db_instance.asterisk_mysql.address
    port     = aws_db_instance.asterisk_mysql.port
    database = aws_db_instance.asterisk_mysql.db_name
    username = var.db_username
    # password는 Secrets Manager에서 조회
  }
}

# =============================================================================
# Failover Architecture Outputs
# =============================================================================

output "route53_health_check_id" {
  description = "Route 53 health check ID"
  value       = aws_route53_health_check.primary.id
}

output "sns_topic_arn" {
  description = "SNS topic ARN for failover alerts"
  value       = aws_sns_topic.asterisk_alerts.arn
}

output "lambda_function_arn" {
  description = "Lambda failover function ARN"
  value       = aws_lambda_function.failover.arn
}

output "elastic_ip" {
  description = "Elastic IP used for failover"
  value       = data.aws_eip.asterisk.public_ip
}
