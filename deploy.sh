#!/bin/bash
# =============================================================================
# Asterisk Linphone Integration - Deployment Script
# =============================================================================
# This script deploys configuration files to EC2 and sets up the environment.
#
# Usage:
#   ./deploy.sh [--password YOUR_LINPHONE_PASSWORD]
#
# Environment Variables:
#   LINPHONE_PASSWORD - Linphone account password (required)
#   EC2_PUBLIC_IP     - EC2 public IP (optional, auto-detected)
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ASTERISK_CONFIG_DIR="/etc/asterisk"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/config"
STASIS_DIR="${SCRIPT_DIR}/stasis_app"
PYTHON_DIR="${SCRIPT_DIR}/python"

# Default values
LINPHONE_USER="youngho"
LINPHONE_PASSWORD="${LINPHONE_PASSWORD:-}"

# =============================================================================
# Functions
# =============================================================================

print_header() {
    echo ""
    echo "=============================================================="
    echo "$1"
    echo "=============================================================="
}

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_asterisk() {
    print_header "Checking Asterisk Installation"

    if ! command -v asterisk &> /dev/null; then
        print_error "Asterisk is not installed"
        exit 1
    fi

    ASTERISK_VERSION=$(asterisk -V 2>/dev/null || echo "Unknown")
    print_info "Asterisk version: ${ASTERISK_VERSION}"

    if systemctl is-active --quiet asterisk; then
        print_info "Asterisk service is running"
    else
        print_warn "Asterisk service is not running"
    fi
}

get_ec2_public_ip() {
    print_header "Detecting EC2 Public IP"

    if [[ -n "${EC2_PUBLIC_IP}" ]]; then
        print_info "Using provided EC2_PUBLIC_IP: ${EC2_PUBLIC_IP}"
        return
    fi

    # Try to get public IP from EC2 metadata
    EC2_PUBLIC_IP=$(curl -s --connect-timeout 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || true)

    if [[ -z "${EC2_PUBLIC_IP}" ]]; then
        # Fallback to external service
        EC2_PUBLIC_IP=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || true)
    fi

    if [[ -z "${EC2_PUBLIC_IP}" ]]; then
        print_error "Could not detect EC2 public IP"
        print_info "Please set EC2_PUBLIC_IP environment variable"
        exit 1
    fi

    print_info "Detected EC2 Public IP: ${EC2_PUBLIC_IP}"
}

get_vpc_cidr() {
    # Get the local network CIDR
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    # Extract first two octets for /16 CIDR
    VPC_CIDR=$(echo "${LOCAL_IP}" | cut -d. -f1-2).0.0/16
    print_info "VPC CIDR: ${VPC_CIDR}"
}

get_password() {
    print_header "Linphone Account Configuration"

    # Check command line argument
    while [[ $# -gt 0 ]]; do
        case $1 in
            --password)
                LINPHONE_PASSWORD="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    if [[ -z "${LINPHONE_PASSWORD}" ]]; then
        print_info "Linphone username: ${LINPHONE_USER}"
        read -sp "Enter Linphone password: " LINPHONE_PASSWORD
        echo ""
    fi

    if [[ -z "${LINPHONE_PASSWORD}" ]]; then
        print_error "Linphone password is required"
        exit 1
    fi

    print_info "Linphone account: ${LINPHONE_USER}@sip.linphone.org"
}

backup_configs() {
    print_header "Backing Up Existing Configurations"

    BACKUP_DIR="${ASTERISK_CONFIG_DIR}/backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "${BACKUP_DIR}"

    for conf in pjsip.conf extensions.conf rtp.conf ari.conf http.conf; do
        if [[ -f "${ASTERISK_CONFIG_DIR}/${conf}" ]]; then
            cp "${ASTERISK_CONFIG_DIR}/${conf}" "${BACKUP_DIR}/"
            print_info "Backed up: ${conf}"
        fi
    done

    print_info "Backup directory: ${BACKUP_DIR}"
}

deploy_configs() {
    print_header "Deploying Asterisk Configurations"

    # Deploy pjsip.conf with variable substitution
    print_info "Deploying pjsip.conf..."
    sed -e "s/__LINPHONE_PASSWORD__/${LINPHONE_PASSWORD}/g" \
        -e "s/13.209.97.212/${EC2_PUBLIC_IP}/g" \
        -e "s|172.31.0.0/16|${VPC_CIDR}|g" \
        "${CONFIG_DIR}/pjsip.conf" > "${ASTERISK_CONFIG_DIR}/pjsip.conf"

    # Deploy other configs as-is
    for conf in extensions.conf rtp.conf ari.conf http.conf; do
        print_info "Deploying ${conf}..."
        cp "${CONFIG_DIR}/${conf}" "${ASTERISK_CONFIG_DIR}/${conf}"
    done

    # Set permissions
    chown asterisk:asterisk "${ASTERISK_CONFIG_DIR}"/*.conf 2>/dev/null || true
    chmod 640 "${ASTERISK_CONFIG_DIR}/pjsip.conf"  # Restrict pjsip.conf (contains password)

    print_info "Configuration files deployed successfully"
}

reload_asterisk() {
    print_header "Reloading Asterisk"

    if systemctl is-active --quiet asterisk; then
        # Reload configuration
        asterisk -rx "core reload" 2>/dev/null || true
        sleep 2

        # Reload specific modules
        asterisk -rx "pjsip reload" 2>/dev/null || true
        asterisk -rx "dialplan reload" 2>/dev/null || true

        print_info "Asterisk configuration reloaded"
    else
        print_info "Starting Asterisk service..."
        systemctl start asterisk
        sleep 3
    fi

    # Check registration status
    print_info "Checking SIP registration status..."
    sleep 5
    asterisk -rx "pjsip show registrations" 2>/dev/null || true
}

setup_stasis_app() {
    print_header "Setting Up Stasis Application"

    # Check if Node.js is installed
    if ! command -v node &> /dev/null; then
        print_warn "Node.js is not installed"
        print_info "Please install Node.js 16+ to run the Stasis app"
        print_info "  curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -"
        print_info "  sudo apt-get install -y nodejs"
        return
    fi

    NODE_VERSION=$(node -v)
    print_info "Node.js version: ${NODE_VERSION}"

    # Install dependencies
    print_info "Installing Stasis app dependencies..."
    cd "${STASIS_DIR}"
    npm install --production 2>/dev/null || npm install

    print_info "Stasis app ready at: ${STASIS_DIR}"
    print_info "To start: cd ${STASIS_DIR} && node app.js"
}

check_security_group() {
    print_header "Security Group Reminder"

    echo "Please ensure the following ports are open in your AWS Security Group:"
    echo ""
    echo "  Port      Protocol   Purpose"
    echo "  ----      --------   -------"
    echo "  5060      UDP        SIP signaling"
    echo "  8088      TCP        ARI HTTP/WebSocket"
    echo "  10000-20000  UDP     RTP media"
    echo "  12345     UDP        ExternalMedia (if receiving locally)"
    echo ""
}

print_summary() {
    print_header "Deployment Complete"

    echo ""
    echo "Configuration:"
    echo "  EC2 Public IP:  ${EC2_PUBLIC_IP}"
    echo "  VPC CIDR:       ${VPC_CIDR}"
    echo "  Linphone User:  ${LINPHONE_USER}@sip.linphone.org"
    echo ""
    echo "Next Steps:"
    echo ""
    echo "  1. Start the UDP receiver (in Terminal 1):"
    echo "     cd ${PYTHON_DIR}"
    echo "     python3 udp_receiver.py"
    echo ""
    echo "  2. Start the Stasis app (in Terminal 2):"
    echo "     cd ${STASIS_DIR}"
    echo "     node app.js"
    echo ""
    echo "  3. Check Asterisk registration:"
    echo "     sudo asterisk -rx 'pjsip show registrations'"
    echo ""
    echo "  4. Make a test call:"
    echo "     Call youngho@sip.linphone.org from another Linphone account"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    print_header "Asterisk Linphone Integration Deployment"

    check_root
    check_asterisk
    get_ec2_public_ip
    get_vpc_cidr
    get_password "$@"
    backup_configs
    deploy_configs
    reload_asterisk
    setup_stasis_app
    check_security_group
    print_summary
}

# Run main with all arguments
main "$@"
