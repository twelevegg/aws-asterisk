# =============================================================================
# SSM Automation for Deployment and Failover
# =============================================================================

resource "aws_ssm_document" "asterisk_deploy" {
  name            = "asterisk-deploy"
  document_type   = "Command"
  document_format = "YAML"

  content = <<DOC
schemaVersion: '2.2'
description: Deploy Asterisk AICC application
parameters:
  GitBranch:
    type: String
    default: main
    description: Git branch to deploy
mainSteps:
  - action: aws:runShellScript
    name: deployAsterisk
    inputs:
      runCommand:
        - |
          #!/bin/bash
          set -ex
          cd /opt/aicc
          git fetch origin
          git checkout {{ GitBranch }}
          git pull origin {{ GitBranch }}
          cp /opt/aicc/config/*.conf /etc/asterisk/
          systemctl restart asterisk
          sleep 5
          systemctl restart stasis-app
          systemctl restart aicc-pipeline
          systemctl is-active asterisk
          systemctl is-active stasis-app
          asterisk -rx "pjsip show registrations"
DOC

  tags = {
    Name = "asterisk-deploy"
  }
}

resource "aws_ssm_document" "asterisk_health" {
  name            = "asterisk-health-check"
  document_type   = "Command"
  document_format = "YAML"

  content = <<DOC
schemaVersion: '2.2'
description: Check Asterisk health status
mainSteps:
  - action: aws:runShellScript
    name: checkHealth
    inputs:
      runCommand:
        - |
          #!/bin/bash
          echo "=== Asterisk Service Status ==="
          systemctl is-active asterisk && echo "OK" || echo "FAILED"
          echo "=== Stasis App Status ==="
          systemctl is-active stasis-app && echo "OK" || echo "FAILED"
          echo "=== AICC Pipeline Status ==="
          systemctl is-active aicc-pipeline && echo "OK" || echo "FAILED"
          echo "=== SIP Registrations ==="
          asterisk -rx "pjsip show registrations"
          echo "=== Active Calls ==="
          asterisk -rx "core show channels concise"
          echo "=== ARI Status ==="
          curl -s -u ari:ari http://localhost:8088/ari/applications || echo "ARI not responding"
DOC

  tags = {
    Name = "asterisk-health-check"
  }
}

resource "aws_ssm_document" "asterisk_manual_failover" {
  name            = "asterisk-manual-failover"
  document_type   = "Command"
  document_format = "YAML"

  content = <<DOC
schemaVersion: '2.2'
description: Manual failover - invoke Lambda to reassign EIP
parameters:
  TargetInstance:
    type: String
    allowedValues:
      - primary
      - standby
    description: Target instance to failover to
mainSteps:
  - action: aws:runShellScript
    name: invokeFailover
    inputs:
      runCommand:
        - |
          #!/bin/bash
          set -ex
          echo "Invoking failover Lambda..."
          aws lambda invoke \
            --function-name asterisk-eip-failover \
            --payload '{"manual": true, "target": "{{ TargetInstance }}"}' \
            /tmp/failover-response.json
          cat /tmp/failover-response.json
DOC

  tags = {
    Name = "asterisk-manual-failover"
  }
}
