#!/bin/bash

# OpenVPN Manager Health Check Script
set -e

# Configuration
HOST=${OPENVPN_MANAGER_HOST:-"localhost"}
PORT=${OPENVPN_MANAGER_PORT:-"8822"}
TIMEOUT=10

# Function to log health check results
log_health() {
    echo "[HEALTHCHECK $(date +'%Y-%m-%d %H:%M:%S')] $1"
}

# Check if the web service is responding
check_web_service() {
    if curl -f -s --max-time $TIMEOUT "http://$HOST:$PORT/api/status" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Check if Python process is running
check_python_process() {
    if pgrep -f "python.*app.py" >/dev/null; then
        return 0
    else
        return 1
    fi
}

# Check database connectivity
check_database() {
    if [[ -f "/app/data/vpn_history.db" ]] && sqlite3 /app/data/vpn_history.db "SELECT 1;" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Check log directory
check_logs() {
    if [[ -d "/app/logs" ]] && [[ -w "/app/logs" ]]; then
        return 0
    else
        return 1
    fi
}

# Main health check
main() {
    local exit_code=0
    
    # Check web service
    if check_web_service; then
        log_health "✓ Web service is responding"
    else
        log_health "✗ Web service is not responding"
        exit_code=1
    fi
    
    # Check Python process
    if check_python_process; then
        log_health "✓ Python process is running"
    else
        log_health "✗ Python process is not running"
        exit_code=1
    fi
    
    # Check database
    if check_database; then
        log_health "✓ Database is accessible"
    else
        log_health "✗ Database is not accessible"
        exit_code=1
    fi
    
    # Check logs
    if check_logs; then
        log_health "✓ Log directory is writable"
    else
        log_health "✗ Log directory is not accessible"
        exit_code=1
    fi
    
    if [[ $exit_code -eq 0 ]]; then
        log_health "🟢 All health checks passed"
    else
        log_health "🔴 Some health checks failed"
    fi
    
    exit $exit_code
}

# Execute health check
main "$@" 