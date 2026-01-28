# =============================================================================
# Asterisk RDS Infrastructure - Variables
# =============================================================================

variable "aws_region" {
  description = "AWS Region"
  type        = string
  default     = "ap-northeast-2"
}

variable "vpc_id" {
  description = "VPC ID where RDS will be created"
  type        = string
  default     = "vpc-080d0ee90ce2e4fc3"
}

variable "ec2_security_group_id" {
  description = "EC2 Security Group ID for RDS access"
  type        = string
  default     = "sg-002ef6068dc1eac15"
}

variable "subnet_ids" {
  description = "Subnet IDs for RDS Subnet Group (minimum 2 AZs)"
  type        = list(string)
  default = [
    "subnet-08a1a475056f3db26", # ap-northeast-2c
    "subnet-0ea991d3ed002526d"  # ap-northeast-2b
  ]
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "asterisk"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "admin"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for tagging"
  type        = string
  default     = "aicc-asterisk"
}

# =============================================================================
# SIP Allowed IPs - UDP 5060 접근 허용 IP 목록
# =============================================================================
variable "sip_allowed_ips" {
  description = "List of IPs allowed to access SIP port (UDP 5060)"
  type = list(object({
    cidr        = string
    description = string
  }))
  default = []
}

variable "rtp_allowed_ips" {
  description = "List of IPs allowed to access RTP ports (UDP 10000-20000)"
  type = list(object({
    cidr        = string
    description = string
  }))
  default = []
}
