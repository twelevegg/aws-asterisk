# =============================================================================
# Route 53 Health Checks for Primary Instance
# =============================================================================

resource "aws_route53_health_check" "primary" {
  ip_address        = "3.36.250.255"
  port              = 8088
  type              = "TCP"
  request_interval  = 10
  failure_threshold = 3

  tags = {
    Name        = "asterisk-primary-health-check"
    Environment = var.environment
    Project     = var.project_name
  }
}
