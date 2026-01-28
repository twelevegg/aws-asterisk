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
  }

  # 로컬 상태 파일 사용
  # backend "s3" { } # 팀 협업 시 S3 backend 사용
}

provider "aws" {
  region = var.aws_region
}

# 기존 VPC 데이터 소스
data "aws_vpc" "asterisk_vpc" {
  id = var.vpc_id
}

# 기존 EC2 Security Group 데이터 소스
data "aws_security_group" "asterisk_ec2_sg" {
  id = var.ec2_security_group_id
}
