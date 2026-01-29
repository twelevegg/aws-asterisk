# =============================================================================
# Lambda Function for EIP Failover
# =============================================================================

data "aws_eip" "asterisk" {
  public_ip = "3.36.250.255"
}

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
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.asterisk_alerts.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

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

data "archive_file" "failover_lambda" {
  type        = "zip"
  output_path = "${path.module}/files/failover_lambda.zip"
  source_dir  = "${path.module}/files/failover_lambda"
}

resource "aws_cloudwatch_log_group" "failover_lambda" {
  name              = "/aws/lambda/asterisk-eip-failover"
  retention_in_days = 14
}

resource "aws_lambda_permission" "cloudwatch" {
  statement_id  = "AllowCloudWatchInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.failover.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.failover_trigger.arn
}

resource "aws_cloudwatch_event_rule" "failover_trigger" {
  name        = "asterisk-failover-trigger"
  description = "Trigger Lambda when Route 53 health check fails"

  event_pattern = jsonencode({
    source      = ["aws.cloudwatch"]
    detail-type = ["CloudWatch Alarm State Change"]
    detail = {
      alarmName = [aws_cloudwatch_metric_alarm.route53_health.alarm_name]
      state     = { value = ["ALARM"] }
    }
  })
}

resource "aws_cloudwatch_event_target" "failover_lambda" {
  rule      = aws_cloudwatch_event_rule.failover_trigger.name
  target_id = "asterisk-failover-lambda"
  arn       = aws_lambda_function.failover.arn
}
