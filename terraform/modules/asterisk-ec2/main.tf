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

  monitoring = true

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
    instance_role           = var.name
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
