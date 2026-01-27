# =============================================================================
# Terraform Backend Configuration
#
# For production, uncomment the S3 backend configuration below.
# This enables:
#   - Remote state storage with encryption
#   - State locking via DynamoDB to prevent concurrent modifications
#   - Team collaboration support
#
# Prerequisites:
#   1. Create S3 bucket: aicc-terraform-state
#   2. Enable bucket encryption
#   3. Create DynamoDB table: terraform-locks (partition key: LockID)
# =============================================================================

# Uncomment for production use:
# terraform {
#   backend "s3" {
#     bucket         = "aicc-terraform-state"
#     key            = "aws-asterisk/terraform.tfstate"
#     region         = "ap-northeast-2"
#     encrypt        = true
#     dynamodb_table = "terraform-locks"
#   }
# }

# Local backend (current - for development only)
# WARNING: Local state contains sensitive data. Never commit to version control.
