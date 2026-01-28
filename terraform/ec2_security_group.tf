# =============================================================================
# EC2 Security Group Rules - SIP & RTP
# =============================================================================
# 기존 EC2 Security Group에 SIP/RTP 규칙 추가
# IP 목록은 sip_allowed_ips.auto.tfvars에서 관리
# =============================================================================

# SIP 시그널링 (UDP 5060) - 특정 IP만 허용
resource "aws_security_group_rule" "sip_ingress" {
  for_each = { for idx, ip in var.sip_allowed_ips : idx => ip }

  type              = "ingress"
  from_port         = 5060
  to_port           = 5060
  protocol          = "udp"
  cidr_blocks       = [each.value.cidr]
  description       = "SIP: ${each.value.description}"
  security_group_id = var.ec2_security_group_id
}

# RTP 미디어 (UDP 10000-20000) - 특정 IP만 허용
resource "aws_security_group_rule" "rtp_ingress" {
  for_each = { for idx, ip in var.rtp_allowed_ips : idx => ip }

  type              = "ingress"
  from_port         = 10000
  to_port           = 20000
  protocol          = "udp"
  cidr_blocks       = [each.value.cidr]
  description       = "RTP: ${each.value.description}"
  security_group_id = var.ec2_security_group_id
}

# Linphone.org SIP 서버 (아웃바운드 등록용) - 항상 허용
resource "aws_security_group_rule" "linphone_sip_ingress" {
  type              = "ingress"
  from_port         = 5060
  to_port           = 5060
  protocol          = "udp"
  cidr_blocks       = ["5.135.215.43/32", "176.31.149.179/32"]
  description       = "SIP: Linphone.org servers"
  security_group_id = var.ec2_security_group_id
}
