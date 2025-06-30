# openvpn-web-manager
🌐 Modern web-based OpenVPN management system with cluster support, client administration, and real-time monitoring


# OpenVPN Cluster Management System

![OpenVPN Manager](https://img.shields.io/badge/openvpn-web-manager-blue.svg)
![Python](https://img.shields.io/badge/Python-3.7+-green.svg)
![Flask](https://img.shields.io/badge/Flask-2.0+-red.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

A comprehensive web-based management system for OpenVPN with advanced cluster management, client administration, and monitoring capabilities.

## 🌟 Features

### 🖥️ **Web Management Interface**
- Modern, responsive Bootstrap 5 UI
- Real-time dashboard with live statistics
- Dark/Light theme support
- Mobile-friendly design

### 👥 **Advanced Client Management**
- Bulk client operations (create, revoke, renew)
- Client grouping and profiles
- Certificate lifecycle management
- Temporary client support with auto-expiry
- Client activity tracking and history
- Export client configurations and statistics

### 🔧 **Configuration Management**
- Live OpenVPN server configuration editing
- Port and protocol management
- Authentication settings (username/password + certificates)
- Advanced security settings
- Configuration templates and validation
- Backup and restore system

### 🌐 **Cluster Management**
- Multi-server cluster support
- Remote server management via SSH
- Load balancing and client distribution
- Health monitoring and alerts
- Real-time cluster status dashboard
- Automatic failover capabilities

### 📊 **Monitoring & Analytics**
- Real-time connection monitoring
- Traffic analysis and bandwidth tracking
- System metrics (CPU, memory, disk)
- Client session history
- Activity logs and audit trails
- Performance statistics

### 🔐 **Security Features**
- HTTP Basic Authentication
- Role-based access control
- Secure API endpoints
- Configuration validation
- Encrypted backup system

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenVPN Cluster Manager                      │
├─────────────────────────────────────────────────────────────────┤
│  Web Interface (Flask + Bootstrap 5)                           │
│  ├── Dashboard                                                  │
│  ├── Client Management                                          │
│  ├── Cluster Management                                         │
│  ├── Configuration Editor                                       │
│  └── Monitoring & Analytics                                     │
├─────────────────────────────────────────────────────────────────┤
│  Backend Services                                               │
│  ├── OpenVPN Manager (Local Operations)                        │
│  ├── Cluster Manager (Remote Operations)                       │
│  ├── Configuration Manager                                      │
│  ├── Backup Manager                                             │
│  └── Monitoring Service                                         │
├─────────────────────────────────────────────────────────────────┤
│  Data Layer                                                     │
│  ├── SQLite Database (Client History, Sessions, Logs)          │
│  ├── Configuration Files (/etc/openvpn/server/)                │
│  ├── Certificates (PKI Infrastructure)                         │
│  └── Backup Storage                                             │
├─────────────────────────────────────────────────────────────────┤
│  External Integrations                                          │
│  ├── OpenVPN Server (Management Interface)                     │
│  ├── SSH Connections (Remote Servers)                          │
│  ├── System Commands (iptables, systemctl)                     │
│  └── EasyRSA (Certificate Management)                           │
└─────────────────────────────────────────────────────────────────┘
```

## 📋 System Requirements

### Minimum Requirements
- **OS**: Linux (Ubuntu 18.04+, CentOS 7+, Debian 9+)
- **RAM**: 512MB
- **Storage**: 1GB free space
- **Python**: 3.7 or higher
- **Network**: Internet connection for installation

### Recommended Requirements
- **OS**: Ubuntu 20.04 LTS or newer
- **RAM**: 1GB+
- **Storage**: 2GB+ free space
- **CPU**: 2+ cores
- **Network**: Static IP address

### Dependencies
- OpenVPN 2.4+
- EasyRSA 3.0+
- Python 3.7+
- SQLite 3
- SSH server (for cluster management)

## 🚀 Quick Installation

### Option 1: Automated Installation Script

```bash
curl -fsSL https://raw.githubusercontent.com/georgi-dev215/openvpn-web-manager/install.sh | bash
```

### Option 2: Manual Installation

```bash
# Clone the repository
git clone https://github.com/georgi-dev215/openvpn-web-manager.git
cd openvpn-web-manager

# Run installation script
chmod +x install.sh
sudo ./install.sh

# Start the service
sudo systemctl start openvpn-webmanager
sudo systemctl enable openvpn-webmanager
```

### Option 3: Docker Installation

```bash
# Using Docker Compose
git clone https://github.com/georgi-dev215/openvpn-web-manager.git
cd openvpn-web-manager
docker-compose up -d
```

## ⚙️ Configuration

### Initial Setup

1. **Access the web interface**: `http://your-server-ip:8822`
2. **Default credentials**: `admin` / `admin123`
3. **Change default password** in the settings page
4. **Configure OpenVPN** using the built-in configuration editor

### Environment Variables

```bash
# Application Settings
OPENVPN_MANAGER_HOST=0.0.0.0
OPENVPN_MANAGER_PORT=8822
OPENVPN_MANAGER_DEBUG=False

# Authentication
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password

# Database
DATABASE_PATH=vpn_history.db

# OpenVPN Settings
OPENVPN_CONFIG_PATH=/etc/openvpn/server
EASYRSA_PATH=/etc/openvpn/server/easy-rsa
```

### Advanced Configuration

Edit `config.py` for advanced settings:

```python
# Server Configuration
OPENVPN_SERVER_CONFIG = {
    'port': 1194,
    'protocol': 'udp',
    'cipher': 'AES-256-GCM',
    'auth': 'SHA512',
    'network': '10.8.0.0 255.255.255.0'
}

# Cluster Settings
CLUSTER_CONFIG = {
    'enable_auto_balancing': True,
    'health_check_interval': 60,
    'max_clients_per_server': 50
}

# Monitoring Settings
MONITORING_CONFIG = {
    'enable_metrics_collection': True,
    'metrics_retention_days': 30,
    'enable_email_alerts': False
}
```

## 📖 User Guide

### Dashboard Overview

The main dashboard provides:
- **Server Status**: Current OpenVPN server state
- **Client Overview**: Active, total, and revoked clients
- **System Metrics**: CPU, RAM, disk usage
- **Recent Activity**: Latest client connections and operations
- **Cluster Status**: Multi-server overview (if configured)

### Client Management

#### Creating Clients
1. Navigate to **Clients** page
2. Click **Add New Client**
3. Enter client name and select options:
   - **Expiry Period**: Certificate validity
   - **Client Group**: Organizational grouping
   - **Profile**: Access level and restrictions
4. Download the generated `.ovpn` configuration

#### Bulk Operations
- Select multiple clients using checkboxes
- Available operations:
  - Bulk group assignment
  - Bulk certificate renewal
  - Bulk revocation
  - Bulk export

#### Client Profiles
- **Standard**: Basic VPN access
- **High Bandwidth**: Optimized for streaming
- **Restricted**: Time-limited access
- **Mobile Only**: Mobile device optimization
- **Admin Access**: Full network access
- **Guest Limited**: Restricted guest access

### Cluster Management

#### Adding Servers
1. Go to **Cluster** page
2. Click **Add Server**
3. Configure connection:
   - **Server ID**: Unique identifier
   - **Hostname/IP**: Server address
   - **SSH Credentials**: Username/password or key
   - **OpenVPN Port**: Service port
4. Test connection before adding

#### Load Balancing
- **Manual Assignment**: Assign clients to specific servers
- **Automatic Balancing**: Distribute based on server load
- **Geographic Distribution**: Route by client location
- **Performance-Based**: Route by server performance

### Configuration Management

#### Server Configuration
- Edit OpenVPN server configuration directly
- Real-time validation
- Configuration templates for common setups
- Backup before changes

#### Network Settings
- Port and protocol configuration
- DNS server settings
- Network topology
- Routing rules

#### Security Settings
- Encryption algorithms
- Authentication methods
- TLS version requirements
- Certificate parameters

### Backup & Restore

#### Creating Backups
- **Full System Backup**: All configurations, certificates, database
- **Configuration Only**: OpenVPN config files
- **Database Only**: Client history and statistics
- **Scheduled Backups**: Automated backup creation

#### Restore Process
1. Select backup from list
2. Choose restore scope
3. Confirm restoration
4. System automatically creates pre-restore backup

## 🔌 API Documentation

### Authentication

All API endpoints require HTTP Basic Authentication:

```bash
curl -u admin:password http://localhost:8822/api/status
```

### Core Endpoints

#### System Information
```bash
# Get server status
GET /api/status

# Get system metrics
GET /api/system_metrics

# Get server configuration
GET /api/server_config
```

#### Client Management
```bash
# List all clients
GET /api/clients

# Add new client
POST /api/clients
{
    "client_name": "john_doe",
    "expiry_days": 365,
    "group": "employees",
    "profile": "standard"
}

# Revoke client
POST /api/revoke_client
{
    "client_name": "john_doe"
}
```

#### Cluster Operations
```bash
# Get cluster status
GET /api/cluster/status

# Add server to cluster
POST /api/cluster/servers
{
    "server_id": "server-01",
    "server_name": "Primary Server",
    "host": "10.0.1.100",
    "ssh_user": "admin",
    "ssh_password": "password"
}

# Get cluster activity
GET /api/cluster/activity
```

### WebSocket Events

Real-time updates via WebSocket connection:

```javascript
const ws = new WebSocket('ws://localhost:8822/ws');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    switch(data.type) {
        case 'client_connected':
            updateClientStatus(data.client_name, 'online');
            break;
        case 'server_status_changed':
            updateServerStatus(data.status);
            break;
    }
};
```

## 🐳 Docker Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  openvpn-web-manager:
    build: .
    ports:
      - "8822:8822"
    volumes:
      - ./data:/app/data
      - /etc/openvpn:/etc/openvpn
    environment:
      - ADMIN_USERNAME=admin
      - ADMIN_PASSWORD=your-secure-password
    privileged: true
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - openvpn-web-manager
    restart: unless-stopped
```

### SSL Configuration

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    location / {
        proxy_pass http://openvpn-web-manager:8822;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔧 Troubleshooting

### Common Issues

#### Service Won't Start
```bash
# Check service status
sudo systemctl status openvpn-webmanager

# Check logs
sudo journalctl -u openvpn-webmanager -f

# Check Python dependencies
pip3 list | grep -E "(flask|sqlite)"
```

#### Can't Access Web Interface
```bash
# Check if port is open
sudo netstat -tulpn | grep 8822

# Check firewall
sudo ufw status
sudo ufw allow 8822

# Check service binding
sudo ss -tulpn | grep 8822
```

#### OpenVPN Integration Issues
```bash
# Check OpenVPN installation
openvpn --version

# Check configuration files
ls -la /etc/openvpn/server/

# Check EasyRSA installation
ls -la /etc/openvpn/server/easy-rsa/
```

### Performance Optimization

#### Database Optimization
```sql
-- Clean old session data
DELETE FROM client_sessions WHERE session_start < datetime('now', '-30 days');

-- Rebuild database
VACUUM;

-- Check database size
SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();
```

#### System Resources
```bash
# Monitor memory usage
free -h

# Monitor disk space
df -h

# Monitor CPU usage
top -p $(pgrep -f "python.*app.py")
```

## 🤝 Contributing

### Development Setup

```bash
# Clone repository
git clone https://github.com/georgi-dev215/openvpn-web-manager.git
cd openvpn-web-manager

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run in development mode
export FLASK_ENV=development
python app.py
```

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings for all functions and classes
- Write unit tests for new features

### Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Run tests: `python -m pytest`
6. Commit changes: `git commit -am 'Add new feature'`
7. Push to branch: `git push origin feature-name`
8. Submit a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- OpenVPN community for the excellent VPN software
- Flask framework for the web interface
- Bootstrap for the responsive UI components
- EasyRSA for certificate management
- All contributors and users of this project

## 📞 Support

- **Documentation**: [Wiki](https://github.com/georgi-dev215/openvpn-web-manager/wiki)
- **Issues**: [GitHub Issues](https://github.com/georgi-dev215/openvpn-web-manager/issues)
- **Email**: georgidev942@gmail.com

## 🗺️ Roadmap

### Version 2.1
- [ ] REST API v2 with OpenAPI documentation
- [ ] Advanced user role management
- [ ] Integration with external authentication (LDAP, OAuth)
- [ ] Enhanced monitoring with Prometheus metrics

### Version 2.2
- [ ] Mobile app for iOS and Android
- [ ] Advanced traffic shaping and QoS
- [ ] Multi-tenancy support
- [ ] Enhanced cluster management with Kubernetes

### Version 3.0
- [ ] Complete UI redesign with React
- [ ] Microservices architecture
- [ ] Advanced analytics and reporting
- [ ] Enterprise features and support

---

**Made with ❤️ for the OpenVPN community** 
