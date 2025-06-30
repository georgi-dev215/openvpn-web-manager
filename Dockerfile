# OpenVPN Cluster Management System - Docker Image
# Based on Ubuntu 22.04 LTS for better OpenVPN compatibility
FROM ubuntu:22.04

# Metadata
LABEL maintainer="OpenVPN Manager Team"
LABEL version="2.0"
LABEL description="OpenVPN Cluster Management System"

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Application settings
ENV OPENVPN_MANAGER_HOST=0.0.0.0
ENV OPENVPN_MANAGER_PORT=8822
ENV OPENVPN_MANAGER_DEBUG=false
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create application user
RUN groupadd -r openvpn-manager && \
    useradd -r -g openvpn-manager -d /app -s /bin/bash openvpn-manager

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    curl \
    wget \
    git \
    sqlite3 \
    openssh-client \
    openssl \
    iptables \
    iproute2 \
    net-tools \
    cron \
    logrotate \
    supervisor \
    # OpenVPN and EasyRSA
    openvpn \
    easy-rsa \
    # Additional utilities
    nano \
    vim \
    htop \
    tree \
    jq \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create application directories
RUN mkdir -p /app/{data,logs,backups,ssh-keys,temp} && \
    chown -R openvpn-manager:openvpn-manager /app

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Create virtual environment and install Python dependencies
RUN python3 -m venv venv && \
    venv/bin/pip install --upgrade pip && \
    venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Set proper permissions
RUN chown -R openvpn-manager:openvpn-manager /app && \
    chmod +x *.sh

# Create OpenVPN directories if they don't exist
RUN mkdir -p /etc/openvpn/server && \
    mkdir -p /var/log/openvpn && \
    chown -R openvpn-manager:openvpn-manager /etc/openvpn /var/log/openvpn

# Copy supervisor configuration
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy health check script
COPY docker/healthcheck.sh /healthcheck.sh
RUN chmod +x /healthcheck.sh

# Expose ports
EXPOSE 8822

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD /healthcheck.sh

# Create volume mount points
VOLUME ["/app/data", "/app/logs", "/app/backups", "/etc/openvpn"]

# Switch to application user
USER openvpn-manager

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"] 