# =============================================================================
# SIP/RTP Allowed IPs
# =============================================================================
# Edit this file and commit & push to update Security Group automatically.
#
# Note:
#   - Use CIDR format (e.g., "1.2.3.4/32" for single IP)
#   - Description must be ASCII only (no Korean)
#   - Linphone server IPs are managed in ec2_security_group.tf
# =============================================================================

# SIP signaling (UDP 5060) allowed IPs
sip_allowed_ips = [
  {
    cidr        = "112.146.155.116/32"
    description = "Current User"
  },
  {
    cidr        = "175.117.63.58/32"
    description = "Existing"
  },
  {
    cidr        = "15.165.10.24/32"
    description = "SIP Server"
  },
]

# RTP media (UDP 10000-20000) allowed IPs
rtp_allowed_ips = [
  {
    cidr        = "112.146.155.116/32"
    description = "Current User"
  },
  {
    cidr        = "175.117.63.58/32"
    description = "Existing"
  },
  {
    cidr        = "15.165.10.24/32"
    description = "SIP Server"
  },
]
