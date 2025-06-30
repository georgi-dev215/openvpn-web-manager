#!/bin/bash

# OpenVPN Cluster Management System - Automated Installation Script
# Version: 2.0
# Author: OpenVPN Manager Team
# License: MIT

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_VERSION="2.0"
INSTALL_DIR="/opt/openvpn-manager"
SERVICE_NAME="openvpn-webmanager"
DEFAULT_PORT="8822"
DEFAULT_USER="admin"
DEFAULT_PASS="admin123"

# System requirements
MIN_PYTHON_VERSION="3.7"
MIN_RAM_MB=512
MIN_DISK_MB=1024

# Log function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Print banner
print_banner() {
    echo -e "${BLUE}"
    cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                OpenVPN Cluster Manager                        ║
║                  Automated Installer                          ║
║                     Version 2.0                              ║
╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "This script should not be run as root! Please run as a regular user with sudo privileges."
    fi
    
    # Check sudo access
    if ! sudo -n true 2>/dev/null; then
        error "This script requires sudo privileges. Please run: sudo $0"
    fi
}

# Detect OS and distribution
detect_os() {
    log "Detecting operating system..."
    
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
        CODENAME=$VERSION_CODENAME
    else
        error "Cannot detect operating system. This script supports Ubuntu, Debian, and CentOS."
    fi
    
    case $OS in
        "Ubuntu"|"Debian GNU/Linux")
            PACKAGE_MANAGER="apt"
            ;;
        "CentOS Linux"|"Red Hat Enterprise Linux")
            PACKAGE_MANAGER="yum"
            ;;
        *)
            error "Unsupported operating system: $OS"
            ;;
    esac
    
    success "Detected: $OS $VER ($PACKAGE_MANAGER)"
}

# Check system requirements
check_requirements() {
    log "Checking system requirements..."
    
    # Check RAM
    RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
    if [[ $RAM_MB -lt $MIN_RAM_MB ]]; then
        warning "System has ${RAM_MB}MB RAM, minimum ${MIN_RAM_MB}MB recommended"
    else
        success "RAM: ${RAM_MB}MB (✓)"
    fi
    
    # Check disk space
    DISK_MB=$(df / | awk 'NR==2{print int($4/1024)}')
    if [[ $DISK_MB -lt $MIN_DISK_MB ]]; then
        error "Insufficient disk space. Required: ${MIN_DISK_MB}MB, Available: ${DISK_MB}MB"
    else
        success "Disk space: ${DISK_MB}MB (✓)"
    fi
    
    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
        if python3 -c "import sys; exit(0 if sys.version_info >= (3,7) else 1)"; then
            success "Python: $PYTHON_VERSION (✓)"
        else
            error "Python $PYTHON_VERSION found, but $MIN_PYTHON_VERSION+ required"
        fi
    else
        warning "Python3 not found, will be installed"
    fi
}

# Install system dependencies
install_dependencies() {
    log "Installing system dependencies..."
    
    sudo apt update -qq
    
    case $PACKAGE_MANAGER in
        "apt")
            sudo apt install -y \
                python3 \
                python3-pip \
                python3-venv \
                python3-dev \
                build-essential \
                curl \
                wget \
                git \
                sqlite3 \
                openssh-server \
                ufw \
                cron \
                logrotate
            ;;
        "yum")
            sudo yum install -y epel-release
            sudo yum install -y \
                python3 \
                python3-pip \
                python3-devel \
                gcc \
                gcc-c++ \
                make \
                curl \
                wget \
                git \
                sqlite \
                openssh-server \
                firewalld \
                cronie
            ;;
    esac
    
    success "System dependencies installed"
}

# Install OpenVPN if not present
install_openvpn() {
    if command -v openvpn &> /dev/null; then
        success "OpenVPN already installed: $(openvpn --version | head -1)"
        return
    fi
    
    log "Installing OpenVPN..."
    
    case $PACKAGE_MANAGER in
        "apt")
            sudo apt install -y openvpn easy-rsa
            ;;
        "yum")
            sudo yum install -y openvpn easy-rsa
            ;;
    esac
    
    success "OpenVPN installed"
}

# Create application user
create_app_user() {
    if id "openvpn-manager" &>/dev/null; then
        success "User 'openvpn-manager' already exists"
        return
    fi
    
    log "Creating application user..."
    sudo useradd -r -s /bin/false -d $INSTALL_DIR openvpn-manager
    success "Application user created"
}

# Download and setup application
setup_application() {
    log "Setting up OpenVPN Manager application..."
    
    # Create installation directory
    sudo mkdir -p $INSTALL_DIR
    sudo mkdir -p $INSTALL_DIR/logs
    sudo mkdir -p $INSTALL_DIR/backups
    sudo mkdir -p $INSTALL_DIR/data
    
    # Copy application files
    if [[ -f "app.py" ]]; then
        # Installation from local files
        log "Installing from local directory..."
        sudo cp -r * $INSTALL_DIR/
    else
        # Download from GitHub
        log "Downloading from GitHub repository..."
        TEMP_DIR=$(mktemp -d)
        cd $TEMP_DIR
        git clone https://github.com/yourusername/openvpn-manager.git .
        sudo cp -r * $INSTALL_DIR/
        cd - > /dev/null
        rm -rf $TEMP_DIR
    fi
    
    # Set permissions
    sudo chown -R openvpn-manager:openvpn-manager $INSTALL_DIR
    sudo chmod +x $INSTALL_DIR/*.sh
    
    success "Application files installed"
}

# Install Python dependencies
install_python_deps() {
    log "Installing Python dependencies..."
    
    # Create virtual environment
    sudo -u openvpn-manager python3 -m venv $INSTALL_DIR/venv
    
    # Install requirements
    sudo -u openvpn-manager $INSTALL_DIR/venv/bin/pip install --upgrade pip
    sudo -u openvpn-manager $INSTALL_DIR/venv/bin/pip install -r $INSTALL_DIR/requirements.txt
    
    success "Python dependencies installed"
}

# Create systemd service
create_service() {
    log "Creating systemd service..."
    
    sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=OpenVPN Cluster Management System
After=network.target openvpn.service

[Service]
Type=simple
User=openvpn-manager
Group=openvpn-manager
WorkingDirectory=$INSTALL_DIR
Environment=PATH=$INSTALL_DIR/venv/bin
ExecStart=$INSTALL_DIR/venv/bin/python app.py
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=openvpn-manager

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR /etc/openvpn

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    success "Systemd service created"
}

# Configure firewall
configure_firewall() {
    log "Configuring firewall..."
    
    case $PACKAGE_MANAGER in
        "apt")
            if command -v ufw &> /dev/null; then
                sudo ufw allow $DEFAULT_PORT/tcp comment "OpenVPN Manager"
                if ! sudo ufw status | grep -q "Status: active"; then
                    warning "UFW is not active. Enable it with: sudo ufw enable"
                fi
            fi
            ;;
        "yum")
            if command -v firewall-cmd &> /dev/null; then
                sudo firewall-cmd --permanent --add-port=$DEFAULT_PORT/tcp
                sudo firewall-cmd --reload
            fi
            ;;
    esac
    
    success "Firewall configured for port $DEFAULT_PORT"
}

# Create configuration files
create_config() {
    log "Creating configuration files..."
    
    # Create environment file
    sudo tee $INSTALL_DIR/.env > /dev/null << EOF
# OpenVPN Manager Configuration
OPENVPN_MANAGER_HOST=0.0.0.0
OPENVPN_MANAGER_PORT=$DEFAULT_PORT
OPENVPN_MANAGER_DEBUG=False

# Authentication
ADMIN_USERNAME=$DEFAULT_USER
ADMIN_PASSWORD=$DEFAULT_PASS

# Database
DATABASE_PATH=$INSTALL_DIR/data/vpn_history.db

# OpenVPN Settings
OPENVPN_CONFIG_PATH=/etc/openvpn/server
EASYRSA_PATH=/etc/openvpn/server/easy-rsa

# Logging
LOG_LEVEL=INFO
LOG_FILE=$INSTALL_DIR/logs/app.log
EOF

    sudo chown openvpn-manager:openvpn-manager $INSTALL_DIR/.env
    sudo chmod 600 $INSTALL_DIR/.env
    
    success "Configuration files created"
}

# Setup log rotation
setup_logging() {
    log "Setting up log rotation..."
    
    sudo tee /etc/logrotate.d/openvpn-manager > /dev/null << EOF
$INSTALL_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
    su openvpn-manager openvpn-manager
}
EOF

    success "Log rotation configured"
}

# Setup backup cron job
setup_backup() {
    log "Setting up automated backups..."
    
    # Create backup script
    sudo tee $INSTALL_DIR/backup.sh > /dev/null << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/openvpn-manager/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="auto_backup_$DATE"

# Create backup via API
curl -s -u admin:admin123 -X POST http://localhost:8822/api/backup_configs > /dev/null

# Clean old backups (keep 7 days)
find $BACKUP_DIR -name "auto_backup_*.tar.gz" -mtime +7 -delete
EOF

    sudo chmod +x $INSTALL_DIR/backup.sh
    sudo chown openvpn-manager:openvpn-manager $INSTALL_DIR/backup.sh
    
    # Add to crontab (daily at 2 AM)
    echo "0 2 * * * openvpn-manager $INSTALL_DIR/backup.sh" | sudo tee -a /etc/crontab > /dev/null
    
    success "Automated backup configured"
}

# Start services
start_services() {
    log "Starting services..."
    
    sudo systemctl enable $SERVICE_NAME
    sudo systemctl start $SERVICE_NAME
    
    # Wait for service to start
    sleep 5
    
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        success "OpenVPN Manager service started successfully"
    else
        error "Failed to start OpenVPN Manager service. Check logs: sudo journalctl -u $SERVICE_NAME"
    fi
}

# Security hardening
apply_security() {
    log "Applying security hardening..."
    
    # Set secure permissions
    sudo chmod 750 $INSTALL_DIR
    sudo chmod 600 $INSTALL_DIR/.env
    
    # Disable unnecessary services (optional)
    # sudo systemctl disable telnet.socket 2>/dev/null || true
    
    success "Basic security hardening applied"
}

# Print installation summary
print_summary() {
    local server_ip=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    
    echo -e "\n${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                  INSTALLATION COMPLETED!                      ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}\n"
    
    echo -e "${BLUE}📋 Installation Summary:${NC}"
    echo -e "   • Installation Directory: $INSTALL_DIR"
    echo -e "   • Service Name: $SERVICE_NAME"
    echo -e "   • Web Interface Port: $DEFAULT_PORT"
    echo -e "   • Log Directory: $INSTALL_DIR/logs"
    echo -e "   • Backup Directory: $INSTALL_DIR/backups"
    
    echo -e "\n${BLUE}🌐 Access Information:${NC}"
    echo -e "   • Web Interface: http://$server_ip:$DEFAULT_PORT"
    echo -e "   • Default Username: $DEFAULT_USER"
    echo -e "   • Default Password: $DEFAULT_PASS"
    echo -e "   ${YELLOW}⚠️  Please change the default password after first login!${NC}"
    
    echo -e "\n${BLUE}🔧 Service Management:${NC}"
    echo -e "   • Start service: sudo systemctl start $SERVICE_NAME"
    echo -e "   • Stop service: sudo systemctl stop $SERVICE_NAME"
    echo -e "   • Restart service: sudo systemctl restart $SERVICE_NAME"
    echo -e "   • Check status: sudo systemctl status $SERVICE_NAME"
    echo -e "   • View logs: sudo journalctl -u $SERVICE_NAME -f"
    
    echo -e "\n${BLUE}📁 Important Files:${NC}"
    echo -e "   • Configuration: $INSTALL_DIR/.env"
    echo -e "   • Application: $INSTALL_DIR/app.py"
    echo -e "   • Database: $INSTALL_DIR/data/vpn_history.db"
    echo -e "   • Service file: /etc/systemd/system/$SERVICE_NAME.service"
    
    echo -e "\n${BLUE}🔗 Useful Links:${NC}"
    echo -e "   • Documentation: https://github.com/yourusername/openvpn-manager/wiki"
    echo -e "   • Issues: https://github.com/yourusername/openvpn-manager/issues"
    echo -e "   • Discussions: https://github.com/yourusername/openvpn-manager/discussions"
    
    echo -e "\n${GREEN}🎉 OpenVPN Cluster Manager is now ready to use!${NC}"
    echo -e "${GREEN}   Open your browser and navigate to: http://$server_ip:$DEFAULT_PORT${NC}\n"
}

# Interactive configuration
interactive_config() {
    echo -e "\n${BLUE}🔧 Interactive Configuration${NC}"
    
    # Ask for custom port
    read -p "Web interface port [$DEFAULT_PORT]: " custom_port
    if [[ -n "$custom_port" ]]; then
        DEFAULT_PORT="$custom_port"
    fi
    
    # Ask for custom credentials
    read -p "Admin username [$DEFAULT_USER]: " custom_user
    if [[ -n "$custom_user" ]]; then
        DEFAULT_USER="$custom_user"
    fi
    
    while true; do
        read -s -p "Admin password [$DEFAULT_PASS]: " custom_pass
        echo
        if [[ -n "$custom_pass" ]]; then
            DEFAULT_PASS="$custom_pass"
            break
        else
            break
        fi
    done
}

# Cleanup function
cleanup() {
    if [[ $? -ne 0 ]]; then
        error "Installation failed! Check the logs above for details."
        echo -e "\n${YELLOW}Cleanup commands:${NC}"
        echo -e "   sudo systemctl stop $SERVICE_NAME 2>/dev/null"
        echo -e "   sudo systemctl disable $SERVICE_NAME 2>/dev/null"
        echo -e "   sudo rm -rf $INSTALL_DIR"
        echo -e "   sudo rm -f /etc/systemd/system/$SERVICE_NAME.service"
        echo -e "   sudo userdel openvpn-manager 2>/dev/null"
    fi
}

# Main installation function
main() {
    trap cleanup EXIT
    
    print_banner
    
    log "Starting OpenVPN Cluster Manager installation..."
    
    # Check if running with --interactive flag
    if [[ "$1" == "--interactive" ]]; then
        interactive_config
    fi
    
    check_root
    detect_os
    check_requirements
    install_dependencies
    install_openvpn
    create_app_user
    setup_application
    install_python_deps
    create_config
    create_service
    configure_firewall
    setup_logging
    setup_backup
    apply_security
    start_services
    
    print_summary
    
    trap - EXIT
    success "Installation completed successfully!"
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "OpenVPN Cluster Manager Installer"
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --interactive    Run interactive configuration"
        echo "  --help, -h       Show this help message"
        echo "  --version, -v    Show version information"
        exit 0
        ;;
    --version|-v)
        echo "OpenVPN Cluster Manager Installer v$SCRIPT_VERSION"
        exit 0
        ;;
    --interactive)
        main --interactive
        ;;
    "")
        main
        ;;
    *)
        error "Unknown option: $1. Use --help for usage information."
        ;;
esac 