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

locals {
  public_subnet_ids = length(data.aws_subnets.public.ids) >= 2 ? data.aws_subnets.public.ids : var.subnet_ids
}

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

resource "aws_iam_role_policy_attachment" "secrets" {
  role       = aws_iam_role.asterisk_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/SecretsManagerReadWrite"
}

resource "aws_iam_instance_profile" "asterisk" {
  name = "asterisk-ec2-profile"
  role = aws_iam_role.asterisk_ec2.name
}

module "ec2_primary" {
  source = "./modules/asterisk-ec2"

  name                    = "primary"
  subnet_id               = local.public_subnet_ids[0]
  security_group_id       = var.ec2_security_group_id
  instance_type           = "t3.small"
  key_name                = var.key_name
  ami_id                  = data.aws_ami.amazon_linux_2023.id
  iam_instance_profile    = aws_iam_instance_profile.asterisk.name
  environment             = var.environment
  project_name            = var.project_name
  eip_allocation_id       = data.aws_eip.asterisk.id
  rds_endpoint            = aws_db_instance.asterisk_mysql.endpoint
  rds_password_secret_arn = aws_secretsmanager_secret.rds_credentials.arn
}

module "ec2_standby" {
  source = "./modules/asterisk-ec2"

  name                    = "standby"
  subnet_id               = local.public_subnet_ids[1]
  security_group_id       = var.ec2_security_group_id
  instance_type           = "t3.small"
  key_name                = var.key_name
  ami_id                  = data.aws_ami.amazon_linux_2023.id
  iam_instance_profile    = aws_iam_instance_profile.asterisk.name
  environment             = var.environment
  project_name            = var.project_name
  eip_allocation_id       = null
  rds_endpoint            = aws_db_instance.asterisk_mysql.endpoint
  rds_password_secret_arn = aws_secretsmanager_secret.rds_credentials.arn
}

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

output "public_subnet_ids_used" {
  description = "Public subnet IDs used for EC2 instances"
  value       = local.public_subnet_ids
}
