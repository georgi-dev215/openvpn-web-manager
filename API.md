# OpenVPN Cluster Manager API Documentation

This document provides comprehensive API documentation for OpenVPN Cluster Manager.

## Base URL

```
http://your-server:8822/api
```

## Authentication

All API endpoints require HTTP Basic Authentication:

```bash
curl -u admin:password http://your-server:8822/api/endpoint
```

## Response Format

All API responses follow this format:

```json
{
    "success": true,
    "data": {},
    "message": "Operation completed successfully",
    "timestamp": "2025-01-01T12:00:00Z"
}
```

Error responses:

```json
{
    "success": false,
    "error": "Error description",
    "code": 400,
    "timestamp": "2025-01-01T12:00:00Z"
}
```

## System Information

### Get Server Status

**GET** `/api/status`

Returns general server status and information.

**Response:**
```json
{
    "success": true,
    "data": {
        "server_status": true,
        "openvpn_version": "2.5.1",
        "clients_total": 25,
        "clients_active": 12,
        "clients_online": 8,
        "uptime": "5 days, 14:23:15",
        "system_load": "0.45, 0.52, 0.48"
    }
}
```

### Get System Metrics

**GET** `/api/system_metrics`

Returns detailed system performance metrics.

**Response:**
```json
{
    "success": true,
    "data": {
        "cpu_usage": 15.5,
        "memory_usage": 45.2,
        "disk_usage": 67.8,
        "network_rx": 1024000,
        "network_tx": 2048000,
        "timestamp": "2025-01-01T12:00:00Z"
    }
}
```

### Get Network Bandwidth

**GET** `/api/network_bandwidth`

Returns network bandwidth statistics.

**Response:**
```json
{
    "success": true,
    "data": {
        "interface": "eth0",
        "bytes_sent": 1073741824,
        "bytes_received": 2147483648,
        "packets_sent": 1000000,
        "packets_received": 1500000
    }
}
```

## Client Management

### List All Clients

**GET** `/api/clients`

Returns a list of all VPN clients.

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "name": "john_doe",
            "status": "active",
            "created_date": "2025-01-01",
            "expiry_date": "2026-01-01",
            "group": "employees",
            "profile": "standard",
            "last_activity": "2025-01-01T12:00:00Z"
        }
    ]
}
```

### Add New Client

**POST** `/api/clients`

Creates a new VPN client.

**Request Body:**
```json
{
    "client_name": "john_doe",
    "expiry_days": 365,
    "group": "employees",
    "profile": "standard"
}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "client_name": "john_doe",
        "config_file": "/path/to/john_doe.ovpn",
        "created_date": "2025-01-01T12:00:00Z"
    }
}
```

### Revoke Client

**POST** `/api/revoke_client`

Revokes a VPN client certificate.

**Request Body:**
```json
{
    "client_name": "john_doe"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Client john_doe revoked successfully"
}
```

### Renew Client

**POST** `/api/renew_client`

Renews a client certificate.

**Request Body:**
```json
{
    "client_name": "john_doe",
    "expiry_days": 365
}
```

### Get Client Activity

**GET** `/api/activity`

Returns recent client connection activity.

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "client_name": "john_doe",
            "action": "connected",
            "timestamp": "2025-01-01T12:00:00Z",
            "real_address": "192.168.1.100",
            "virtual_address": "10.8.0.2"
        }
    ]
}
```

### Get Client Traffic History

**GET** `/api/client_traffic/{client_name}`

Returns traffic statistics for a specific client.

**Parameters:**
- `client_name` - Name of the client
- `days` - Number of days to retrieve (optional, default: 30)

**Response:**
```json
{
    "success": true,
    "data": {
        "client_name": "john_doe",
        "total_bytes_sent": 1073741824,
        "total_bytes_received": 2147483648,
        "sessions": [
            {
                "start_time": "2025-01-01T12:00:00Z",
                "end_time": "2025-01-01T14:00:00Z",
                "bytes_sent": 104857600,
                "bytes_received": 209715200,
                "duration": 7200
            }
        ]
    }
}
```

## Bulk Operations

### Bulk Assign Group

**POST** `/api/bulk_assign_group`

Assigns multiple clients to a group.

**Request Body:**
```json
{
    "clients": ["john_doe", "jane_smith", "bob_johnson"],
    "group": "employees"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Successfully assigned 3 clients to group employees",
    "assigned_count": 3
}
```

### Export Clients

**GET** `/api/export_clients`

Exports client list as CSV file.

**Response:**
- Content-Type: `text/csv`
- File download with client information

## Configuration Management

### Get Server Configuration

**GET** `/api/server_config`

Returns OpenVPN server configuration.

**Response:**
```json
{
    "success": true,
    "data": {
        "port": 1194,
        "proto": "udp",
        "cipher": "AES-256-GCM",
        "auth": "SHA512",
        "server": "10.8.0.0 255.255.255.0",
        "raw_content": "# OpenVPN Server Configuration..."
    }
}
```

### Update Server Configuration

**POST** `/api/server_config`

Updates OpenVPN server configuration.

**Request Body:**
```json
{
    "port": 1194,
    "proto": "udp",
    "cipher": "AES-256-GCM",
    "custom_configs": "# Additional configurations..."
}
```

### Get Port Configuration

**GET** `/api/port_config`

Returns port mapping configuration.

**Response:**
```json
{
    "success": true,
    "data": {
        "internal_port": 1194,
        "external_port": 1194,
        "protocol": "udp"
    }
}
```

### Update Port Configuration

**POST** `/api/port_config`

Updates port mapping configuration.

**Request Body:**
```json
{
    "internal_port": 1194,
    "external_port": 443,
    "protocol": "tcp"
}
```

### Validate Configuration

**POST** `/api/validate_config`

Validates OpenVPN configuration files.

**Response:**
```json
{
    "success": true,
    "data": {
        "valid": true,
        "message": "Configuration is valid",
        "openvpn_test": "OpenVPN syntax test passed"
    }
}
```

## Backup Management

### List Backups

**GET** `/api/backups`

Returns list of available backups.

**Response:**
```json
{
    "success": true,
    "data": {
        "backups": [
            {
                "id": 1,
                "name": "backup_20250101_120000",
                "created_at": "2025-01-01T12:00:00Z",
                "size_mb": 15.2,
                "description": "Comprehensive system backup",
                "exists": true
            }
        ]
    }
}
```

### Create Backup

**POST** `/api/backup_configs`

Creates a new system backup.

**Response:**
```json
{
    "success": true,
    "data": {
        "backup_name": "backup_20250101_120000",
        "backup_path": "/app/backups/backup_20250101_120000.tar.gz",
        "backup_info": {
            "files_backed_up": 15,
            "database_backed_up": true,
            "size_mb": 15.2
        }
    }
}
```

### Download Backup

**GET** `/api/backups/{backup_id}/download`

Downloads a backup file.

**Response:**
- Content-Type: `application/gzip`
- File download

### Restore Backup

**POST** `/api/backups/{backup_id}/restore`

Restores system from backup.

**Response:**
```json
{
    "success": true,
    "message": "Backup restored successfully"
}
```

### Delete Backup

**DELETE** `/api/backups/{backup_id}`

Deletes a backup.

**Response:**
```json
{
    "success": true,
    "message": "Backup deleted successfully"
}
```

## Cluster Management

### Get Cluster Status

**GET** `/api/cluster/status`

Returns cluster overview and status.

**Response:**
```json
{
    "success": true,
    "data": {
        "total_servers": 5,
        "online_servers": 4,
        "total_clients": 150,
        "cluster_health": "healthy"
    }
}
```

### List Cluster Servers

**GET** `/api/cluster/servers`

Returns list of servers in the cluster.

**Response:**
```json
{
    "success": true,
    "data": {
        "servers": [
            {
                "id": "server-01",
                "name": "Primary Server",
                "host": "10.0.1.100",
                "status": "online",
                "clients_count": 25,
                "cpu_usage": 15.5,
                "memory_usage": 45.2
            }
        ]
    }
}
```

### Add Server to Cluster

**POST** `/api/cluster/servers`

Adds a new server to the cluster.

**Request Body:**
```json
{
    "server_id": "server-02",
    "server_name": "Secondary Server",
    "host": "10.0.1.101",
    "ssh_user": "admin",
    "ssh_password": "password",
    "ssh_port": 22,
    "openvpn_port": 1194
}
```

### Remove Server from Cluster

**DELETE** `/api/cluster/servers/{server_id}`

Removes a server from the cluster.

**Response:**
```json
{
    "success": true,
    "message": "Server server-02 removed from cluster"
}
```

### Test Server Connection

**POST** `/api/cluster/test_connection`

Tests SSH connection to a server.

**Request Body:**
```json
{
    "host": "10.0.1.101",
    "ssh_user": "admin",
    "ssh_password": "password",
    "ssh_port": 22
}
```

### Assign Client to Server

**POST** `/api/cluster/assign_client`

Assigns a client to a specific server.

**Request Body:**
```json
{
    "client_name": "john_doe",
    "server_id": "server-01",
    "strategy": "manual"
}
```

### Get Cluster Activity

**GET** `/api/cluster/activity`

Returns cluster activity log.

**Parameters:**
- `limit` - Number of activities to return (optional, default: 50)

**Response:**
```json
{
    "success": true,
    "data": {
        "activity": [
            {
                "timestamp": "2025-01-01T12:00:00Z",
                "activity_type": "server_added",
                "description": "Server server-02 added to cluster",
                "server_id": "server-02",
                "user_id": "admin"
            }
        ]
    }
}
```

## Error Codes

| Code | Description |
|------|-------------|
| 200  | Success |
| 400  | Bad Request - Invalid parameters |
| 401  | Unauthorized - Authentication required |
| 403  | Forbidden - Insufficient permissions |
| 404  | Not Found - Resource not found |
| 409  | Conflict - Resource already exists |
| 500  | Internal Server Error |

## Rate Limiting

API endpoints are rate-limited to prevent abuse:

- General API: 100 requests per minute
- Authentication: 10 requests per minute
- Bulk operations: 5 requests per minute

Rate limit headers are included in responses:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## WebSocket Events

Real-time updates are available via WebSocket connection at `/ws`:

```javascript
const ws = new WebSocket('ws://your-server:8822/ws');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Event:', data.type, data.payload);
};
```

### Event Types

- `client_connected` - Client connection established
- `client_disconnected` - Client disconnected
- `server_status_changed` - Server status update
- `cluster_event` - Cluster-related event
- `backup_completed` - Backup operation completed

## SDKs and Libraries

### Python SDK

```python
from openvpn_manager import OpenVPNManagerClient

client = OpenVPNManagerClient(
    base_url="http://your-server:8822",
    username="admin",
    password="password"
)

# Get server status
status = client.get_status()

# Add client
result = client.add_client("john_doe", expiry_days=365)

# List clients
clients = client.list_clients()
```

### JavaScript SDK

```javascript
const OpenVPNManager = require('openvpn-manager-js');

const client = new OpenVPNManager({
    baseURL: 'http://your-server:8822',
    auth: {
        username: 'admin',
        password: 'password'
    }
});

// Get server status
const status = await client.getStatus();

// Add client
const result = await client.addClient('john_doe', { expiryDays: 365 });
```

## Examples

### Complete Client Lifecycle

```bash
# Create client
curl -u admin:password -X POST \
  http://your-server:8822/api/clients \
  -H "Content-Type: application/json" \
  -d '{"client_name": "john_doe", "expiry_days": 365}'

# Check client status
curl -u admin:password \
  http://your-server:8822/api/clients

# Download configuration
curl -u admin:password \
  http://your-server:8822/download_config/john_doe \
  -o john_doe.ovpn

# Monitor activity
curl -u admin:password \
  http://your-server:8822/api/activity

# Revoke client
curl -u admin:password -X POST \
  http://your-server:8822/api/revoke_client \
  -H "Content-Type: application/json" \
  -d '{"client_name": "john_doe"}'
```

### Cluster Management

```bash
# Add server to cluster
curl -u admin:password -X POST \
  http://your-server:8822/api/cluster/servers \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "server-02",
    "server_name": "Secondary Server",
    "host": "10.0.1.101",
    "ssh_user": "admin",
    "ssh_password": "password"
  }'

# Assign client to server
curl -u admin:password -X POST \
  http://your-server:8822/api/cluster/assign_client \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "john_doe",
    "server_id": "server-02",
    "strategy": "manual"
  }'

# Get cluster status
curl -u admin:password \
  http://your-server:8822/api/cluster/status
```

---

For more information, visit the [project documentation](https://github.com/yourusername/openvpn-manager/wiki). 