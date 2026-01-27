#!/bin/bash
# Generate unique passwords for each SIP agent
# Usage: ./generate_agent_passwords.sh [output_file]
#
# This script generates secure random passwords for each agent
# and outputs them in a format suitable for environment variables.

set -e

OUTPUT_FILE="${1:-agents_passwords.env}"
AGENTS="agent01 agent02 agent03 agent04 agent05 agent06"

echo "# Generated SIP Agent Passwords - $(date)" > "$OUTPUT_FILE"
echo "# DO NOT COMMIT THIS FILE TO VERSION CONTROL" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

for agent in $AGENTS; do
    # Generate 16 character alphanumeric password
    password=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c16)
    echo "${agent^^}_PASSWORD='$password'" >> "$OUTPUT_FILE"
    echo "Generated password for $agent"
done

chmod 600 "$OUTPUT_FILE"
echo ""
echo "Passwords saved to: $OUTPUT_FILE"
echo "Remember to:"
echo "  1. Source this file: source $OUTPUT_FILE"
echo "  2. Update the database with the new passwords"
echo "  3. Update agent SIP client configurations"
