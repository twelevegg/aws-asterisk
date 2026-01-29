# =============================================================================
# CloudWatch Alarms and Monitoring
# =============================================================================

resource "aws_sns_topic" "asterisk_alerts" {
  name = "asterisk-failover-alerts"

  tags = {
    Name        = "asterisk-failover-alerts"
    Environment = var.environment
    Project     = var.project_name
  }
}

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
