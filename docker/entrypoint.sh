#!/bin/bash

# OpenVPN Manager Docker Entrypoint Script
set -e

echo "🚀 Starting OpenVPN Cluster Manager..."
echo "   Version: 2.0"
echo "   Container ID: $(hostname)"
echo "   Timestamp: $(date)"

# Function to log messages
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Wait for dependencies
wait_for_service() {
    local host="$1"
    local port="$2"
    local service="$3"
    
    log "Waiting for $service to be available at $host:$port..."
    
    for i in {1..30}; do
        if nc -z "$host" "$port" 2>/dev/null; then
            log "$service is available!"
            return 0
        fi
        sleep 2
    done
    
    log "Warning: $service is not available after 60 seconds"
    return 1
}

# Initialize database if it doesn't exist
init_database() {
    if [[ ! -f "/app/data/vpn_history.db" ]]; then
        log "Initializing database..."
        touch /app/data/vpn_history.db
        chmod 644 /app/data/vpn_history.db
    fi
}

# Create log files
init_logging() {
    log "Setting up logging..."
    
    # Create log files
    touch /app/logs/app.log
    touch /app/logs/access.log
    touch /app/logs/error.log
    
    # Set permissions
    chmod 644 /app/logs/*.log
}

# Set environment variables from .env file if it exists
load_env() {
    if [[ -f "/app/.env" ]]; then
        log "Loading environment variables from .env file..."
        set -a
        source /app/.env
        set +a
    fi
}

# Validate required environment variables
validate_env() {
    log "Validating environment variables..."
    
    # Set defaults if not provided
    export OPENVPN_MANAGER_HOST=${OPENVPN_MANAGER_HOST:-"0.0.0.0"}
    export OPENVPN_MANAGER_PORT=${OPENVPN_MANAGER_PORT:-"8822"}
    export ADMIN_USERNAME=${ADMIN_USERNAME:-"admin"}
    export ADMIN_PASSWORD=${ADMIN_PASSWORD:-"admin123"}
    export DATABASE_PATH=${DATABASE_PATH:-"/app/data/vpn_history.db"}
    export LOG_LEVEL=${LOG_LEVEL:-"INFO"}
    
    log "Configuration loaded:"
    log "  - Host: $OPENVPN_MANAGER_HOST"
    log "  - Port: $OPENVPN_MANAGER_PORT"
    log "  - Admin User: $ADMIN_USERNAME"
    log "  - Database: $DATABASE_PATH"
    log "  - Log Level: $LOG_LEVEL"
}

# Setup OpenVPN directories
setup_openvpn() {
    log "Setting up OpenVPN directories..."
    
    # Create directories if they don't exist
    mkdir -p /etc/openvpn/server
    mkdir -p /var/log/openvpn
    
    # Check if OpenVPN configuration exists
    if [[ ! -f "/etc/openvpn/server/server.conf" ]]; then
        log "Warning: OpenVPN server configuration not found at /etc/openvpn/server/server.conf"
        log "The application will start but OpenVPN integration may not work properly."
    fi
}

# Setup SSH for cluster management
setup_ssh() {
    log "Setting up SSH client configuration..."
    
    # Create SSH directory
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    
    # Copy SSH keys if they exist
    if [[ -d "/app/ssh-keys" ]]; then
        cp /app/ssh-keys/* ~/.ssh/ 2>/dev/null || true
        chmod 600 ~/.ssh/* 2>/dev/null || true
    fi
    
    # Create SSH config with relaxed security for container environment
    cat > ~/.ssh/config << EOF
Host *
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    LogLevel ERROR
    ConnectTimeout 10
EOF
    chmod 600 ~/.ssh/config
}

# Run pre-flight checks
preflight_checks() {
    log "Running pre-flight checks..."
    
    # Check Python environment
    if /app/venv/bin/python --version &>/dev/null; then
        log "✓ Python environment: $(/app/venv/bin/python --version)"
    else
        log "✗ Python environment check failed"
        exit 1
    fi
    
    # Check required Python packages
    if /app/venv/bin/python -c "import flask, sqlite3, paramiko" &>/dev/null; then
        log "✓ Required Python packages are available"
    else
        log "✗ Some required Python packages are missing"
        exit 1
    fi
    
    # Check database directory
    if [[ -d "/app/data" ]]; then
        log "✓ Database directory exists"
    else
        log "✗ Database directory not found"
        exit 1
    fi
    
    # Check application files
    if [[ -f "/app/app.py" ]]; then
        log "✓ Application file found"
    else
        log "✗ Application file not found"
        exit 1
    fi
}

# Generate initial configuration
generate_config() {
    if [[ ! -f "/app/.env" ]]; then
        log "Generating initial configuration..."
        
        cat > /app/.env << EOF
# OpenVPN Manager Configuration (Docker)
OPENVPN_MANAGER_HOST=$OPENVPN_MANAGER_HOST
OPENVPN_MANAGER_PORT=$OPENVPN_MANAGER_PORT
OPENVPN_MANAGER_DEBUG=false

# Authentication
ADMIN_USERNAME=$ADMIN_USERNAME
ADMIN_PASSWORD=$ADMIN_PASSWORD

# Database
DATABASE_PATH=$DATABASE_PATH

# OpenVPN Settings
OPENVPN_CONFIG_PATH=/etc/openvpn/server
EASYRSA_PATH=/etc/openvpn/server/easy-rsa

# Logging
LOG_LEVEL=$LOG_LEVEL
LOG_FILE=/app/logs/app.log

# Container specific
CONTAINER_MODE=true
EOF
        chmod 600 /app/.env
        log "Configuration file created at /app/.env"
    fi
}

# Main initialization
main() {
    log "Starting OpenVPN Manager initialization..."
    
    # Load and validate environment
    load_env
    validate_env
    generate_config
    
    # Initialize components
    init_database
    init_logging
    setup_openvpn
    setup_ssh
    
    # Run checks
    preflight_checks
    
    log "✅ Initialization completed successfully!"
    log "🌐 Web interface will be available at: http://localhost:$OPENVPN_MANAGER_PORT"
    log "👤 Default credentials: $ADMIN_USERNAME / $ADMIN_PASSWORD"
    log ""
    log "Starting application..."
    
    # Execute the main command
    exec "$@"
}

# Handle different run modes
case "${1:-}" in
    "supervisord")
        main "$@"
        ;;
    "app")
        main /app/venv/bin/python /app/app.py
        ;;
    "shell"|"bash")
        log "Starting interactive shell..."
        exec /bin/bash
        ;;
    "help"|"--help")
        echo "OpenVPN Manager Docker Container"
        echo "Available commands:"
        echo "  supervisord  - Start with supervisor (default)"
        echo "  app         - Start application directly"
        echo "  shell       - Interactive shell"
        echo "  help        - Show this help"
        exit 0
        ;;
    *)
        if [[ -n "$1" ]]; then
            log "Executing custom command: $*"
            exec "$@"
        else
            log "No command specified, starting with supervisor..."
            main supervisord -c /etc/supervisor/conf.d/supervisord.conf
        fi
        ;;
esac 