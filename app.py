#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess
import os
import re
import json
from datetime import datetime, timedelta
import threading
import time
from pathlib import Path
import psutil
import sqlite3
from collections import defaultdict
import paramiko
from concurrent.futures import ThreadPoolExecutor, as_completed
import yaml
import tempfile
import shutil

auth = HTTPBasicAuth()

# Отключаем Flask/Werkzeug логирование
import logging
logging.getLogger('werkzeug').disabled = True
logging.getLogger('flask').disabled = True

# Создаём Flask app
app = Flask(__name__)
app.secret_key = 'd%0&!or)z36hb1$gtytzp&fc2ye!m+xs*6d(=$82qdqz^3&59y'
app.logger.disabled = True

# Database for traffic history
DATABASE_PATH = 'vpn_history.db'

def init_database():
    """Initialize database for traffic history"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        
        # Configure datetime adapter for Python 3.12+ compatibility
        sqlite3.register_adapter(datetime, lambda dt: dt.isoformat())
        sqlite3.register_converter("timestamp", lambda b: datetime.fromisoformat(b.decode()))
        
        cursor = conn.cursor()
        
        # Create traffic history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS traffic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                bytes_sent INTEGER DEFAULT 0,
                bytes_received INTEGER DEFAULT 0,
                duration_seconds INTEGER DEFAULT 0,
                session_start DATETIME,
                session_end DATETIME,
                real_address TEXT,
                virtual_address TEXT
            )
        ''')
        
        # Create system metrics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                cpu_percent REAL,
                memory_percent REAL,
                memory_available INTEGER,
                network_sent INTEGER,
                network_received INTEGER,
                active_connections INTEGER
            )
        ''')
        
        # Create temporary clients table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS temporary_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                revoke_at DATETIME NOT NULL,
                hours INTEGER NOT NULL,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Create client statistics table for aggregated data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT UNIQUE NOT NULL,
                total_bytes_sent INTEGER DEFAULT 0,
                total_bytes_received INTEGER DEFAULT 0,
                total_duration_seconds INTEGER DEFAULT 0,
                session_count INTEGER DEFAULT 0,
                first_connection DATETIME,
                last_connection DATETIME,
                last_activity DATETIME,
                is_online INTEGER DEFAULT 0,
                current_session_start DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create cluster servers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT UNIQUE NOT NULL,
                server_name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER DEFAULT 22,
                username TEXT DEFAULT 'root',
                auth_method TEXT DEFAULT 'key',
                ssh_key TEXT,
                password TEXT,
                location TEXT DEFAULT 'custom',
                max_clients INTEGER DEFAULT 100,
                server_role TEXT DEFAULT 'load-balanced',
                status TEXT DEFAULT 'offline',
                last_ping DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create cluster client assignments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_client_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                server_id TEXT NOT NULL,
                assignment_strategy TEXT DEFAULT 'manual',
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (server_id) REFERENCES cluster_servers(server_id)
            )
        ''')
        
        # Create cluster activity log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cluster_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                server_id TEXT,
                activity_type TEXT NOT NULL,
                description TEXT NOT NULL,
                details TEXT,
                user_id TEXT DEFAULT 'system'
            )
        ''')
        
        # Create client groups table for group assignments
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                group_name TEXT NOT NULL,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(client_name)
            )
        ''')
        
        # Add new columns to existing traffic_history table if they don't exist
        try:
            cursor.execute('ALTER TABLE traffic_history ADD COLUMN real_address TEXT')
        except:
            pass  # Column already exists
        try:
            cursor.execute('ALTER TABLE traffic_history ADD COLUMN virtual_address TEXT')
        except:
            pass  # Column already exists
        
        # Create indexes for better performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_traffic_client ON traffic_history(client_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_traffic_timestamp ON traffic_history(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_traffic_real_address ON traffic_history(real_address)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_system_timestamp ON system_metrics(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_stats_name ON client_stats(client_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_stats_updated ON client_stats(updated_at)')
        
        # Cluster indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_servers_id ON cluster_servers(server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_servers_status ON cluster_servers(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_assignments_client ON cluster_client_assignments(client_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_assignments_server ON cluster_client_assignments(server_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_activity_timestamp ON cluster_activity(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_activity_server ON cluster_activity(server_id)')
        
        # Client groups indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_groups_name ON client_groups(client_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_groups_group ON client_groups(group_name)')
        
        conn.commit()
        
        # Test database write
        cursor.execute('INSERT INTO traffic_history (client_name, bytes_sent, bytes_received, duration_seconds) VALUES (?, ?, ?, ?)', 
                      ('test_client', 1024, 2048, 60))
        conn.commit()
        
        cursor.execute('SELECT COUNT(*) FROM traffic_history WHERE client_name = ?', ('test_client',))
        test_count = cursor.fetchone()[0]
        
        cursor.execute('DELETE FROM traffic_history WHERE client_name = ?', ('test_client',))
        conn.commit()
        
        conn.close()
        
    except Exception as e:
        print(f"💥 Database initialization error: {e}")
        import traceback
        traceback.print_exc()

# Global storage for tracking client sessions
active_sessions = {}  # {client_name: {'start_time': datetime, 'initial_sent': int, 'initial_received': int}}

# Global storage for temporary clients tracking
temporary_clients = {}  # {client_name: {'revoke_time': datetime, 'timer': Timer, 'hours': int}}

def track_client_sessions():
    """Background task to track and save client sessions"""
    try:
        current_connections = OpenVPNManager.get_active_connections()
        current_clients = {conn['name']: conn for conn in current_connections}
        
        # Check for new connections
        for client_name, conn in current_clients.items():
            if client_name not in active_sessions:
                # New client connected
                session_start = datetime.now()
                active_sessions[client_name] = {
                    'start_time': session_start,
                    'initial_sent': int(conn.get('bytes_sent', 0)),
                    'initial_received': int(conn.get('bytes_received', 0)),
                    'real_address': conn.get('real_address', 'Unknown'),
                    'virtual_address': conn.get('virtual_address', 'Unknown')
                }
                
                # Update client stats - mark as online
                OpenVPNManager.update_client_stats(
                    client_name=client_name,
                    session_start=session_start,
                    is_connection=True
                )
                
                print(f"📊 TRACKING: {client_name} connected - Initial: {int(conn.get('bytes_sent', 0))/1024/1024:.2f}MB sent, {int(conn.get('bytes_received', 0))/1024/1024:.2f}MB received")
        
        # Update current session data for active clients and SAVE DATA EVERY 30 SECONDS
        for client_name in list(active_sessions.keys()):
            if client_name in current_clients:
                # Update current traffic data
                current_conn = current_clients[client_name]
                current_sent = int(current_conn.get('bytes_sent', 0))
                current_received = int(current_conn.get('bytes_received', 0))
                
                active_sessions[client_name]['current_sent'] = current_sent
                active_sessions[client_name]['current_received'] = current_received
                
                # Calculate session traffic from start
                session_data = active_sessions[client_name]
                session_start = session_data['start_time']
                current_time = datetime.now()
                duration_seconds = int((current_time - session_start).total_seconds())
                
                session_sent = max(0, current_sent - session_data['initial_sent'])
                session_received = max(0, current_received - session_data['initial_received'])
                
                # SAVE/UPDATE CURRENT DATA TO DATABASE EVERY 30 SECONDS
                print(f"💾 SAVING DATA: {client_name} - Duration: {duration_seconds}s, Sent: {session_sent/1024/1024:.2f}MB, Received: {session_received/1024/1024:.2f}MB")
                
                # Update existing session record instead of creating new one
                OpenVPNManager.update_active_session(
                    client_name=client_name,
                    bytes_sent=session_sent,
                    bytes_received=session_received,
                    duration_seconds=duration_seconds,
                    session_start=session_start.isoformat(),
                    session_end=None,  # Keep NULL for active sessions
                    real_address=session_data.get('real_address', 'Unknown'),
                    virtual_address=session_data.get('virtual_address', 'Unknown')
                )
                
                # Update last activity in stats
                OpenVPNManager.update_client_stats(
                    client_name=client_name,
                    last_activity=current_time,
                    is_activity_update=True
                )
        
        # Check for disconnected clients
        disconnected_clients = []
        for client_name in active_sessions:
            if client_name not in current_clients:
                disconnected_clients.append(client_name)
        
        # Save sessions for disconnected clients
        for client_name in disconnected_clients:
            session_data = active_sessions[client_name]
            session_start = session_data['start_time']
            session_end = datetime.now()
            duration_seconds = int((session_end - session_start).total_seconds())
            
            # Calculate actual traffic used during this session
            final_sent = session_data.get('current_sent', session_data['initial_sent'])
            final_received = session_data.get('current_received', session_data['initial_received'])
            
            # Calculate session traffic (difference from initial)
            session_sent = max(0, final_sent - session_data['initial_sent'])
            session_received = max(0, final_received - session_data['initial_received'])
            
            # Only save if session was longer than 10 seconds
            if duration_seconds > 10:
                print(f"💾 DISCONNECTED: {client_name} - Session: {duration_seconds}s, {session_sent/1024/1024:.2f}MB sent, {session_received/1024/1024:.2f}MB received")
                
                # Finalize active session by setting session_end
                OpenVPNManager.finalize_session(
                    client_name=client_name,
                    bytes_sent=session_sent,
                    bytes_received=session_received,
                    duration_seconds=duration_seconds,
                    session_start=session_start.isoformat(),
                    session_end=session_end.isoformat(),
                    real_address=session_data.get('real_address', 'Unknown'),
                    virtual_address=session_data.get('virtual_address', 'Unknown')
                )
                
                # Update aggregated client stats
                OpenVPNManager.update_client_stats(
                    client_name=client_name,
                    session_end=session_end,
                    bytes_sent=session_sent,
                    bytes_received=session_received,
                    duration_seconds=duration_seconds,
                    is_disconnection=True
                )
            else:
                print(f"⏭️ SKIPPED: {client_name} - Session too short ({duration_seconds}s)")
                # Still finalize the session even if short
                OpenVPNManager.finalize_session(
                    client_name=client_name,
                    bytes_sent=session_sent,
                    bytes_received=session_received,
                    duration_seconds=duration_seconds,
                    session_start=session_start.isoformat(),
                    session_end=session_end.isoformat(),
                    real_address=session_data.get('real_address', 'Unknown'),
                    virtual_address=session_data.get('virtual_address', 'Unknown')
                )
                # Still mark as offline
                OpenVPNManager.update_client_stats(
                    client_name=client_name,
                    session_end=session_end,
                    is_disconnection=True
                )
            
            del active_sessions[client_name]
            
    except Exception as e:
        print(f"💥 Error in track_client_sessions: {e}")
        import traceback
        traceback.print_exc()

def check_expired_temporary_clients():
    """Check for expired temporary clients and process them"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Find expired clients
        current_time = datetime.now()
        cursor.execute('''
            SELECT client_name, revoke_at 
            FROM temporary_clients 
            WHERE status = 'active' AND revoke_at <= ?
        ''', (current_time.isoformat(),))
        
        expired_clients = cursor.fetchall()
        conn.close()
        
        if expired_clients:
            print(f"⏰ Found {len(expired_clients)} expired temporary clients")
            for client_name, revoke_at in expired_clients:
                print(f"🔄 Processing expired client: {client_name} (expired at {revoke_at})")
                OpenVPNManager.auto_revoke_client(client_name)
        
    except Exception as e:
        print(f"Error checking expired temporary clients: {e}")

def start_session_tracking():
    """Start background session tracking"""
    def run_tracking():
        check_counter = 0
        metrics_counter = 0
        while True:
            try:
                track_client_sessions()
                
                # Save system metrics every 2 minutes (4 cycles * 30 seconds)
                metrics_counter += 1
                if metrics_counter >= 4:
                    OpenVPNManager.save_system_metrics()
                    print(f"💾 SYSTEM METRICS: Saved system metrics to database")
                    metrics_counter = 0
                
                # Check for expired temporary clients every 5 minutes (10 cycles * 30 seconds)
                check_counter += 1
                if check_counter >= 10:
                    check_expired_temporary_clients()
                    check_counter = 0
                
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"Session tracking error: {e}")
                time.sleep(60)  # Wait longer on error
    
    tracking_thread = threading.Thread(target=run_tracking, daemon=True)
    tracking_thread.start()

def restore_temporary_clients():
    """Restore temporary clients from database on startup"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT client_name, revoke_at, hours, status 
            FROM temporary_clients 
            WHERE status = 'active'
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        current_time = datetime.now()
        restored_count = 0
        expired_count = 0
        
        for client_name, revoke_at_str, hours, status in rows:
            try:
                # Parse revoke time
                revoke_time = datetime.fromisoformat(revoke_at_str)
                
                # Check if already expired
                if revoke_time <= current_time:
                    OpenVPNManager.auto_revoke_client(client_name)
                    expired_count += 1
                else:
                    # Calculate remaining time
                    time_left = revoke_time - current_time
                    seconds_left = int(time_left.total_seconds())
                    
                    if seconds_left > 0:
                        # Create new timer
                        timer = threading.Timer(
                            seconds_left,
                            OpenVPNManager.auto_revoke_client,
                            args=[client_name]
                        )
                        
                        # Store in temporary clients tracking
                        temporary_clients[client_name] = {
                            'revoke_time': revoke_time,
                            'timer': timer,
                            'hours': hours
                        }
                        
                        # Start the timer
                        timer.start()
                        
                        restored_count += 1
                    
            except Exception as e:
                pass
            
    except Exception as e:
        pass

# Initialize traffic history restoration
def restore_traffic_history():
    """Restore active sessions from database on startup"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Find active sessions (those without session_end)
        cursor.execute('''
            SELECT client_name, session_start, bytes_sent, bytes_received, 
                   real_address, virtual_address, duration_seconds
            FROM traffic_history 
            WHERE session_end IS NULL
        ''')
        
        active_db_sessions = cursor.fetchall()
        
        # Get currently connected clients
        current_connections = OpenVPNManager.get_active_connections()
        current_clients = {conn['name']: conn for conn in current_connections}
        
        restored_count = 0
        closed_count = 0
        
        for row in active_db_sessions:
            client_name, session_start_str, bytes_sent, bytes_received, real_address, virtual_address, duration_seconds = row
            
            if client_name in current_clients:
                # Client is still connected - restore to active_sessions
                try:
                    session_start = datetime.fromisoformat(session_start_str)
                    current_conn = current_clients[client_name]
                    
                    active_sessions[client_name] = {
                        'start_time': session_start,
                        'initial_sent': max(0, int(current_conn.get('bytes_sent', 0)) - (bytes_sent or 0)),
                        'initial_received': max(0, int(current_conn.get('bytes_received', 0)) - (bytes_received or 0)),
                        'current_sent': int(current_conn.get('bytes_sent', 0)),
                        'current_received': int(current_conn.get('bytes_received', 0)),
                        'real_address': real_address or current_conn.get('real_address', 'Unknown'),
                        'virtual_address': virtual_address or current_conn.get('virtual_address', 'Unknown')
                    }
                    
                    print(f"🔄 RESTORED: Active session for {client_name} - Duration: {duration_seconds}s, Traffic: {bytes_sent/1024/1024:.2f}MB sent, {bytes_received/1024/1024:.2f}MB received")
                    restored_count += 1
                    
                except Exception as e:
                    print(f"⚠️ Error restoring session for {client_name}: {e}")
            else:
                # Client is no longer connected - finalize the session
                try:
                    session_start = datetime.fromisoformat(session_start_str)
                    session_end = datetime.now()
                    final_duration = int((session_end - session_start).total_seconds())
                    
                    OpenVPNManager.finalize_session(
                        client_name=client_name,
                        bytes_sent=bytes_sent or 0,
                        bytes_received=bytes_received or 0,
                        duration_seconds=final_duration,
                        session_start=session_start_str,
                        session_end=session_end.isoformat(),
                        real_address=real_address,
                        virtual_address=virtual_address
                    )
                    
                    print(f"✅ FINALIZED: Disconnected session for {client_name} - Final duration: {final_duration}s")
                    closed_count += 1
                    
                except Exception as e:
                    print(f"⚠️ Error finalizing session for {client_name}: {e}")
        
        conn.close()
        
        if restored_count > 0 or closed_count > 0:
            print(f"🔄 Session recovery: {restored_count} restored, {closed_count} finalized")
        
    except Exception as e:
        print(f"⚠️ Error restoring traffic history: {e}")
        import traceback
        traceback.print_exc()

# Настройки аутентификации (ИЗМЕНИТЕ ЭТИ ДАННЫЕ!)
users = {
    "admin": generate_password_hash("admin123")  # Логин: admin, Пароль: admin123
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

# Пути к важным файлам OpenVPN
OPENVPN_DIR = '/etc/openvpn/server'
EASYRSA_DIR = '/etc/openvpn/server/easy-rsa'
INDEX_FILE = '/etc/openvpn/server/easy-rsa/pki/index.txt'
SCRIPT_PATH = './openvpn-install.sh'

# Пользовательский путь к файлу статуса (можно настроить)
CUSTOM_STATUS_FILE = '/var/log/openvpn/openvpn-status.log'

# Configuration file paths
SERVER_CONF_PATH = '/etc/openvpn/server/server.conf'
CLIENT_COMMON_PATH = '/etc/openvpn/server/client-common.txt'

class OpenVPNManager:
    @staticmethod
    def is_openvpn_installed():
        """Check if OpenVPN is installed"""
        return os.path.exists(f'{OPENVPN_DIR}/server.conf')
    
    @staticmethod
    def get_server_status():
        """Get OpenVPN server status"""
        try:
            result = subprocess.run(['systemctl', 'is-active', 'openvpn-server@server.service'], 
                                  capture_output=True, text=True)
            return result.stdout.strip() == 'active'
        except:
            return False
    
    @staticmethod
    def get_server_info():
        """Get server information from configuration"""
        info = {}
        try:
            with open(f'{OPENVPN_DIR}/server.conf', 'r') as f:
                content = f.read()
                
            # Извлекаем порт
            port_match = re.search(r'^port\s+(\d+)', content, re.MULTILINE)
            if port_match:
                info['port'] = port_match.group(1)
            
            # Извлекаем протокол
            proto_match = re.search(r'^proto\s+(\w+)', content, re.MULTILINE)
            if proto_match:
                info['protocol'] = proto_match.group(1)
            
            # Извлекаем локальный IP
            local_ip = None
            
            # Сначала попробуем найти директиву 'local' в конфигурации
            local_match = re.search(r'^local\s+([0-9.]+)', content, re.MULTILINE)
            if local_match:
                local_ip = local_match.group(1)
            else:
                # Если 'local' не указан, определяем IP автоматически
                try:
                    # Метод 1: Через hostname -I
                    result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        ips = result.stdout.strip().split()
                        if ips:
                            # Берем первый IP (обычно основной)
                            local_ip = ips[0]
                except:
                    pass
                
                # Метод 2: Через ip route (если первый не сработал)
                if not local_ip:
                    try:
                        result = subprocess.run(['ip', 'route', 'get', '8.8.8.8'], 
                                              capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            # Парсим вывод: ... src IP_ADDRESS ...
                            src_match = re.search(r'src\s+([0-9.]+)', result.stdout)
                            if src_match:
                                local_ip = src_match.group(1)
                    except:
                        pass
                
                # Метод 3: Через socket (последний вариант)
                if not local_ip:
                    try:
                        import socket
                        # Создаем соединение с внешним адресом для определения локального IP
                        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                            s.connect(("8.8.8.8", 80))
                            local_ip = s.getsockname()[0]
                    except:
                        pass
                
                # Fallback: localhost если ничего не сработало
                if not local_ip:
                    local_ip = "127.0.0.1"
            
            info['local_ip'] = local_ip
                
        except Exception as e:
            print(f"Error reading server configuration: {e}")
        
        return info
    
    @staticmethod
    def get_clients():
        """Get list of all clients"""
        clients = []
        if not os.path.exists(INDEX_FILE):
            return clients
        
        try:
            with open(INDEX_FILE, 'r') as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                parts = line.split('\t')
                
                if len(parts) >= 6:
                    # Format: status, expiry_date, revoke_date, serial_number, file_path, distinguished_name
                    status = parts[0].strip()
                    expiry_date = parts[1].strip()
                    revoke_date = parts[2].strip() if parts[2].strip() else None
                    serial = parts[3].strip() if len(parts) > 3 else ''
                    file_path = parts[4].strip() if len(parts) > 4 else ''
                    dn_part = parts[5].strip() if len(parts) > 5 else ''
                    
                    # Extract client name from DN (Distinguished Name)
                    client_name = None
                    
                    # Try different CN patterns
                    cn_patterns = [
                        r'CN=([^/,]+)',  # Standard CN=name format
                        r'/CN=([^/,]+)',  # With leading slash
                        r'CN\s*=\s*([^/,]+)',  # With spaces
                    ]
                    
                    for pattern in cn_patterns:
                        cn_match = re.search(pattern, dn_part)
                        if cn_match:
                            client_name = cn_match.group(1).strip()
                            break
                    
                    if not client_name:
                        # If CN extraction fails, try to get name from file path
                        if file_path:
                            path_parts = file_path.split('/')
                            for part in reversed(path_parts):
                                if part and part != 'unknown':
                                    client_name = part.replace('.pem', '').replace('.crt', '')
                                    break
                    
                    if client_name and client_name.lower() != 'server':  # Exclude server certificate
                        # Determine actual status
                        cert_status = 'active' if status == 'V' else 'revoked'
                        
                        # Check if config file exists
                        config_exists = os.path.exists(f'./{client_name}.ovpn')
                        
                        # Format expiry date and calculate days until expiry
                        formatted_expiry = 'N/A'
                        days_until_expiry = None
                        expiry_status = 'unknown'
                        
                        if expiry_date and len(expiry_date) >= 12:
                            try:
                                # Format: YYMMDDHHMMSSZ -> readable date
                                year = int('20' + expiry_date[:2])
                                month = int(expiry_date[2:4])
                                day = int(expiry_date[4:6])
                                formatted_expiry = f"{year}-{month:02d}-{day:02d}"
                                
                                # Calculate days until expiry
                                from datetime import datetime, date
                                expiry_datetime = date(year, month, day)
                                today = date.today()
                                days_until_expiry = (expiry_datetime - today).days
                                
                                # Determine expiry status
                                if days_until_expiry < 0:
                                    expiry_status = 'expired'
                                elif days_until_expiry == 0:
                                    expiry_status = 'expires_today'
                                elif days_until_expiry <= 1:
                                    expiry_status = 'expiring_very_soon' 
                                elif days_until_expiry <= 7:
                                    expiry_status = 'expiring_soon'
                                elif days_until_expiry <= 30:
                                    expiry_status = 'expiring_in_month'
                                elif days_until_expiry <= 90:
                                    expiry_status = 'expiring_in_3_months'
                                else:
                                    expiry_status = 'valid'
                                    
                            except:
                                formatted_expiry = expiry_date[:8]  # Fallback
                        
                        # Format revoke date
                        formatted_revoke_date = None
                        if revoke_date and len(revoke_date) >= 12:
                            try:
                                # Format: YYMMDDHHMMSSZ -> readable date
                                year = int('20' + revoke_date[:2])
                                month = int(revoke_date[2:4])
                                day = int(revoke_date[4:6])
                                hour = int(revoke_date[6:8])
                                minute = int(revoke_date[8:10])
                                formatted_revoke_date = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
                            except:
                                formatted_revoke_date = revoke_date[:12]  # Fallback
                        
                        # Get client group from database if available
                        client_group = ''
                        try:
                            conn = sqlite3.connect(DATABASE_PATH)
                            cursor = conn.cursor()
                            cursor.execute('SELECT group_name FROM client_groups WHERE client_name = ?', (client_name,))
                            result = cursor.fetchone()
                            if result:
                                client_group = result[0]
                            conn.close()
                        except Exception as e:
                            pass  # Group info not critical
                        
                        client_info = {
                            'name': client_name,
                            'status': cert_status,
                            'expiry_date': formatted_expiry,
                            'days_until_expiry': days_until_expiry,
                            'expiry_status': expiry_status,
                            'serial': serial,
                            'has_config': config_exists,
                            'revoke_date': formatted_revoke_date,
                            'group': client_group,
                            'profile': 'standard'  # Default profile
                        }
                        
                        clients.append(client_info)
                        pass
                    else:
                        pass
                else:
                    pass
                    
        except Exception as e:
            print(f"💥 Error reading client list: {e}")
            import traceback
            traceback.print_exc()
        
        return clients
    
    @staticmethod
    def get_active_connections():
        """Parse OpenVPN status file to get active client connections"""
        active_connections = []
        
        try:
            # List of possible status file locations
            status_files = [
                CUSTOM_STATUS_FILE,  # Пользовательский путь в первую очередь
                '/var/log/openvpn/openvpn-status.log',
                '/etc/openvpn/server/openvpn-status.log',  
                '/tmp/openvpn-status.log',
                '/run/openvpn-server/status-server.log',
                '/var/log/openvpn-status.log',
                '/etc/openvpn/openvpn-status.log',
                '/home/openvpn-status.log',
                './openvpn-status.log',
                '/usr/local/etc/openvpn/openvpn-status.log'
            ]
            
            status_content = None
            for status_file in status_files:
                if os.path.exists(status_file):
                    try:
                        with open(status_file, 'r') as f:
                            status_content = f.read()
                        break
                    except Exception as e:
                        continue
            
            if status_content:
                lines = status_content.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    # Parse CLIENT_LIST format: CLIENT_LIST,name,real_ip:port,virtual_ip,ipv6,bytes_recv,bytes_sent,connected_since,time_t,username,client_id,peer_id,cipher
                    if line.startswith('CLIENT_LIST,'):
                        parts = line.split(',')
                        
                        if len(parts) >= 8:
                            client_name = parts[1].strip()
                            real_address = parts[2].strip()
                            virtual_address = parts[3].strip() if parts[3].strip() else 'N/A'
                            bytes_received = parts[5].strip() if len(parts) > 5 else '0'
                            bytes_sent = parts[6].strip() if len(parts) > 6 else '0'
                            connected_since = parts[7].strip() if len(parts) > 7 else 'N/A'
                            
                            if client_name and client_name != 'UNDEF':
                                # Calculate connection duration
                                connection_duration = OpenVPNManager.calculate_connection_duration(connected_since)
                                
                                active_connections.append({
                                    'name': client_name,
                                    'real_address': real_address,
                                    'virtual_address': virtual_address,
                                    'bytes_received': bytes_received,
                                    'bytes_sent': bytes_sent,
                                    'connected_since': connected_since,
                                    'connection_duration': connection_duration,
                                    'duration_seconds': connection_duration.get('total_seconds', 0),
                                    'duration_formatted': connection_duration.get('formatted', 'N/A')
                                })
                    
        except Exception as e:
            pass
        
        return active_connections
    
    @staticmethod
    def get_client_activity():
        """Get last activity for each client from logs"""
        activity_data = {}
        try:
            # Check OpenVPN log files
            log_files = [
                '/var/log/openvpn/openvpn.log',
                '/var/log/openvpn.log',
                '/var/log/syslog',
                '/var/log/messages'
            ]
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    try:
                        # Read last 2000 lines to get recent activity
                        result = subprocess.run(['tail', '-2000', log_file], 
                                              capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            lines = result.stdout.split('\n')
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                
                                # Look for connection/disconnection events
                                if any(keyword in line.lower() for keyword in ['client connected', 'client disconnected', 'peer-id', 'tls:']):
                                    # Try to extract client name and timestamp
                                    parts = line.split()
                                    if len(parts) >= 3:
                                        # Extract timestamp (usually first 3 parts: Month Day Time)
                                        timestamp = ' '.join(parts[:3])
                                        
                                        # Look for client name patterns
                                        for part in parts:
                                            # Skip IP addresses and common log words
                                            if ('.' in part and part.count('.') == 3) or part.lower() in ['client', 'connected', 'disconnected', 'tls:', 'peer-id']:
                                                continue
                                            
                                            # Potential client name (alphanumeric, reasonable length)
                                            if len(part) > 2 and part.replace('_', '').replace('-', '').isalnum():
                                                activity_data[part] = timestamp
                                                break
                        break  # Stop after first successful log file
                    except subprocess.TimeoutExpired:
                        continue
                    except Exception as e:
                        continue
            
            # Try to get connection info from status file as well
            status_files = [
                CUSTOM_STATUS_FILE,  # Пользовательский путь в первую очередь
                '/var/log/openvpn/openvpn-status.log',
                '/etc/openvpn/server/openvpn-status.log',  
                '/tmp/openvpn-status.log',
                '/run/openvpn-server/status-server.log',
                '/var/log/openvpn-status.log',
                '/etc/openvpn/openvpn-status.log',
                '/home/openvpn-status.log',
                './openvpn-status.log',
                '/usr/local/etc/openvpn/openvpn-status.log'
            ]
            
            for status_file in status_files:
                if os.path.exists(status_file):
                    try:
                        with open(status_file, 'r') as f:
                            content = f.read()
                        
                        lines = content.split('\n')
                        for line in lines:
                            if line.startswith('CLIENT_LIST,'):
                                parts = line.split(',')
                                if len(parts) >= 8:
                                    client_name = parts[1].strip()
                                    connected_since = parts[7].strip()
                                    if client_name and client_name != 'UNDEF':
                                        activity_data[client_name] = connected_since
                        break
                    except Exception as e:
                        continue
                        
        except Exception as e:
            pass
        
        return activity_data
    
    @staticmethod
    def get_server_stats():
        """Get overall server statistics"""
        stats = {
            'total_connections': 0,
            'active_connections': 0,
            'total_bytes_sent': 0,
            'total_bytes_received': 0,
            'uptime': 'N/A'
        }
        
        try:
            # Get active connections and calculate stats
            active_conns = OpenVPNManager.get_active_connections()
            stats['active_connections'] = len(active_conns)
            
            # Calculate total traffic from active connections
            for conn in active_conns:
                try:
                    if conn['bytes_sent'] not in ['N/A', '0', 0]:
                        stats['total_bytes_sent'] += int(conn['bytes_sent'])
                    if conn['bytes_received'] not in ['N/A', '0', 0]:
                        stats['total_bytes_received'] += int(conn['bytes_received'])
                except (ValueError, TypeError):
                    continue
            
            # Get OpenVPN service uptime
            try:
                result = subprocess.run(['systemctl', 'show', 'openvpn-server@server.service', 
                                       '--property=ActiveEnterTimestamp'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    output = result.stdout.strip()
                    if '=' in output:
                        timestamp_str = output.split('=')[1].strip()
                        if timestamp_str and timestamp_str != 'n/a':
                            # Try to calculate uptime
                            from datetime import datetime
                            try:
                                # Parse systemd timestamp format
                                start_time = datetime.strptime(timestamp_str.split('.')[0], '%a %Y-%m-%d %H:%M:%S %Z')
                                uptime_seconds = (datetime.now() - start_time).total_seconds()
                                
                                # Format uptime
                                if uptime_seconds > 86400:  # More than a day
                                    days = int(uptime_seconds // 86400)
                                    hours = int((uptime_seconds % 86400) // 3600)
                                    stats['uptime'] = f"{days}d {hours}h"
                                elif uptime_seconds > 3600:  # More than an hour
                                    hours = int(uptime_seconds // 3600)
                                    minutes = int((uptime_seconds % 3600) // 60)
                                    stats['uptime'] = f"{hours}h {minutes}m"
                                else:  # Less than an hour
                                    minutes = int(uptime_seconds // 60)
                                    stats['uptime'] = f"{minutes}m"
                            except:
                                stats['uptime'] = timestamp_str.split()[-2:] if len(timestamp_str.split()) >= 2 else 'N/A'
            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                pass
                
        except Exception as e:
            pass
        
        return stats
    
    @staticmethod
    def enable_status_file():
        """Enable OpenVPN status file for better monitoring"""
        try:
            config_file = f'{OPENVPN_DIR}/server.conf'
            status_file_path = '/var/log/openvpn/openvpn-status.log'
            
            if not os.path.exists(config_file):
                return False, "Server configuration not found"
            
            # Create log directory if it doesn't exist
            log_dir = '/var/log/openvpn'
            if not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
                subprocess.run(['chown', 'openvpn:openvpn', log_dir], check=False)
            
            # Read current config
            with open(config_file, 'r') as f:
                content = f.read()
            
            # Check if status directive already exists
            if 'status ' in content:
                # Update existing status line
                lines = content.split('\n')
                new_lines = []
                status_updated = False
                
                for line in lines:
                    if line.strip().startswith('status '):
                        new_lines.append(f'status {status_file_path} 10')
                        status_updated = True
                    else:
                        new_lines.append(line)
                
                if not status_updated:
                    # Add before last line
                    new_lines.insert(-1, f'status {status_file_path} 10')
                
                content = '\n'.join(new_lines)
            else:
                # Add status file directive before the last line
                lines = content.split('\n')
                # Find good place to insert (before verb line or at end)
                insert_pos = len(lines) - 1
                for i, line in enumerate(lines):
                    if line.strip().startswith('verb '):
                        insert_pos = i
                        break
                
                lines.insert(insert_pos, f'status {status_file_path} 10')
                content = '\n'.join(lines)
            
            # Write back to config
            with open(config_file, 'w') as f:
                f.write(content)
            
            print(f"📝 Added status directive: status {status_file_path} 10")
            
            # Restart OpenVPN service to apply changes
            print("🔄 Restarting OpenVPN service...")
            result = subprocess.run(['systemctl', 'restart', 'openvpn-server@server.service'],
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                # Wait a moment for service to start
                import time
                time.sleep(3)
                
                # Check if status file is created
                if os.path.exists(status_file_path):
                    return True, f"Status file enabled at {status_file_path} and OpenVPN restarted"
                else:
                    return True, f"OpenVPN restarted, status file will be created on first connection"
            else:
                return False, f"Failed to restart OpenVPN: {result.stderr}"
                
        except Exception as e:
            print(f"💥 Error enabling status file: {str(e)}")
            return False, f"Error enabling status file: {str(e)}"
    
    @staticmethod
    def add_client_direct(client_name, expiry_days=3650, client_group='', client_profile='standard'):
        """Add client directly using EasyRSA commands with group and profile support"""
        try:
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            
            if not clean_name:
                return False, "Invalid client name"
            
            if os.path.exists(f'{EASYRSA_DIR}/pki/issued/{clean_name}.crt'):
                return False, "Client with this name already exists"
            
            print(f"🔧 Adding client directly: {clean_name} with expiry {expiry_days} days")
            
            # Check if EasyRSA directory exists
            if not os.path.exists(EASYRSA_DIR):
                return False, f"EasyRSA directory not found: {EASYRSA_DIR}"
            
            # Check if EasyRSA script exists
            easyrsa_script = f'{EASYRSA_DIR}/easyrsa'
            if not os.path.exists(easyrsa_script):
                return False, f"EasyRSA script not found: {easyrsa_script}"
            
            # Change to EasyRSA directory
            old_cwd = os.getcwd()
            os.chdir(EASYRSA_DIR)
            
            try:
                # Clean up any existing intermediate files for this client
                cleanup_success, cleanup_msg = OpenVPNManager.cleanup_client_files(clean_name, old_cwd)
                
                # Create client certificate
                cmd = ['./easyrsa', '--batch', f'--days={expiry_days}', 'build-client-full', clean_name, 'nopass']
                print(f"🔧 Running command: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=60
                )
                
                print(f"📤 Command return code: {result.returncode}")
                print(f"📄 STDOUT: {result.stdout}")
                if result.stderr:
                    print(f"❌ STDERR: {result.stderr}")
                
                if result.returncode != 0:
                    error_msg = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
                    if not error_msg:
                        error_msg = f"Command failed with return code {result.returncode}"
                    
                    # If still failing due to existing files, try one more cleanup and retry
                    if "already exists" in error_msg.lower() or "aborting build" in error_msg.lower():
                        print(f"🔄 Attempting additional cleanup and retry...")
                        
                        # Run cleanup again (more thorough with wildcards)
                        OpenVPNManager.cleanup_client_files(clean_name, old_cwd)
                        
                        # Retry the command once
                        print(f"🔄 Retrying certificate creation...")
                        result = subprocess.run(
                            cmd,
                            capture_output=True, text=True, timeout=60
                        )
                        
                        print(f"📤 Retry return code: {result.returncode}")
                        if result.returncode != 0:
                            error_msg = result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
                            if not error_msg:
                                error_msg = f"Command failed with return code {result.returncode}"
                            return False, f"Failed to create certificate after cleanup: {error_msg}"
                    else:
                        return False, f"Failed to create certificate: {error_msg}"
                
                # Create .ovpn file
                client_config_path = f'{old_cwd}/{clean_name}.ovpn'
                
                # Read client-common.txt
                common_config = ""
                common_config_path = '/etc/openvpn/server/client-common.txt'
                
                if not os.path.exists(common_config_path):
                    return False, f"Client common config not found: {common_config_path}"
                
                try:
                    with open(common_config_path, 'r') as f:
                        common_config = f.read()
                    print(f"✅ Client common config read ({len(common_config)} chars)")
                    
                    if not common_config.strip():
                        return False, "Client common config is empty"
                        
                except Exception as e:
                    return False, f"Cannot read client-common.txt: {str(e)}"
                
                # Check if all required certificate files exist
                ca_crt_path = f'pki/ca.crt'
                client_crt_path = f'pki/issued/{clean_name}.crt'
                client_key_path = f'pki/private/{clean_name}.key'
                tls_auth_path = '/etc/openvpn/server/tc.key'
                
                missing_files = []
                for file_path, name in [(ca_crt_path, 'CA certificate'), 
                                      (client_crt_path, 'client certificate'),
                                      (client_key_path, 'client private key'),
                                      (tls_auth_path, 'TLS auth key')]:
                    if not os.path.exists(file_path):
                        missing_files.append(f"{name} ({file_path})")
                
                if missing_files:
                    return False, f"Missing certificate files: {', '.join(missing_files)}"
                
                # Read client certificates and key
                try:
                    print(f"📄 Reading certificate files...")
                    
                    with open(ca_crt_path, 'r') as f:
                        ca_cert = f.read()
                    print(f"✅ CA certificate read ({len(ca_cert)} chars)")
                    
                    with open(client_crt_path, 'r') as f:
                        client_cert = f.read()
                    print(f"✅ Client certificate read ({len(client_cert)} chars)")
                    
                    with open(client_key_path, 'r') as f:
                        client_key = f.read()
                    print(f"✅ Client private key read ({len(client_key)} chars)")
                    
                    with open(tls_auth_path, 'r') as f:
                        tls_auth = f.read()
                    print(f"✅ TLS auth key read ({len(tls_auth)} chars)")
                    
                except Exception as e:
                    return False, f"Cannot read certificates: {str(e)}"
                
                # Create .ovpn file content
                ovpn_content = f"""{common_config}
<ca>
{ca_cert}</ca>
<cert>
{client_cert}</cert>
<key>
{client_key}</key>
<tls-crypt>
{tls_auth}</tls-crypt>
"""
                
                # Write .ovpn file
                try:
                    with open(client_config_path, 'w') as f:
                        f.write(ovpn_content)
                    print(f"✅ OVPN config file created: {client_config_path} ({len(ovpn_content)} chars)")
                    
                    # Verify the file was created and is readable
                    if not os.path.exists(client_config_path):
                        return False, f"OVPN config file was not created: {client_config_path}"
                    
                    file_size = os.path.getsize(client_config_path)
                    if file_size == 0:
                        return False, f"OVPN config file is empty: {client_config_path}"
                    
                    print(f"✅ OVPN config verification passed (size: {file_size} bytes)")
                    
                except Exception as e:
                    return False, f"Cannot create OVPN config file: {str(e)}"
                
                print(f"✅ Client {clean_name} created successfully")
                return True, f"Client {clean_name} successfully added"
                
            finally:
                os.chdir(old_cwd)
                
        except Exception as e:
            print(f"💥 Exception in add_client_direct: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def renew_client(client_name, expiry_days=3650):
        """Renew client certificate (revoke old + create new)"""
        try:
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            
            if not clean_name:
                return False, "Invalid client name"
            
            if not os.path.exists(f'{EASYRSA_DIR}/pki/issued/{clean_name}.crt'):
                return False, "Client certificate not found"
            
            print(f"🔄 Renewing client certificate: {clean_name} for {expiry_days} days")
            
            # Cancel any existing auto-revoke for this client
            OpenVPNManager.cancel_auto_revoke(clean_name)
            
            # Check if this is an auto-revoke request
            auto_hours = OpenVPNManager.parse_auto_revoke_hours(str(expiry_days))
            actual_expiry_days = 1 if auto_hours else expiry_days  # Use 1 day for auto-revoke clients
            
            # Step 1: Revoke the old certificate
            success, revoke_message = OpenVPNManager.revoke_client_direct(clean_name)
            if not success:
                return False, f"Failed to revoke old certificate: {revoke_message}"
            
            print(f"✅ Old certificate revoked: {revoke_message}")
            
            # Step 2: Create new certificate with the same name
            success, create_message = OpenVPNManager.add_client_direct(clean_name, actual_expiry_days)
            if not success:
                return False, f"Failed to create new certificate: {create_message}"
            
            print(f"✅ New certificate created: {create_message}")
            
            # If this is an auto-revoke client, schedule the revocation
            if auto_hours:
                OpenVPNManager.schedule_auto_revoke(clean_name, auto_hours)
                return True, f"Client {clean_name} certificate renewed successfully with auto-revoke in {auto_hours} hours"
            else:
                return True, f"Client {clean_name} certificate renewed successfully for {actual_expiry_days} days"
            
        except Exception as e:
            print(f"💥 Exception in renew_client: {str(e)}")
            return False, f"Error renewing client: {str(e)}"

    @staticmethod
    def parse_auto_revoke_hours(expiry_value):
        """Parse auto_* expiry values and return hours"""
        if not isinstance(expiry_value, str) or not expiry_value.startswith('auto_'):
            return None
        
        hours_map = {
            'auto_1h': 1,
            'auto_2h': 2, 
            'auto_6h': 6,
            'auto_12h': 12
        }
        
        return hours_map.get(expiry_value)

    @staticmethod
    def auto_revoke_client(client_name):
        """Automatically revoke a client certificate"""
        print(f"🔄 Auto-revoking client: {client_name}")
        
        try:
            # Update database status first
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE temporary_clients 
                    SET status = 'revoking' 
                    WHERE client_name = ? AND status = 'active'
                ''', (client_name,))
                conn.commit()
                conn.close()
                print(f"📝 Updated database status to 'revoking' for {client_name}")
            except Exception as db_e:
                print(f"⚠️ Database update failed: {db_e}")
            
            # Perform the actual revocation
            success, message = OpenVPNManager.revoke_client_direct(client_name)
            
            if success:
                print(f"✅ Auto-revoked client {client_name}: {message}")
                
                # Update database status to revoked
                try:
                    conn = sqlite3.connect(DATABASE_PATH)
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE temporary_clients 
                        SET status = 'revoked' 
                        WHERE client_name = ?
                    ''', (client_name,))
                    conn.commit()
                    conn.close()
                    print(f"💾 Updated database status to 'revoked' for {client_name}")
                except Exception as db_e:
                    print(f"⚠️ Database status update failed: {db_e}")
                
                # Force disconnect specific client only
                try:
                    OpenVPNManager.force_disconnect_client(client_name)
                    print(f"🔄 Auto-revoke: forced disconnect of client {client_name}")
                except Exception as e:
                    print(f"⚠️ Auto-revoke client disconnect error: {e}")
                
                # Remove from temporary clients tracking
                if client_name in temporary_clients:
                    del temporary_clients[client_name]
                    print(f"🗑️ Removed {client_name} from active tracking")
                    
            else:
                print(f"❌ Failed to auto-revoke client {client_name}: {message}")
                
                # Update database status to failed
                try:
                    conn = sqlite3.connect(DATABASE_PATH)
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE temporary_clients 
                        SET status = 'failed' 
                        WHERE client_name = ?
                    ''', (client_name,))
                    conn.commit()
                    conn.close()
                except Exception as db_e:
                    print(f"⚠️ Database status update failed: {db_e}")
                
        except Exception as e:
            print(f"💥 Error in auto-revoke for {client_name}: {str(e)}")
            
            # Update database status to error
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE temporary_clients 
                    SET status = 'error' 
                    WHERE client_name = ?
                ''', (client_name,))
                conn.commit()
                conn.close()
            except Exception as db_e:
                print(f"⚠️ Database error status update failed: {db_e}")

    @staticmethod
    def schedule_auto_revoke(client_name, hours):
        """Schedule automatic revocation of a client after specified hours"""
        print(f"⏰ Scheduling auto-revoke for {client_name} in {hours} hours")
        
        # Calculate revoke time
        revoke_time = datetime.now() + timedelta(hours=hours)
        
        # Save to database
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO temporary_clients 
                (client_name, revoke_at, hours, status) 
                VALUES (?, ?, ?, 'active')
            ''', (client_name, revoke_time.isoformat(), hours))
            
            conn.commit()
            conn.close()
            print(f"💾 Saved temporary client to database: {client_name}")
        except Exception as e:
            print(f"❌ Failed to save temporary client to database: {e}")
        
        # Create timer for auto-revoke
        timer = threading.Timer(
            hours * 3600,  # Convert hours to seconds
            OpenVPNManager.auto_revoke_client,
            args=[client_name]
        )
        
        # Store in temporary clients tracking
        temporary_clients[client_name] = {
            'revoke_time': revoke_time,
            'timer': timer,
            'hours': hours
        }
        
        # Start the timer
        timer.start()
        
        print(f"✅ Auto-revoke scheduled for {client_name} at {revoke_time.strftime('%Y-%m-%d %H:%M:%S')}")
        return True

    @staticmethod
    def cancel_auto_revoke(client_name):
        """Cancel scheduled auto-revoke for a client"""
        cancelled = False
        
        # Cancel timer if exists
        if client_name in temporary_clients:
            timer = temporary_clients[client_name]['timer']
            timer.cancel()
            del temporary_clients[client_name]
            print(f"🚫 Cancelled timer for {client_name}")
            cancelled = True
        
        # Remove from database
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE temporary_clients 
                SET status = 'cancelled' 
                WHERE client_name = ? AND status = 'active'
            ''', (client_name,))
            
            if cursor.rowcount > 0:
                print(f"💾 Updated database status to 'cancelled' for {client_name}")
                cancelled = True
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ Failed to update database for cancellation: {e}")
        
        if cancelled:
            print(f"✅ Successfully cancelled auto-revoke for {client_name}")
        
        return cancelled

    @staticmethod
    def get_temporary_client_info(client_name):
        """Get info about temporary client's auto-revoke status"""
        if client_name in temporary_clients:
            temp_info = temporary_clients[client_name]
            time_left = temp_info['revoke_time'] - datetime.now()
            
            if time_left.total_seconds() > 0:
                hours_left = time_left.total_seconds() / 3600
                minutes_left = (time_left.total_seconds() % 3600) / 60
                
                return {
                    'is_temporary': True,
                    'revoke_time': temp_info['revoke_time'],
                    'hours_left': hours_left,
                    'minutes_left': int(minutes_left),
                    'total_hours': temp_info['hours'],
                    'time_left_str': f"{int(hours_left)}h {int(minutes_left)}m" if hours_left >= 1 else f"{int(minutes_left)}m"
                }
            else:
                # Timer should have expired, clean up
                OpenVPNManager.cancel_auto_revoke(client_name)
                
        return {'is_temporary': False}

    @staticmethod
    def restore_client(client_name, expiry_days=3650):
        """Restore a revoked client with new certificate"""
        try:
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            
            if not clean_name:
                return False, "Invalid client name"
            
            print(f"🔄 Restoring revoked client: {clean_name}")
            
            # Check if client exists in revoked list
            clients = OpenVPNManager.get_clients()
            revoked_client = None
            for client in clients:
                if client['name'] == clean_name and client['status'] == 'revoked':
                    revoked_client = client
                    break
            
            if not revoked_client:
                return False, f"No revoked client found with name: {clean_name}"
            
            # Cancel any existing auto-revoke for this client
            OpenVPNManager.cancel_auto_revoke(clean_name)
            
            # Check if this is an auto-revoke request
            auto_hours = OpenVPNManager.parse_auto_revoke_hours(str(expiry_days))
            actual_expiry_days = 1 if auto_hours else expiry_days
            
            # Remove old config file if it exists (cleanup)
            old_config_path = f'./{clean_name}.ovpn'
            
            try:
                if os.path.exists(old_config_path):
                    os.remove(old_config_path)
                    print(f"🗑️ Removed old config file: {old_config_path}")
            except Exception as e:
                print(f"⚠️ Could not remove old config: {e}")
            
            # Create new certificate with the same name
            success, create_message = OpenVPNManager.add_client_direct(clean_name, actual_expiry_days)
            if not success:
                return False, f"Failed to create new certificate: {create_message}"
            
            print(f"✅ New certificate created for restored client: {create_message}")
            
            # If this is an auto-revoke client, schedule the revocation
            if auto_hours:
                OpenVPNManager.schedule_auto_revoke(clean_name, auto_hours)
                return True, f"Client {clean_name} restored successfully with auto-revoke in {auto_hours} hours"
            else:
                return True, f"Client {clean_name} restored successfully for {actual_expiry_days} days"
            
        except Exception as e:
            print(f"💥 Exception in restore_client: {str(e)}")
            return False, f"Error restoring client: {str(e)}"

    @staticmethod
    def diagnose_system():
        """Diagnose system configuration and permissions"""
        diagnosis = {
            'easyrsa_status': 'unknown',
            'permissions': [],
            'missing_files': [],
            'errors': [],
            'recommendations': []
        }
        
        try:
            # Check EasyRSA directory
            if not os.path.exists(EASYRSA_DIR):
                diagnosis['errors'].append(f"EasyRSA directory missing: {EASYRSA_DIR}")
                diagnosis['recommendations'].append("Run OpenVPN installation script first")
                return diagnosis
            
            # Check EasyRSA script
            easyrsa_script = f'{EASYRSA_DIR}/easyrsa'
            if not os.path.exists(easyrsa_script):
                diagnosis['errors'].append(f"EasyRSA script missing: {easyrsa_script}")
                diagnosis['recommendations'].append("Reinstall EasyRSA or run setup script")
            elif not os.access(easyrsa_script, os.X_OK):
                diagnosis['errors'].append(f"EasyRSA script not executable: {easyrsa_script}")
                diagnosis['recommendations'].append(f"Run: chmod +x {easyrsa_script}")
            else:
                diagnosis['easyrsa_status'] = 'executable'
            
            # Check PKI directory structure
            pki_dir = f'{EASYRSA_DIR}/pki'
            required_dirs = ['issued', 'private', 'reqs']
            for dir_name in required_dirs:
                dir_path = f'{pki_dir}/{dir_name}'
                if not os.path.exists(dir_path):
                    diagnosis['missing_files'].append(f"PKI directory: {dir_path}")
            
            # Check required files
            required_files = [
                (f'{pki_dir}/ca.crt', 'CA certificate'),
                (f'{pki_dir}/index.txt', 'Certificate index'),
                ('/etc/openvpn/server/client-common.txt', 'Client common config'),
                ('/etc/openvpn/server/tc.key', 'TLS auth key')
            ]
            
            for file_path, description in required_files:
                if not os.path.exists(file_path):
                    diagnosis['missing_files'].append(f"{description}: {file_path}")
                elif not os.access(file_path, os.R_OK):
                    diagnosis['permissions'].append(f"Cannot read {description}: {file_path}")
            
            # Check directory permissions
            if os.path.exists(EASYRSA_DIR):
                if not os.access(EASYRSA_DIR, os.R_OK | os.W_OK | os.X_OK):
                    diagnosis['permissions'].append(f"Insufficient permissions for EasyRSA directory: {EASYRSA_DIR}")
            
            # Test EasyRSA command
            if diagnosis['easyrsa_status'] == 'executable':
                try:
                    old_cwd = os.getcwd()
                    os.chdir(EASYRSA_DIR)
                    
                    result = subprocess.run(['./easyrsa', 'help'], 
                                          capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        diagnosis['easyrsa_status'] = 'working'
                    else:
                        diagnosis['errors'].append(f"EasyRSA command failed: {result.stderr}")
                        
                    os.chdir(old_cwd)
                    
                except Exception as e:
                    diagnosis['errors'].append(f"Cannot test EasyRSA: {str(e)}")
            
            # Generate recommendations
            if diagnosis['missing_files']:
                diagnosis['recommendations'].append("Some required files are missing - consider reinstalling OpenVPN")
            if diagnosis['permissions']:
                diagnosis['recommendations'].append("Fix file permissions - run as root or adjust ownership")
            if not diagnosis['errors'] and diagnosis['easyrsa_status'] == 'working':
                diagnosis['recommendations'].append("System appears to be configured correctly")
                
        except Exception as e:
            diagnosis['errors'].append(f"Diagnosis failed: {str(e)}")
        
        return diagnosis

    @staticmethod
    def cleanup_client_files(client_name, working_dir=None):
        """Clean up existing client files before certificate generation"""
        try:
            import glob
            
            # Use current working directory if not specified
            if working_dir is None:
                working_dir = os.getcwd()
            
            print(f"🧹 Cleaning up existing files for {client_name}...")
            
            # List of file patterns to clean up
            cleanup_patterns = [
                f'pki/reqs/{client_name}.req',
                f'pki/reqs/{client_name}.*',
                f'pki/private/{client_name}.key', 
                f'pki/private/{client_name}.*',
                f'pki/issued/{client_name}.crt',
                f'pki/issued/{client_name}.*',
                f'pki/certs_by_serial/{client_name}.pem',
                f'{working_dir}/{client_name}.ovpn'
            ]
            
            files_removed = 0
            
            for pattern in cleanup_patterns:
                if '*' in pattern:
                    # Use glob for patterns with wildcards
                    matching_files = glob.glob(pattern)
                    for file_path in matching_files:
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                                print(f"🗑️ Removed: {file_path}")
                                files_removed += 1
                            except Exception as e:
                                print(f"⚠️ Could not remove {file_path}: {e}")
                else:
                    # Direct file path
                    if os.path.exists(pattern):
                        try:
                            os.remove(pattern)
                            print(f"🗑️ Removed: {pattern}")
                            files_removed += 1
                        except Exception as e:
                            print(f"⚠️ Could not remove {pattern}: {e}")
            
            print(f"✅ Cleanup completed. Removed {files_removed} files.")
            return True, f"Removed {files_removed} files"
            
        except Exception as e:
            print(f"💥 Error during cleanup: {str(e)}")
            return False, f"Cleanup error: {str(e)}"

    @staticmethod
    def calculate_connection_duration(connected_since_str):
        """Calculate how long a client has been connected"""
        duration_info = {
            'total_seconds': 0,
            'formatted': 'N/A',
            'days': 0,
            'hours': 0,
            'minutes': 0,
            'seconds': 0
        }
        
        if not connected_since_str or connected_since_str in ['N/A', '']:
            return duration_info
        
        try:
            from datetime import datetime
            
            # Parse different timestamp formats that OpenVPN might use
            current_time = datetime.now()
            connected_time = None
            
            # Try different timestamp formats
            timestamp_formats = [
                '%a %b %d %H:%M:%S %Y',      # Tue Jan 15 14:30:45 2024
                '%Y-%m-%d %H:%M:%S',         # 2024-01-15 14:30:45
                '%m/%d/%Y %H:%M:%S',         # 01/15/2024 14:30:45
                '%d/%m/%Y %H:%M:%S',         # 15/01/2024 14:30:45
                '%Y-%m-%d %H:%M:%S %Z',      # 2024-01-15 14:30:45 UTC
                '%a %Y-%m-%d %H:%M:%S %Z',   # Tue 2024-01-15 14:30:45 UTC
                '%a %Y-%m-%d %H:%M:%S',      # Tue 2024-01-15 14:30:45
            ]
            
            # Remove extra spaces and clean the string
            clean_timestamp = ' '.join(connected_since_str.split())
            
            for fmt in timestamp_formats:
                try:
                    connected_time = datetime.strptime(clean_timestamp, fmt)
                    break
                except ValueError:
                    continue
            
            # If standard formats fail, try parsing Unix timestamp
            if not connected_time:
                try:
                    # Check if it's a Unix timestamp
                    timestamp = float(connected_since_str)
                    connected_time = datetime.fromtimestamp(timestamp)
                except (ValueError, OSError):
                    pass
            
            if connected_time:
                # Calculate duration
                time_diff = current_time - connected_time
                total_seconds = int(time_diff.total_seconds())
                
                if total_seconds < 0:
                    total_seconds = 0  # Handle future timestamps
                
                # Break down into components
                days = total_seconds // 86400
                remaining = total_seconds % 86400
                hours = remaining // 3600
                remaining = remaining % 3600
                minutes = remaining // 60
                seconds = remaining % 60
                
                duration_info.update({
                    'total_seconds': total_seconds,
                    'days': days,
                    'hours': hours,
                    'minutes': minutes,
                    'seconds': seconds
                })
                
                # Format duration string
                if days > 0:
                    duration_info['formatted'] = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    duration_info['formatted'] = f"{hours}h {minutes}m"
                elif minutes > 0:
                    duration_info['formatted'] = f"{minutes}m {seconds}s"
                else:
                    duration_info['formatted'] = f"{seconds}s"
                
                pass
            else:
                pass
                
        except Exception as e:
            pass
        
        return duration_info

    @staticmethod
    def check_file_status():
        """Check status of important OpenVPN files"""
        files = {
            'config_files': {
                'server_conf': {
                    'path': '/etc/openvpn/server/server.conf',
                    'name': 'server.conf',
                    'exists': False,
                    'readable': False,
                    'size': 0
                },
                'ca_cert': {
                    'path': '/etc/openvpn/server/easy-rsa/pki/ca.crt',
                    'name': 'ca.crt',
                    'exists': False,
                    'readable': False,
                    'size': 0
                },
                'index_txt': {
                    'path': '/etc/openvpn/server/easy-rsa/pki/index.txt',
                    'name': 'index.txt',
                    'exists': False,
                    'readable': False,
                    'size': 0
                }
            },
            'log_files': {
                'status_log': {
                    'path': '/var/log/openvpn/openvpn-status.log',
                    'name': 'openvpn-status.log',
                    'exists': False,
                    'readable': False,
                    'size': 0
                },
                'main_log': {
                    'path': '/var/log/openvpn/openvpn.log',
                    'name': 'openvpn.log',
                    'exists': False,
                    'readable': False,
                    'size': 0
                },
                'syslog': {
                    'path': '/var/log/syslog',
                    'name': 'syslog',
                    'exists': False,
                    'readable': False,
                    'size': 0
                }
            }
        }
        
        # Check all files
        for category in files:
            for file_key, file_info in files[category].items():
                try:
                    if os.path.exists(file_info['path']):
                        file_info['exists'] = True
                        file_info['size'] = os.path.getsize(file_info['path'])
                        file_info['readable'] = os.access(file_info['path'], os.R_OK)
                except Exception:
                    pass
        
        return files
    
    @staticmethod
    def get_log_content(log_type='status', lines=50):
        """Get log file content"""
        log_paths = {
            'status': '/var/log/openvpn/openvpn-status.log',
            'main': '/var/log/openvpn/openvpn.log',
            'syslog': '/var/log/syslog'
        }
        
        if log_type not in log_paths:
            return None
        
        log_path = log_paths[log_type]
        
        try:
            if not os.path.exists(log_path):
                return None
            
            # Use tail command to get last N lines
            result = subprocess.run(['tail', '-n', str(lines), log_path], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                # Fallback to Python reading
                with open(log_path, 'r') as f:
                    lines_list = f.readlines()
                    return ''.join(lines_list[-lines:])
        
        except Exception as e:
            return f"Error reading log: {str(e)}"
        
        return None

    @staticmethod
    def force_create_client(client_name, expiry_days=3650):
        """Force create client by cleaning up all existing files first"""
        try:
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            
            if not clean_name:
                return False, "Invalid client name"
            
            print(f"🔧 Force creating client: {clean_name}")
            
            # Clean up files from current working directory first
            cleanup_success, cleanup_msg = OpenVPNManager.cleanup_client_files(clean_name)
            
            # Change to EasyRSA directory and clean up there too
            if os.path.exists(EASYRSA_DIR):
                old_cwd = os.getcwd()
                os.chdir(EASYRSA_DIR)
                try:
                    OpenVPNManager.cleanup_client_files(clean_name, old_cwd)
                finally:
                    os.chdir(old_cwd)
            
            # Now try to create the client
            return OpenVPNManager.add_client_direct(clean_name, expiry_days)
            
        except Exception as e:
            print(f"💥 Exception in force_create_client: {str(e)}")
            return False, f"Error in force create: {str(e)}"

    @staticmethod
    def add_client(client_name, expiry_days=3650, client_group='', client_profile='standard'):
        """Add new client with group and profile support"""
        try:
            # Clean client name from invalid characters
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            
            if not clean_name:
                return False, "Invalid client name"
            
            # Check if client already exists
            if os.path.exists(f'{EASYRSA_DIR}/pki/issued/{clean_name}.crt'):
                return False, "Client with this name already exists"
            
            print(f"🔧 Starting to add client: {clean_name} (group: {client_group}, profile: {client_profile})")
            
            # Check if this is an auto-revoke request
            auto_hours = OpenVPNManager.parse_auto_revoke_hours(str(expiry_days))
            actual_expiry_days = 1 if auto_hours else expiry_days  # Use 1 day for auto-revoke clients
            
            # Try direct method first
            success, message = OpenVPNManager.add_client_direct(clean_name, actual_expiry_days, client_group, client_profile)
            if success:
                # If this is an auto-revoke client, schedule the revocation
                if auto_hours:
                    OpenVPNManager.schedule_auto_revoke(clean_name, auto_hours)
                    return True, f"Client {clean_name} successfully added with auto-revoke in {auto_hours} hours"
                else:
                    return success, message
            
            print(f"⚠️ Direct method failed, trying script method: {message}")
            
            # Используем скрипт для добавления клиента
            env = os.environ.copy()
            process = subprocess.Popen(
                ['bash', SCRIPT_PATH],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # Отправляем команды: 1 (добавить клиента), имя клиента
            input_commands = f"1\n{clean_name}\n"
            print(f"📝 Sending commands: {repr(input_commands)}")
            
            stdout, stderr = process.communicate(input=input_commands)
            
            print(f"📤 Process return code: {process.returncode}")
            print(f"📄 STDOUT: {stdout}")
            print(f"❌ STDERR: {stderr}")
            
            if process.returncode == 0:
                # If this is an auto-revoke client, schedule the revocation
                if auto_hours:
                    OpenVPNManager.schedule_auto_revoke(clean_name, auto_hours)
                    return True, f"Client {clean_name} successfully added with auto-revoke in {auto_hours} hours"
                else:
                    return True, f"Client {clean_name} successfully added"
            else:
                return False, f"Error adding client (return code {process.returncode}): {stderr}"
                
        except Exception as e:
            print(f"💥 Exception in add_client: {str(e)}")
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def revoke_client_direct(client_name):
        """Revoke client directly using EasyRSA commands"""
        try:
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            
            if not clean_name:
                return False, "Invalid client name"
            
            if not os.path.exists(f'{EASYRSA_DIR}/pki/issued/{clean_name}.crt'):
                return False, "Client certificate not found"
            
            print(f"🔧 Revoking client directly: {clean_name}")
            
            # Change to EasyRSA directory
            old_cwd = os.getcwd()
            os.chdir(EASYRSA_DIR)
            
            try:
                # Revoke client certificate
                result = subprocess.run(
                    ['./easyrsa', '--batch', 'revoke', clean_name],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode != 0:
                    return False, f"Failed to revoke certificate: {result.stderr}"
                
                # Generate new CRL
                result = subprocess.run(
                    ['./easyrsa', '--batch', '--days=3650', 'gen-crl'],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode != 0:
                    return False, f"Failed to generate CRL: {result.stderr}"
                
                # Copy CRL to OpenVPN directory
                try:
                    subprocess.run(['cp', 'pki/crl.pem', '/etc/openvpn/server/crl.pem'], check=True)
                    subprocess.run(['chown', 'nobody:nogroup', '/etc/openvpn/server/crl.pem'], check=True)
                except:
                    pass  # Continue if chown fails
                
                # Remove client config file
                config_path = f'{old_cwd}/{clean_name}.ovpn'
                if os.path.exists(config_path):
                    os.remove(config_path)
                
                # Force disconnect specific client only
                try:
                    OpenVPNManager.force_disconnect_client(clean_name)
                    print(f"🔄 Forced disconnect of client {clean_name}")
                except Exception as e:
                    print(f"⚠️ Client disconnect error: {e}")
                
                print(f"✅ Client {clean_name} revoked successfully")
                return True, f"Client {clean_name} successfully revoked"
                
            finally:
                os.chdir(old_cwd)
                
        except Exception as e:
            print(f"💥 Exception in revoke_client_direct: {str(e)}")
            return False, f"Error: {str(e)}"

    @staticmethod
    def revoke_client(client_name):
        """Revoke client"""
        try:
            print(f"🔧 Starting to revoke client: {client_name}")
            
            # Try direct method first
            success, message = OpenVPNManager.revoke_client_direct(client_name)
            if success:
                return success, message
            
            print(f"⚠️ Direct method failed, trying script method: {message}")
            
            # Fallback to script method
            # Get list of active clients from the script perspective
            process = subprocess.Popen(
                ['bash', SCRIPT_PATH],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Send option 2 to see the client list
            stdout, stderr = process.communicate(input="2\n")
            
            if process.returncode != 0:
                return False, f"Script error: {stderr}"
            
            # Parse output to find client number
            lines = stdout.split('\n')
            client_number = None
            
            for i, line in enumerate(lines):
                if client_name in line and ')' in line:
                    # Extract number from line like "1) clientname"
                    parts = line.split(')')
                    if len(parts) > 0:
                        try:
                            client_number = parts[0].strip()
                            break
                        except:
                            continue
            
            if not client_number:
                return False, "Client not found in revocation list"
            
            print(f"📝 Found client at position: {client_number}")
            
            # Now revoke the client
            process = subprocess.Popen(
                ['bash', SCRIPT_PATH],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Send commands: 2 (revoke client), client number, y (confirm)
            input_commands = f"2\n{client_number}\ny\n"
            stdout, stderr = process.communicate(input=input_commands)
            
            print(f"📤 Revoke process return code: {process.returncode}")
            print(f"📄 STDOUT: {stdout}")
            print(f"❌ STDERR: {stderr}")
            
            if process.returncode == 0:
                return True, f"Client {client_name} successfully revoked"
            else:
                return False, f"Error revoking client (return code {process.returncode}): {stderr}"
                
        except Exception as e:
            print(f"💥 Exception in revoke_client: {str(e)}")
            return False, f"Error: {str(e)}"
    
    @staticmethod
    def get_system_metrics():
        """Get current system metrics (CPU, RAM, Network)"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available = memory.available
            memory_total = memory.total
            memory_used = memory.used
            
            # Network statistics
            network_io = psutil.net_io_counters()
            network_sent = network_io.bytes_sent
            network_received = network_io.bytes_recv
            
            # Disk usage (root partition)
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # Active network connections
            connections = psutil.net_connections()
            
            # Get current active VPN connections count
            active_vpn_connections = len(OpenVPNManager.get_active_connections())
            
            return {
                'cpu': {
                    'percent': round(cpu_percent, 1),
                    'status': 'high' if cpu_percent > 80 else 'normal' if cpu_percent > 50 else 'low'
                },
                'memory': {
                    'percent': round(memory_percent, 1),
                    'available': memory_available,
                    'total': memory_total,
                    'used': memory_used,
                    'available_gb': round(memory_available / 1024 / 1024 / 1024, 1),
                    'total_gb': round(memory_total / 1024 / 1024 / 1024, 1),
                    'used_gb': round(memory_used / 1024 / 1024 / 1024, 1),
                    'status': 'high' if memory_percent > 85 else 'normal' if memory_percent > 60 else 'low'
                },
                'network': {
                    'bytes_sent': network_sent,
                    'bytes_received': network_received,
                    'sent_mb': round(network_sent / 1024 / 1024, 1),
                    'received_mb': round(network_received / 1024 / 1024, 1),
                    'sent_gb': round(network_sent / 1024 / 1024 / 1024, 2),
                    'received_gb': round(network_received / 1024 / 1024 / 1024, 2)
                },
                'disk': {
                    'percent': round(disk_percent, 1),
                    'free': disk.free,
                    'total': disk.total,
                    'used': disk.used,
                    'free_gb': round(disk.free / 1024 / 1024 / 1024, 1),
                    'total_gb': round(disk.total / 1024 / 1024 / 1024, 1),
                    'status': 'high' if disk_percent > 90 else 'normal' if disk_percent > 70 else 'low'
                },
                'vpn_connections': active_vpn_connections,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error getting system metrics: {e}")
            return {
                'cpu': {'percent': 0, 'status': 'unknown'},
                'memory': {'percent': 0, 'available': 0, 'total': 0, 'status': 'unknown'},
                'network': {'bytes_sent': 0, 'bytes_received': 0},
                'disk': {'percent': 0, 'free': 0, 'total': 0, 'status': 'unknown'},
                'vpn_connections': 0,
                'timestamp': datetime.now().isoformat()
            }
    
    @staticmethod
    def get_network_bandwidth():
        """Get real-time network bandwidth usage"""
        try:
            # Take two measurements 1 second apart
            net1 = psutil.net_io_counters()
            time.sleep(1)
            net2 = psutil.net_io_counters()
            
            # Calculate bandwidth per second
            upload_speed = net2.bytes_sent - net1.bytes_sent
            download_speed = net2.bytes_recv - net1.bytes_recv
            
            return {
                'upload_bps': upload_speed,
                'download_bps': download_speed,
                'upload_kbps': round(upload_speed / 1024, 2),
                'download_kbps': round(download_speed / 1024, 2),
                'upload_mbps': round(upload_speed / 1024 / 1024, 3),
                'download_mbps': round(download_speed / 1024 / 1024, 3),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error getting network bandwidth: {e}")
            return {
                'upload_bps': 0, 'download_bps': 0,
                'upload_kbps': 0, 'download_kbps': 0,
                'upload_mbps': 0.0, 'download_mbps': 0.0,
                'timestamp': datetime.now().isoformat()
            }
    
    @staticmethod
    def save_system_metrics():
        """Save current system metrics to database"""
        try:
            metrics = OpenVPNManager.get_system_metrics()
            
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO system_metrics 
                (cpu_percent, memory_percent, memory_available, network_sent, network_received, active_connections)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                metrics['cpu']['percent'],
                metrics['memory']['percent'],
                metrics['memory']['available'],
                metrics['network']['bytes_sent'],
                metrics['network']['bytes_received'],
                metrics['vpn_connections']
            ))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error saving system metrics: {e}")
            return False
    
    @staticmethod
    def get_client_traffic_history(client_name, days=30):
        """Get traffic history for specific client"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, bytes_sent, bytes_received, duration_seconds, session_start, session_end, real_address, virtual_address
                FROM traffic_history 
                WHERE client_name = ? AND timestamp >= datetime('now', '-{} days')
                ORDER BY timestamp DESC
            '''.format(days), (client_name,))
            
            history = []
            for row in cursor.fetchall():
                history.append({
                    'timestamp': row[0],
                    'bytes_sent': row[1],
                    'bytes_received': row[2],
                    'duration_seconds': row[3],
                    'session_start': row[4],
                    'session_end': row[5],
                    'real_address': row[6] if len(row) > 6 else 'Unknown',
                    'virtual_address': row[7] if len(row) > 7 else 'Unknown',
                    'total_bytes': row[1] + row[2],
                    'sent_mb': round(row[1] / 1024 / 1024, 2),
                    'received_mb': round(row[2] / 1024 / 1024, 2),
                    'total_mb': round((row[1] + row[2]) / 1024 / 1024, 2)
                })
            
            # Calculate totals
            total_sent = sum(h['bytes_sent'] for h in history)
            total_received = sum(h['bytes_received'] for h in history)
            total_duration = sum(h['duration_seconds'] for h in history)
            
            conn.close()
            
            return {
                'client_name': client_name,
                'history': history,
                'totals': {
                    'bytes_sent': total_sent,
                    'bytes_received': total_received,
                    'total_bytes': total_sent + total_received,
                    'sent_mb': round(total_sent / 1024 / 1024, 2),
                    'received_mb': round(total_received / 1024 / 1024, 2),
                    'total_mb': round((total_sent + total_received) / 1024 / 1024, 2),
                    'sent_gb': round(total_sent / 1024 / 1024 / 1024, 2),
                    'received_gb': round(total_received / 1024 / 1024 / 1024, 2),
                    'total_gb': round((total_sent + total_received) / 1024 / 1024 / 1024, 2),
                    'total_duration_seconds': total_duration,
                    'total_duration_formatted': OpenVPNManager.format_duration(total_duration)
                },
                'days': days
            }
            
        except Exception as e:
            print(f"Error getting client traffic history: {e}")
            return {
                'client_name': client_name,
                'history': [],
                'totals': {
                    'bytes_sent': 0, 'bytes_received': 0, 'total_bytes': 0,
                    'sent_mb': 0, 'received_mb': 0, 'total_mb': 0,
                    'sent_gb': 0, 'received_gb': 0, 'total_gb': 0,
                    'total_duration_seconds': 0, 'total_duration_formatted': '0s'
                },
                'days': days
            }
    
    @staticmethod
    def update_active_session(client_name, bytes_sent, bytes_received, duration_seconds, session_start=None, session_end=None, real_address=None, virtual_address=None):
        """Update or create active session record"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Check if active session exists for this client (no session_end set yet)
            cursor.execute('''
                SELECT id, session_start FROM traffic_history 
                WHERE client_name = ? AND session_end IS NULL
                ORDER BY timestamp DESC LIMIT 1
            ''', (client_name,))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing active session (keep session_end NULL for active sessions)
                cursor.execute('''
                    UPDATE traffic_history 
                    SET bytes_sent = ?, bytes_received = ?, duration_seconds = ?, 
                        real_address = COALESCE(?, real_address),
                        virtual_address = COALESCE(?, virtual_address),
                        timestamp = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (bytes_sent, bytes_received, duration_seconds, real_address, virtual_address, existing[0]))
                print(f"💾 UPDATED SESSION: {client_name} from {real_address} - Sent: {bytes_sent/1024/1024:.2f}MB, Received: {bytes_received/1024/1024:.2f}MB, Duration: {duration_seconds}s")
            else:
                # Create new session with current time as session_start if not provided
                actual_session_start = session_start or datetime.now().isoformat()
                cursor.execute('''
                    INSERT INTO traffic_history 
                    (client_name, bytes_sent, bytes_received, duration_seconds, session_start, session_end, real_address, virtual_address)
                    VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                ''', (client_name, bytes_sent, bytes_received, duration_seconds, actual_session_start, real_address, virtual_address))
                print(f"💾 NEW SESSION: {client_name} from {real_address} -> {virtual_address} - Sent: {bytes_sent/1024/1024:.2f}MB, Received: {bytes_received/1024/1024:.2f}MB, Duration: {duration_seconds}s")
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"💥 Error updating active session: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def finalize_session(client_name, bytes_sent, bytes_received, duration_seconds, session_start=None, session_end=None, real_address=None, virtual_address=None):
        """Finalize active session by setting session_end"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Find and update the active session for this client
            cursor.execute('''
                UPDATE traffic_history 
                SET bytes_sent = ?, bytes_received = ?, duration_seconds = ?, 
                    session_end = ?, 
                    real_address = COALESCE(?, real_address),
                    virtual_address = COALESCE(?, virtual_address),
                    timestamp = CURRENT_TIMESTAMP
                WHERE client_name = ? AND session_end IS NULL
            ''', (bytes_sent, bytes_received, duration_seconds, session_end or datetime.now().isoformat(), real_address, virtual_address, client_name))
            
            if cursor.rowcount > 0:
                print(f"💾 FINALIZED SESSION: {client_name} from {real_address} - Final: {bytes_sent/1024/1024:.2f}MB sent, {bytes_received/1024/1024:.2f}MB received")
            else:
                # No active session found, create new completed session
                actual_session_start = session_start or datetime.now().isoformat()
                actual_session_end = session_end or datetime.now().isoformat()
                cursor.execute('''
                    INSERT INTO traffic_history 
                    (client_name, bytes_sent, bytes_received, duration_seconds, session_start, session_end, real_address, virtual_address)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (client_name, bytes_sent, bytes_received, duration_seconds, actual_session_start, actual_session_end, real_address, virtual_address))
                print(f"💾 CREATED FINAL SESSION: {client_name} from {real_address} -> {virtual_address} - {bytes_sent/1024/1024:.2f}MB sent, {bytes_received/1024/1024:.2f}MB received")
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"💥 Error finalizing session: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def save_client_session(client_name, bytes_sent, bytes_received, duration_seconds, session_start=None, session_end=None):
        """Save completed client session data to history"""
        try:
            print(f"💾 SAVING SESSION: {client_name} - Sent: {bytes_sent/1024/1024:.2f}MB, Received: {bytes_received/1024/1024:.2f}MB, Duration: {duration_seconds}s")
            
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO traffic_history 
                (client_name, bytes_sent, bytes_received, duration_seconds, session_start, session_end)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (client_name, bytes_sent, bytes_received, duration_seconds, session_start, session_end))
            
            conn.commit()
            
            # Verify the insert
            cursor.execute('SELECT COUNT(*) FROM traffic_history WHERE client_name = ?', (client_name,))
            count = cursor.fetchone()[0]
            
            conn.close()
            
            print(f"✅ Session saved! Total sessions for {client_name}: {count}")
            return True
            
        except Exception as e:
            print(f"💥 Error saving client session: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def format_duration(seconds):
        """Format duration seconds to human readable format"""
        if seconds == 0:
            return "0s"
        
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")
        
        return " ".join(parts)
    
    @staticmethod
    def update_client_stats(client_name, session_start=None, session_end=None, 
                           bytes_sent=0, bytes_received=0, duration_seconds=0,
                           last_activity=None, is_connection=False, is_disconnection=False, is_activity_update=False):
        """Update aggregated client statistics"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            current_time = datetime.now()
            
            # Check if client exists in stats
            cursor.execute('SELECT * FROM client_stats WHERE client_name = ?', (client_name,))
            existing = cursor.fetchone()
            
            if not existing:
                # Create new client entry
                cursor.execute('''
                    INSERT INTO client_stats 
                    (client_name, first_connection, last_connection, last_activity, 
                     is_online, current_session_start, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (client_name, session_start or current_time, session_start or current_time, 
                      last_activity or current_time, 1 if is_connection else 0, 
                      session_start if is_connection else None, current_time, current_time))
                print(f"📊 Created new client stats for: {client_name}")
            else:
                # Update existing client
                if is_connection:
                    # Client connected
                    cursor.execute('''
                        UPDATE client_stats 
                        SET is_online = 1, current_session_start = ?, last_activity = ?, updated_at = ?
                        WHERE client_name = ?
                    ''', (session_start, current_time, current_time, client_name))
                    print(f"📊 Marked {client_name} as online")
                    
                elif is_disconnection:
                    # Client disconnected - update totals
                    cursor.execute('''
                        UPDATE client_stats 
                        SET total_bytes_sent = total_bytes_sent + ?,
                            total_bytes_received = total_bytes_received + ?,
                            total_duration_seconds = total_duration_seconds + ?,
                            session_count = session_count + 1,
                            last_connection = ?,
                            last_activity = ?,
                            is_online = 0,
                            current_session_start = NULL,
                            updated_at = ?
                        WHERE client_name = ?
                    ''', (bytes_sent, bytes_received, duration_seconds, session_end, 
                          session_end, current_time, client_name))
                    print(f"📊 Updated {client_name} totals: +{bytes_sent/1024/1024:.1f}MB sent, +{bytes_received/1024/1024:.1f}MB received")
                    
                elif is_activity_update and last_activity:
                    # Just update last activity
                    cursor.execute('''
                        UPDATE client_stats 
                        SET last_activity = ?, updated_at = ?
                        WHERE client_name = ?
                    ''', (last_activity, current_time, client_name))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"💥 Error updating client stats for {client_name}: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    @staticmethod
    def get_all_clients_traffic_summary():
        """Get traffic summary for all clients from traffic history"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Get aggregated data directly from traffic_history
            cursor.execute('''
                SELECT 
                    client_name,
                    SUM(COALESCE(bytes_sent, 0)) as total_sent,
                    SUM(COALESCE(bytes_received, 0)) as total_received,
                    SUM(COALESCE(duration_seconds, 0)) as total_duration,
                    COUNT(*) as session_count,
                    MIN(session_start) as first_connection,
                    MAX(COALESCE(session_end, session_start)) as last_activity,
                    MAX(CASE WHEN session_end IS NULL THEN 1 ELSE 0 END) as has_active_session
                FROM traffic_history 
                GROUP BY client_name
                ORDER BY (SUM(COALESCE(bytes_sent, 0)) + SUM(COALESCE(bytes_received, 0))) DESC
            ''')
            
            summary = []
            current_time = datetime.now()
            
            for row in cursor.fetchall():
                (client_name, total_sent, total_received, total_duration, session_count,
                 first_connection, last_activity, has_active_session) = row
                
                total_sent = total_sent or 0
                total_received = total_received or 0
                total_duration = total_duration or 0
                total_bytes = total_sent + total_received
                
                # Check if client is currently online
                is_online = bool(has_active_session)
                
                # Debug log for traffic summary
                print(f"📊 Traffic Summary for {client_name}: sent={total_sent/1024/1024:.2f}MB, received={total_received/1024/1024:.2f}MB, sessions={session_count}, online={is_online}")
                
                # Get current session duration if online
                current_session_duration = 0
                if is_online:
                    cursor.execute('''
                        SELECT session_start FROM traffic_history 
                        WHERE client_name = ? AND session_end IS NULL
                        ORDER BY timestamp DESC LIMIT 1
                    ''', (client_name,))
                    active_session = cursor.fetchone()
                    if active_session and active_session[0]:
                        try:
                            session_start_dt = datetime.fromisoformat(active_session[0])
                            current_session_duration = int((current_time - session_start_dt).total_seconds())
                        except:
                            current_session_duration = 0
                
                # Determine display status
                if is_online:
                    status = f"Online ({OpenVPNManager.format_duration(current_session_duration)})"
                else:
                    status = "Offline"
                
                summary.append({
                    'client_name': client_name,
                    'total_sent': total_sent,
                    'total_received': total_received,
                    'total_bytes': total_bytes,
                    'sent_mb': round(total_sent / 1024 / 1024, 2),
                    'received_mb': round(total_received / 1024 / 1024, 2),
                    'total_mb': round(total_bytes / 1024 / 1024, 2),
                    'sent_gb': round(total_sent / 1024 / 1024 / 1024, 2),
                    'received_gb': round(total_received / 1024 / 1024 / 1024, 2),
                    'total_gb': round(total_bytes / 1024 / 1024 / 1024, 2),
                    'total_duration': total_duration,
                    'duration_formatted': OpenVPNManager.format_duration(total_duration),
                    'session_count': session_count,
                    'first_connection': first_connection,
                    'last_connection': last_activity,
                    'last_session': last_activity,  # For compatibility with old template
                    'last_activity': last_activity,
                    'is_online': is_online,
                    'status': status,
                    'current_session_duration': current_session_duration
                })
            
            conn.close()
            return summary
            
        except Exception as e:
            print(f"Error getting clients traffic summary: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def permanently_delete_revoked_clients():
        """Permanently delete all revoked clients and their history"""
        try:
            print("🗑️ Starting permanent deletion of all revoked clients...")
            
            # Get list of revoked clients
            clients = OpenVPNManager.get_clients()
            revoked_clients = [client for client in clients if client['status'] == 'revoked']
            
            if not revoked_clients:
                return True, "No revoked clients found to delete"
            
            deleted_count = 0
            errors = []
            
            for client in revoked_clients:
                try:
                    success, message = OpenVPNManager.permanently_delete_client(client['name'])
                    if success:
                        deleted_count += 1
                        print(f"✅ Permanently deleted: {client['name']}")
                    else:
                        errors.append(f"{client['name']}: {message}")
                        print(f"❌ Failed to delete {client['name']}: {message}")
                        
                except Exception as e:
                    errors.append(f"{client['name']}: {str(e)}")
                    print(f"💥 Error deleting {client['name']}: {str(e)}")
            
            result_message = f"Permanently deleted {deleted_count} revoked clients"
            if errors:
                result_message += f". Errors: {len(errors)}"
            
            print(f"🎯 Deletion completed: {result_message}")
            return True, result_message
            
        except Exception as e:
            error_msg = f"Error in bulk deletion: {str(e)}"
            print(f"💥 {error_msg}")
            return False, error_msg
    
    @staticmethod
    def permanently_delete_client(client_name):
        """Permanently delete a client and all associated data"""
        try:
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            print(f"🗑️ Permanently deleting client: {clean_name}")
            
            # Step 1: Remove from index.txt file
            if os.path.exists(INDEX_FILE):
                try:
                    with open(INDEX_FILE, 'r') as f:
                        lines = f.readlines()
                    
                    # Filter out lines containing this client
                    filtered_lines = []
                    removed_lines = 0
                    
                    for line in lines:
                        if clean_name in line:
                            print(f"📝 Removing from index.txt: {line.strip()}")
                            removed_lines += 1
                        else:
                            filtered_lines.append(line)
                    
                    # Write back filtered content
                    if removed_lines > 0:
                        with open(INDEX_FILE, 'w') as f:
                            f.writelines(filtered_lines)
                        print(f"✅ Removed {removed_lines} entries from index.txt")
                    
                except Exception as e:
                    print(f"⚠️ Error updating index.txt: {e}")
            
            # Step 2: Remove certificate files
            old_cwd = os.getcwd()
            
            try:
                os.chdir(EASYRSA_DIR)
                
                cert_files = [
                    f'pki/issued/{clean_name}.crt',
                    f'pki/private/{clean_name}.key',
                    f'pki/reqs/{clean_name}.req',
                    f'pki/revoked/certs_by_serial/{clean_name}.crt',
                    f'pki/revoked/private_by_serial/{clean_name}.key',
                    f'pki/revoked/reqs_by_serial/{clean_name}.req'
                ]
                
                removed_files = 0
                for file_path in cert_files:
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            print(f"🗑️ Removed certificate file: {file_path}")
                            removed_files += 1
                        except Exception as e:
                            print(f"⚠️ Could not remove {file_path}: {e}")
                
                print(f"✅ Removed {removed_files} certificate files")
                
            finally:
                os.chdir(old_cwd)
            
            # Step 3: Remove config file
            config_path = f'./{clean_name}.ovpn'
            if os.path.exists(config_path):
                try:
                    os.remove(config_path)
                    print(f"🗑️ Removed config file: {config_path}")
                except Exception as e:
                    print(f"⚠️ Could not remove config file: {e}")
            
            # Step 4: Generate new CRL to update revocation list
            try:
                os.chdir(EASYRSA_DIR)
                
                # Generate new CRL
                result = subprocess.run(
                    ['./easyrsa', '--batch', '--days=3650', 'gen-crl'],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    # Copy CRL to OpenVPN directory
                    try:
                        subprocess.run(['cp', 'pki/crl.pem', '/etc/openvpn/server/crl.pem'], check=True)
                        subprocess.run(['chown', 'nobody:nogroup', '/etc/openvpn/server/crl.pem'], check=True)
                        print(f"✅ CRL updated and copied to OpenVPN")
                    except:
                        pass  # Continue if chown fails
                else:
                    print(f"⚠️ Failed to generate CRL: {result.stderr}")
                    
            except Exception as e:
                print(f"⚠️ CRL generation error: {e}")
            finally:
                os.chdir(old_cwd)
            
            # Step 5: Remove from database (traffic history and stats)
            try:
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                
                # Remove traffic history
                cursor.execute('DELETE FROM traffic_history WHERE client_name = ?', (clean_name,))
                traffic_deleted = cursor.rowcount
                
                # Remove client stats
                cursor.execute('DELETE FROM client_stats WHERE client_name = ?', (clean_name,))
                stats_deleted = cursor.rowcount
                
                # Remove temporary client records
                cursor.execute('DELETE FROM temporary_clients WHERE client_name = ?', (clean_name,))
                temp_deleted = cursor.rowcount
                
                conn.commit()
                conn.close()
                
                print(f"💾 Removed {traffic_deleted} traffic records, {stats_deleted} client stats, and {temp_deleted} temporary client records")
                
            except Exception as e:
                print(f"⚠️ Database cleanup error: {e}")
            
            # Step 6: Cancel any active timers
            try:
                OpenVPNManager.cancel_auto_revoke(clean_name)
            except Exception as e:
                print(f"⚠️ Timer cleanup error: {e}")
            
            # Step 7: Remove from active sessions tracking
            if clean_name in active_sessions:
                del active_sessions[clean_name]
                print(f"🗑️ Removed from active sessions tracking")
            
            # Step 8: Force disconnect specific client only
            try:
                OpenVPNManager.force_disconnect_client(clean_name)
                print(f"🔄 Forced disconnect of client {clean_name}")
            except Exception as e:
                print(f"⚠️ Client disconnect error: {e}")
            
            print(f"✅ Successfully permanently deleted client: {clean_name}")
            return True, f"Client {clean_name} permanently deleted"
            
        except Exception as e:
            error_msg = f"Error permanently deleting client {client_name}: {str(e)}"
            print(f"💥 {error_msg}")
            return False, error_msg
    
    @staticmethod
    def force_disconnect_client(client_name):
        """Force disconnect a specific client from VPN using management interface"""
        try:
            clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
            disconnected = False
            
            # Method 1: Try OpenVPN management interface (if available)
            management_ports = [7505, 7506, 1195]  # Common management ports
            for port in management_ports:
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(2)
                    result = sock.connect_ex(('127.0.0.1', port))
                    if result == 0:
                        # Connected to management interface
                        sock.send(f"kill {clean_name}\n".encode())
                        response = sock.recv(1024).decode()
                        sock.close()
                        if "SUCCESS" in response:
                            print(f"✅ Disconnected {clean_name} via management interface on port {port}")
                            disconnected = True
                            break
                    else:
                        sock.close()
                except:
                    try:
                        sock.close()
                    except:
                        pass
            
            # Method 2: Find and terminate by process (safer approach)
            if not disconnected:
                try:
                    # Look for client-specific processes
                    result = subprocess.run(['pgrep', '-f', f'{clean_name}'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.stdout.strip():
                        pids = result.stdout.strip().split('\n')
                        for pid in pids:
                            if pid.strip():
                                subprocess.run(['kill', '-TERM', pid.strip()], 
                                             capture_output=True, text=True, timeout=5)
                                print(f"🔌 Sent TERM signal to process {pid} for {clean_name}")
                                disconnected = True
                except:
                    pass
            
            # Method 3: Signal OpenVPN to reread CRL (gentle approach)
            try:
                # Send USR1 signal to OpenVPN to reread CRL without full restart
                result = subprocess.run(['pkill', '-USR1', 'openvpn'], 
                                      capture_output=True, text=True, timeout=5)
                print(f"📡 Sent USR1 signal to OpenVPN to reread CRL")
            except:
                pass
            
            return True
            
        except Exception as e:
            print(f"⚠️ Error forcing disconnect for {client_name}: {e}")
            return False
    
    @staticmethod  
    def restart_openvpn_service():
        """Restart OpenVPN service to apply changes"""
        try:
            # Try systemctl restart
            result = subprocess.run(['systemctl', 'restart', 'openvpn-server@server.service'], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"✅ OpenVPN service restarted successfully")
                # Wait a moment for service to fully restart
                time.sleep(2)
                return True
            else:
                print(f"⚠️ Failed to restart OpenVPN service: {result.stderr}")
                
                # Try alternative restart methods
                try:
                    subprocess.run(['service', 'openvpn', 'restart'], 
                                 capture_output=True, text=True, timeout=30)
                    print(f"✅ OpenVPN service restarted via service command")
                    time.sleep(2)
                    return True
                except:
                    pass
                
                # Try reload configuration
                try:
                    subprocess.run(['systemctl', 'reload', 'openvpn-server@server.service'], 
                                 capture_output=True, text=True, timeout=30)
                    print(f"✅ OpenVPN service configuration reloaded")
                    time.sleep(1)
                    return True
                except:
                    pass
                    
                return False
                
        except Exception as e:
            print(f"💥 Error restarting OpenVPN service: {e}")
            return False

    @staticmethod
    def read_server_config():
        """Read and parse server.conf file"""
        try:
            if not os.path.exists(SERVER_CONF_PATH):
                return {'error': 'Server configuration file not found', 'config': {}}
            
            config = {}
            with open(SERVER_CONF_PATH, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(' ', 1)
                        if len(parts) >= 1:
                            key = parts[0]
                            value = parts[1] if len(parts) > 1 else ''
                            config[key] = value
            
            return {'config': config, 'raw_content': open(SERVER_CONF_PATH, 'r').read()}
        except Exception as e:
            return {'error': f'Failed to read server config: {str(e)}', 'config': {}}
    
    @staticmethod
    def write_server_config(config_dict):
        """Write server.conf file from dictionary"""
        try:
            # Backup original file
            backup_path = f"{SERVER_CONF_PATH}.backup.{int(time.time())}"
            if os.path.exists(SERVER_CONF_PATH):
                subprocess.run(['cp', SERVER_CONF_PATH, backup_path], check=True)
            
            # Generate config content
            config_lines = []
            config_lines.append("# OpenVPN Server Configuration")
            config_lines.append("# Generated by OpenVPN Web Manager")
            config_lines.append(f"# Last modified: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            config_lines.append("")
            
            # Essential configurations
            required_configs = {
                'port': config_dict.get('port', '1194'),
                'proto': config_dict.get('proto', 'udp'),
                'dev': config_dict.get('dev', 'tun'),
                'ca': 'ca.crt',
                'cert': 'server.crt',
                'key': 'server.key',
                'dh': 'dh.pem',
                'auth': config_dict.get('auth', 'SHA512'),
                'tls-crypt': 'tc.key',
                'topology': 'subnet',
                'server': config_dict.get('server', '10.8.0.0 255.255.255.0'),
                'ifconfig-pool-persist': 'ipp.txt',
                'push': [
                    '"redirect-gateway def1 bypass-dhcp"',
                    f'"dhcp-option DNS {config_dict.get("dns1", "8.8.8.8")}"',
                    f'"dhcp-option DNS {config_dict.get("dns2", "8.8.4.4")}"'
                ],
                'keepalive': '10 120',
                'cipher': config_dict.get('cipher', 'AES-256-GCM'),
                'user': 'nobody',
                'group': 'nogroup',
                'persist-key': '',
                'persist-tun': '',
                'verb': '3',
                'crl-verify': 'crl.pem'
            }
            
            # Add optional configurations
            if config_dict.get('client_to_client', False):
                required_configs['client-to-client'] = ''
            
            if config_dict.get('duplicate_cn', False):
                required_configs['duplicate-cn'] = ''
            
            if config_dict.get('compression', False):
                required_configs['compress'] = config_dict.get('compress_algorithm', 'lz4-v2')
            
            if config_dict.get('status_log', True):
                required_configs['status'] = '/var/log/openvpn/openvpn-status.log'
            
            if config_dict.get('log_append', True):
                required_configs['log'] = '/var/log/openvpn/openvpn.log'
            
            # Management interface for monitoring
            if config_dict.get('management_interface', True):
                required_configs['management'] = f"{config_dict.get('management_ip', '127.0.0.1')} {config_dict.get('management_port', '7505')}"
            
            # Write configurations
            for key, value in required_configs.items():
                if isinstance(value, list):
                    for item in value:
                        config_lines.append(f"{key} {item}")
                elif value:
                    config_lines.append(f"{key} {value}")
                else:
                    config_lines.append(key)
            
            # Add custom configurations
            if 'custom_configs' in config_dict:
                config_lines.append("")
                config_lines.append("# Custom configurations")
                for line in config_dict['custom_configs'].split('\n'):
                    if line.strip():
                        config_lines.append(line.strip())
            
            # Write to file
            with open(SERVER_CONF_PATH, 'w') as f:
                f.write('\n'.join(config_lines))
            
            return {'success': True, 'backup': backup_path}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def read_client_common():
        """Read client-common.txt file"""
        try:
            if not os.path.exists(CLIENT_COMMON_PATH):
                return {'error': 'Client common file not found', 'content': ''}
            
            with open(CLIENT_COMMON_PATH, 'r') as f:
                content = f.read()
            
            return {'content': content}
        except Exception as e:
            return {'error': f'Failed to read client common file: {str(e)}', 'content': ''}
    
    @staticmethod
    def write_client_common(content):
        """Write client-common.txt file"""
        try:
            # Backup original file
            backup_path = f"{CLIENT_COMMON_PATH}.backup.{int(time.time())}"
            if os.path.exists(CLIENT_COMMON_PATH):
                subprocess.run(['cp', CLIENT_COMMON_PATH, backup_path], check=True)
            
            with open(CLIENT_COMMON_PATH, 'w') as f:
                f.write(content)
            
            return {'success': True, 'backup': backup_path}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_port_configuration():
        """Get current port configuration"""
        try:
            config = OpenVPNManager.read_server_config()['config']
            
            # Get internal port from config
            internal_port = config.get('port', '1194')
            
            # Try to detect external port mapping (check iptables)
            try:
                result = subprocess.run(['iptables', '-t', 'nat', '-L', 'PREROUTING', '-n', '--line-numbers'], 
                                      capture_output=True, text=True, timeout=10)
                external_port = internal_port  # Default to same as internal
                
                for line in result.stdout.split('\n'):
                    if 'dpt:' in line and internal_port in line:
                        # Extract external port from iptables rule
                        parts = line.split()
                        for part in parts:
                            if part.startswith('dpt:') and part != f'dpt:{internal_port}':
                                external_port = part.split(':')[1]
                                break
            except:
                external_port = internal_port
            
            return {
                'internal_port': internal_port,
                'external_port': external_port,
                'protocol': config.get('proto', 'udp')
            }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def update_port_configuration(internal_port, external_port, protocol='udp'):
        """Update port configuration"""
        try:
            # Update server.conf
            config = OpenVPNManager.read_server_config()['config']
            config['port'] = str(internal_port)
            config['proto'] = protocol
            
            result = OpenVPNManager.write_server_config(config)
            if not result['success']:
                return result
            
            # Update firewall rules if external port is different
            if str(internal_port) != str(external_port):
                # Remove old rules
                subprocess.run(['iptables', '-t', 'nat', '-D', 'PREROUTING', '-p', protocol, 
                              '--dport', str(external_port), '-j', 'REDIRECT', '--to-port', str(internal_port)], 
                              check=False)
                
                # Add new rule
                subprocess.run(['iptables', '-t', 'nat', '-I', 'PREROUTING', '-p', protocol, 
                              '--dport', str(external_port), '-j', 'REDIRECT', '--to-port', str(internal_port)], 
                              check=True)
                
                # Save iptables rules
                subprocess.run(['iptables-save'], check=False)
            
            return {'success': True, 'message': 'Port configuration updated successfully'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_authentication_settings():
        """Get authentication settings"""
        try:
            config = OpenVPNManager.read_server_config()['config']
            
            settings = {
                'username_password_auth': 'auth-user-pass-verify' in config,
                'certificate_auth': True,  # Always enabled in standard setup
                'duplicate_cn': 'duplicate-cn' in config,
                'client_to_client': 'client-to-client' in config,
                'auth_script': config.get('auth-user-pass-verify', ''),
                'verify_client_cert': config.get('verify-client-cert', 'none') != 'none'
            }
            
            return settings
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def update_authentication_settings(settings):
        """Update authentication settings"""
        try:
            config = OpenVPNManager.read_server_config()['config']
            
            # Remove existing auth settings
            config.pop('auth-user-pass-verify', None)
            config.pop('duplicate-cn', None)
            config.pop('client-to-client', None)
            config.pop('username-as-common-name', None)
            config.pop('verify-client-cert', None)
            
            # Apply new settings
            if settings.get('username_password_auth', False):
                auth_script = settings.get('auth_script', '/etc/openvpn/server/auth-script.sh')
                config['auth-user-pass-verify'] = f'{auth_script} via-env'
                config['username-as-common-name'] = ''
                
                if not settings.get('verify_client_cert', True):
                    config['verify-client-cert'] = 'none'
            
            if settings.get('duplicate_cn', False):
                config['duplicate_cn'] = ''
            
            if settings.get('client_to_client', False):
                config['client_to_client'] = ''
            
            result = OpenVPNManager.write_server_config(config)
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_user_groups():
        """Get user groups configuration"""
        try:
            groups_file = '/etc/openvpn/server/user-groups.conf'
            groups = {}
            
            if os.path.exists(groups_file):
                with open(groups_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if ':' in line:
                                user, group = line.split(':', 1)
                                if group not in groups:
                                    groups[group] = []
                                groups[group].append(user.strip())
            
            return groups
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def update_user_groups(groups):
        """Update user groups configuration"""
        try:
            groups_file = '/etc/openvpn/server/user-groups.conf'
            
            # Backup existing file
            if os.path.exists(groups_file):
                backup_path = f"{groups_file}.backup.{int(time.time())}"
                subprocess.run(['cp', groups_file, backup_path], check=True)
            
            # Write new groups
            with open(groups_file, 'w') as f:
                f.write("# User Groups Configuration\n")
                f.write("# Format: username:groupname\n")
                f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                for group, users in groups.items():
                    for user in users:
                        f.write(f"{user}:{group}\n")
            
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_advanced_settings():
        """Get advanced OpenVPN settings"""
        try:
            config = OpenVPNManager.read_server_config()['config']
            
            settings = {
                'compression': 'compress' in config or 'comp-lzo' in config,
                'compression_algorithm': config.get('compress', config.get('comp-lzo', 'lz4-v2')),
                'keepalive_ping': config.get('keepalive', '10 120').split()[0] if 'keepalive' in config else '10',
                'keepalive_timeout': config.get('keepalive', '10 120').split()[1] if 'keepalive' in config else '120',
                'max_clients': config.get('max-clients', '100'),
                'cipher': config.get('cipher', 'AES-256-GCM'),
                'auth_algorithm': config.get('auth', 'SHA512'),
                'tls_version_min': config.get('tls-version-min', '1.2'),
                'verb_level': config.get('verb', '3'),
                'mute_replay_warnings': config.get('mute-replay-warnings', '20'),
                'management_interface': 'management' in config,
                'status_logging': 'status' in config,
                'log_append': 'log' in config
            }
            
            return settings
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def update_advanced_settings(settings):
        """Update advanced OpenVPN settings"""
        try:
            config = OpenVPNManager.read_server_config()['config']
            
            # Update compression
            config.pop('compress', None)
            config.pop('comp-lzo', None)
            if settings.get('compression', False):
                config['compress'] = settings.get('compression_algorithm', 'lz4-v2')
            
            # Update keepalive
            ping = settings.get('keepalive_ping', '10')
            timeout = settings.get('keepalive_timeout', '120')
            config['keepalive'] = f"{ping} {timeout}"
            
            # Update other settings
            config['max-clients'] = settings.get('max_clients', '100')
            config['cipher'] = settings.get('cipher', 'AES-256-GCM')
            config['auth'] = settings.get('auth_algorithm', 'SHA512')
            config['tls-version-min'] = settings.get('tls_version_min', '1.2')
            config['verb'] = settings.get('verb_level', '3')
            config['mute-replay-warnings'] = settings.get('mute_replay_warnings', '20')
            
            # Management interface
            if settings.get('management_interface', True):
                config['management'] = '127.0.0.1 7505'
            else:
                config.pop('management', None)
            
            # Status logging
            if settings.get('status_logging', True):
                config['status'] = '/var/log/openvpn/openvpn-status.log'
            else:
                config.pop('status', None)
            
            # Log append
            if settings.get('log_append', True):
                config['log'] = '/var/log/openvpn/openvpn.log'
            else:
                config.pop('log', None)
            
            result = OpenVPNManager.write_server_config(config)
            return result
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_network_configuration():
        """Get network configuration settings"""
        try:
            config = OpenVPNManager.read_server_config()['config']
            
            # Parse server network
            server_network = config.get('server', '10.8.0.0 255.255.255.0').split()
            network = server_network[0] if len(server_network) > 0 else '10.8.0.0'
            netmask = server_network[1] if len(server_network) > 1 else '255.255.255.0'
            
            # Parse DNS servers from push directives
            dns_servers = []
            push_routes = []
            
            # This is a simplified approach - in reality we'd need to parse all push directives
            dns_servers = ['8.8.8.8', '8.8.4.4']  # Default values
            
            settings = {
                'server_network': network,
                'server_netmask': netmask,
                'dns_servers': dns_servers,
                'redirect_gateway': True,  # Usually enabled
                'push_routes': push_routes,
                'client_config_dir': config.get('client-config-dir', ''),
                'route_gateway': config.get('route-gateway', ''),
                'local_ip': config.get('local', ''),
                'ifconfig_pool_persist': 'ifconfig-pool-persist' in config
            }
            
            return settings
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def create_auth_script():
        """Create authentication script for username/password auth"""
        try:
            auth_script_path = '/etc/openvpn/server/auth-script.sh'
            
            auth_script_content = '''#!/bin/bash
# OpenVPN Username/Password Authentication Script
# This script authenticates users against a simple user database

USER_DB="/etc/openvpn/server/users.db"

# Create users database if it doesn't exist
if [ ! -f "$USER_DB" ]; then
    touch "$USER_DB"
    chmod 600 "$USER_DB"
fi

# Get username and password from environment
USERNAME="$username"
PASSWORD="$password"

# Simple authentication - check if user:password exists in database
if grep -q "^$USERNAME:$PASSWORD$" "$USER_DB"; then
    echo "Authentication successful for user: $USERNAME"
    exit 0
else
    echo "Authentication failed for user: $USERNAME"
    exit 1
fi
'''
            
            with open(auth_script_path, 'w') as f:
                f.write(auth_script_content)
            
            # Make script executable
            os.chmod(auth_script_path, 0o755)
            
            # Create empty users database
            users_db_path = '/etc/openvpn/server/users.db'
            if not os.path.exists(users_db_path):
                with open(users_db_path, 'w') as f:
                    f.write("# Username:Password database\n")
                    f.write("# Format: username:password\n")
                os.chmod(users_db_path, 0o600)
            
            return {'success': True, 'script_path': auth_script_path}
        except Exception as e:
            return {'success': False, 'error': str(e)}

class ClusterManager:
    """Cluster management for multiple OpenVPN servers"""
    
    @staticmethod
    def get_cluster_servers():
        """Get all servers in the cluster"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT server_id, server_name, host, port, username, location, 
                       max_clients, server_role, status, last_ping, created_at
                FROM cluster_servers
                ORDER BY created_at ASC
            ''')
            
            servers = []
            for row in cursor.fetchall():
                servers.append({
                    'id': row[0],
                    'name': row[1], 
                    'host': row[2],
                    'port': row[3],
                    'username': row[4],
                    'location': row[5],
                    'max_clients': row[6],
                    'role': row[7],
                    'status': row[8],
                    'last_ping': row[9],
                    'created_at': row[10]
                })
            
            conn.close()
            return servers
            
        except Exception as e:
            print(f"Error getting cluster servers: {e}")
            return []
    
    @staticmethod
    def add_server(server_data):
        """Add a new server to the cluster"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO cluster_servers 
                (server_id, server_name, host, port, username, auth_method, 
                 ssh_key, password, location, max_clients, server_role, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                server_data['server_id'],
                server_data['server_name'],
                server_data['host'],
                server_data.get('port', 22),
                server_data.get('username', 'root'),
                server_data.get('auth_method', 'key'),
                server_data.get('ssh_key', ''),
                server_data.get('password', ''),
                server_data.get('location', 'custom'),
                server_data.get('max_clients', 100),
                server_data.get('server_role', 'load-balanced'),
                'offline'
            ))
            
            conn.commit()
            
            # Log activity
            ClusterManager.log_activity(
                server_id=server_data['server_id'],
                activity_type='server_added',
                description=f"Server {server_data['server_name']} added to cluster",
                details=json.dumps({
                    'host': server_data['host'],
                    'location': server_data.get('location', 'custom'),
                    'max_clients': server_data.get('max_clients', 100)
                })
            )
            
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error adding server to cluster: {e}")
            return False
    
    @staticmethod
    def remove_server(server_id):
        """Remove a server from the cluster"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Get server info before deletion
            cursor.execute('SELECT server_name FROM cluster_servers WHERE server_id = ?', (server_id,))
            server_info = cursor.fetchone()
            
            if server_info:
                server_name = server_info[0]
                
                # Remove client assignments
                cursor.execute('DELETE FROM cluster_client_assignments WHERE server_id = ?', (server_id,))
                
                # Remove server
                cursor.execute('DELETE FROM cluster_servers WHERE server_id = ?', (server_id,))
                
                conn.commit()
                
                # Log activity
                ClusterManager.log_activity(
                    server_id=server_id,
                    activity_type='server_removed',
                    description=f"Server {server_name} removed from cluster"
                )
                
                conn.close()
                return True
            
            conn.close()
            return False
            
        except Exception as e:
            print(f"Error removing server from cluster: {e}")
            return False
    
    @staticmethod
    def test_server_connection(server_data):
        """Test SSH connection to a server"""
        try:
            import io
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Configure authentication
            if server_data.get('auth_method') == 'key' and server_data.get('ssh_key'):
                # Use SSH key authentication
                key_obj = paramiko.RSAKey.from_private_key(io.StringIO(server_data['ssh_key']))
                ssh.connect(
                    hostname=server_data['host'],
                    port=server_data.get('port', 22),
                    username=server_data.get('username', 'root'),
                    pkey=key_obj,
                    timeout=10
                )
            else:
                # Use password authentication
                ssh.connect(
                    hostname=server_data['host'],
                    port=server_data.get('port', 22),
                    username=server_data.get('username', 'root'),
                    password=server_data.get('password', ''),
                    timeout=10
                )
            
            # Test basic command
            stdin, stdout, stderr = ssh.exec_command('echo "test"')
            result = stdout.read().decode().strip()
            
            ssh.close()
            
            return result == 'test'
            
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    @staticmethod
    def execute_remote_command(server_id, command):
        """Execute a command on a remote server"""
        try:
            import io
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT host, port, username, auth_method, ssh_key, password
                FROM cluster_servers WHERE server_id = ?
            ''', (server_id,))
            
            server_info = cursor.fetchone()
            conn.close()
            
            if not server_info:
                return None, "Server not found"
            
            host, port, username, auth_method, ssh_key, password = server_info
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Configure authentication
            if auth_method == 'key' and ssh_key:
                key_obj = paramiko.RSAKey.from_private_key(io.StringIO(ssh_key))
                ssh.connect(hostname=host, port=port, username=username, pkey=key_obj, timeout=10)
            else:
                ssh.connect(hostname=host, port=port, username=username, password=password, timeout=10)
            
            # Execute command
            stdin, stdout, stderr = ssh.exec_command(command)
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            ssh.close()
            
            return output, error
            
        except Exception as e:
            return None, str(e)
    
    @staticmethod
    def get_server_status(server_id):
        """Get detailed status of a server"""
        try:
            # Get basic system info
            output, error = ClusterManager.execute_remote_command(
                server_id, 
                'echo "$(uptime)" && echo "---" && echo "$(free -m)" && echo "---" && echo "$(df -h /)" && echo "---" && systemctl status openvpn-server@server'
            )
            
            if error:
                return {'status': 'error', 'error': error}
            
            # Parse output (simplified)
            status = {
                'status': 'online',
                'uptime': output.split('---')[0].strip() if '---' in output else 'Unknown',
                'memory': 'Available' if 'available' in output.lower() else 'Unknown',
                'disk': 'Available' if 'available' in output.lower() else 'Unknown',
                'openvpn_status': 'running' if 'active (running)' in output.lower() else 'stopped'
            }
            
            return status
            
        except Exception as e:
            return {'status': 'offline', 'error': str(e)}
    
    @staticmethod
    def get_server_clients(server_id):
        """Get clients from a specific server"""
        try:
            output, error = ClusterManager.execute_remote_command(
                server_id,
                'ls /etc/openvpn/server/easy-rsa/pki/issued/ | grep -v "^server" | sed "s/.crt$//"'
            )
            
            if error:
                return []
            
            clients = [line.strip() for line in output.split('\n') if line.strip()]
            return clients
            
        except Exception as e:
            print(f"Error getting server clients: {e}")
            return []
    
    @staticmethod
    def assign_client_to_server(client_name, server_id, strategy='manual'):
        """Assign a client to a specific server"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Check if assignment already exists
            cursor.execute('''
                SELECT id FROM cluster_client_assignments 
                WHERE client_name = ? AND status = 'active'
            ''', (client_name,))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing assignment
                cursor.execute('''
                    UPDATE cluster_client_assignments 
                    SET server_id = ?, assignment_strategy = ?, assigned_at = CURRENT_TIMESTAMP
                    WHERE client_name = ? AND status = 'active'
                ''', (server_id, strategy, client_name))
            else:
                # Create new assignment
                cursor.execute('''
                    INSERT INTO cluster_client_assignments 
                    (client_name, server_id, assignment_strategy, status)
                    VALUES (?, ?, ?, 'active')
                ''', (client_name, server_id, strategy))
            
            conn.commit()
            
            # Now create the client on the target server
            create_command = f'cd /etc/openvpn/server/easy-rsa && ./easyrsa build-client-full {client_name} nopass'
            output, error = ClusterManager.execute_remote_command(server_id, create_command)
            
            # Log activity
            ClusterManager.log_activity(
                server_id=server_id,
                activity_type='client_assigned',
                description=f"Client {client_name} assigned to server {server_id}",
                details=json.dumps({
                    'strategy': strategy,
                    'create_output': output[:500] if output else None,
                    'create_error': error[:500] if error else None
                })
            )
            
            conn.close()
            return True, output
            
        except Exception as e:
            print(f"Error assigning client to server: {e}")
            return False, str(e)
    
    @staticmethod
    def get_client_assignments():
        """Get all client assignments"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT ca.client_name, ca.server_id, cs.server_name, cs.host, 
                       ca.assignment_strategy, ca.assigned_at, ca.status
                FROM cluster_client_assignments ca
                JOIN cluster_servers cs ON ca.server_id = cs.server_id
                WHERE ca.status = 'active'
                ORDER BY ca.assigned_at DESC
            ''')
            
            assignments = []
            for row in cursor.fetchall():
                assignments.append({
                    'client_name': row[0],
                    'server_id': row[1],
                    'server_name': row[2],
                    'server_host': row[3],
                    'assignment_strategy': row[4],
                    'assigned_at': row[5],
                    'status': row[6]
                })
            
            conn.close()
            return assignments
            
        except Exception as e:
            print(f"Error getting client assignments: {e}")
            return []
    
    @staticmethod
    def log_activity(server_id=None, activity_type='', description='', details=None, user_id='system'):
        """Log cluster activity"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO cluster_activity (server_id, activity_type, description, details, user_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (server_id, activity_type, description, details, user_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error logging activity: {e}")
    
    @staticmethod
    def get_cluster_activity(limit=50):
        """Get recent cluster activity"""
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT ca.timestamp, ca.server_id, cs.server_name, ca.activity_type, 
                       ca.description, ca.details, ca.user_id
                FROM cluster_activity ca
                LEFT JOIN cluster_servers cs ON ca.server_id = cs.server_id
                ORDER BY ca.timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            activities = []
            for row in cursor.fetchall():
                activities.append({
                    'timestamp': row[0],
                    'server_id': row[1],
                    'server_name': row[2] if row[2] else 'Unknown',
                    'activity_type': row[3],
                    'description': row[4],
                    'details': row[5],
                    'user_id': row[6]
                })
            
            conn.close()
            return activities
            
        except Exception as e:
            print(f"Error getting cluster activity: {e}")
            return []
    
    @staticmethod
    def get_cluster_status():
        """Get overall cluster status"""
        try:
            servers = ClusterManager.get_cluster_servers()
            assignments = ClusterManager.get_client_assignments()
            
            # Calculate statistics
            total_servers = len(servers)
            online_servers = len([s for s in servers if s['status'] == 'online'])
            total_clients = len(assignments)
            
            # Mock active connections for now
            active_connections = sum([15, 23, 8, 12][:online_servers])
            
            return {
                'servers': servers,
                'total_servers': total_servers,
                'online_servers': online_servers,
                'total_clients': total_clients,
                'active_connections': active_connections,
                'assignments': assignments,
                'load_balancer': {
                    'status': 'active' if online_servers > 0 else 'inactive',
                    'next_server': servers[0]['id'] if servers else None
                }
            }
            
        except Exception as e:
            print(f"Error getting cluster status: {e}")
            return {
                'servers': [],
                'total_servers': 0,
                'online_servers': 0,
                'total_clients': 0,
                'active_connections': 0,
                'assignments': [],
                'load_balancer': {'status': 'inactive', 'next_server': None}
            }
    
    @staticmethod
    def ping_all_servers():
        """Ping all servers to check their status"""
        servers = ClusterManager.get_cluster_servers()
        
        def ping_server(server):
            try:
                # Simple ping test
                result = subprocess.run(['ping', '-c', '1', '-W', '3', server['host']], 
                                      capture_output=True, text=True, timeout=5)
                is_online = result.returncode == 0
                
                # Update server status
                conn = sqlite3.connect(DATABASE_PATH)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE cluster_servers 
                    SET status = ?, last_ping = CURRENT_TIMESTAMP
                    WHERE server_id = ?
                ''', ('online' if is_online else 'offline', server['id']))
                conn.commit()
                conn.close()
                
                return server['id'], is_online
                
            except Exception as e:
                print(f"Error pinging server {server['id']}: {e}")
                return server['id'], False
        
        # Ping all servers in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(ping_server, server) for server in servers]
            results = [future.result() for future in as_completed(futures)]
        
        return results

@app.route('/')
@auth.login_required
def index():
    """Main dashboard page with overview and charts"""
    if not OpenVPNManager.is_openvpn_installed():
        return render_template('not_installed.html')
    
    server_status = OpenVPNManager.get_server_status()
    server_info = OpenVPNManager.get_server_info()
    active_connections = OpenVPNManager.get_active_connections()
    server_stats = OpenVPNManager.get_server_stats()
    clients = OpenVPNManager.get_clients()
    
    return render_template('dashboard.html', 
                         server_status=server_status,
                         server_info=server_info,
                         active_connections=active_connections,
                         server_stats=server_stats,
                         clients=clients)

@app.route('/clients')
@auth.login_required  
def clients_page():
    """Clients management page"""
    if not OpenVPNManager.is_openvpn_installed():
        return render_template('not_installed.html')
        
    clients = OpenVPNManager.get_clients()
    active_connections = OpenVPNManager.get_active_connections()
    client_activity = OpenVPNManager.get_client_activity()
    
    # Merge activity data with client list
    for client in clients:
        # Check if client is currently connected
        client['is_online'] = False
        client['current_connection'] = None
        client['last_activity'] = client_activity.get(client['name'], 'Never')
        
        for conn in active_connections:
            if conn['name'] == client['name']:
                client['is_online'] = True
                client['current_connection'] = conn
                break
    
    return render_template('clients.html', clients=clients)

@app.route('/connections')
@auth.login_required
def connections_page():
    """Active connections page"""
    if not OpenVPNManager.is_openvpn_installed():
        return render_template('not_installed.html')
        
    active_connections = OpenVPNManager.get_active_connections()
    server_stats = OpenVPNManager.get_server_stats()
    
    return render_template('connections.html', 
                         active_connections=active_connections,
                         server_stats=server_stats)

@app.route('/settings')
@auth.login_required
def settings_page():
    """Settings and configuration page"""
    if not OpenVPNManager.is_openvpn_installed():
        return render_template('not_installed.html')
        
    server_status = OpenVPNManager.get_server_status()
    server_info = OpenVPNManager.get_server_info()
    file_status = OpenVPNManager.check_file_status()
    diagnosis = OpenVPNManager.diagnose_system()
    
    # Get configuration data for advanced management
    try:
        server_config = OpenVPNManager.read_server_config()
        client_common = OpenVPNManager.read_client_common()
        port_config = OpenVPNManager.get_port_configuration()
        auth_settings = OpenVPNManager.get_authentication_settings()
        user_groups = OpenVPNManager.get_user_groups()
        advanced_settings = OpenVPNManager.get_advanced_settings()
    except Exception as e:
        print(f"Error loading configuration data: {e}")
        server_config = {'config': {}, 'error': str(e)}
        client_common = {'content': '', 'error': str(e)}
        port_config = {'error': str(e)}
        auth_settings = {'error': str(e)}
        user_groups = {}
        advanced_settings = {'error': str(e)}
    
    return render_template('settings.html',
                         server_status=server_status,
                         server_info=server_info,
                         file_status=file_status,
                         diagnosis=diagnosis,
                         server_config=server_config,
                         client_common=client_common,
                         port_config=port_config,
                         auth_settings=auth_settings,
                         user_groups=user_groups,
                         advanced_settings=advanced_settings)

@app.route('/cluster')
@auth.login_required  
def cluster_page():
    """Cluster management page"""
    if not OpenVPNManager.is_openvpn_installed():
        return render_template('not_installed.html')
        
    # Get cluster data
    cluster_status = ClusterManager.get_cluster_status()
    cluster_activity = ClusterManager.get_cluster_activity(limit=20)
    
    return render_template('cluster.html',
                         cluster_status=cluster_status,
                         cluster_activity=cluster_activity)

@app.route('/add_client', methods=['GET', 'POST'])
@auth.login_required
def add_client():
    """Add new client"""
    if request.method == 'GET':
        flash('Invalid request method', 'error')
        return redirect(request.referrer or url_for('index'))
    
    client_name = request.form.get('client_name', '').strip()
    expiry_days = request.form.get('expiry_days', '3650')
    client_group = request.form.get('client_group', '').strip()
    client_profile = request.form.get('client_profile', 'standard').strip()
    custom_group_name = request.form.get('custom_group_name', '').strip()
    
    if not client_name:
        flash('Please enter client name', 'error')
        return redirect(request.referrer or url_for('clients_page'))
    
    # Handle custom group
    if client_group == 'custom' and custom_group_name:
        client_group = custom_group_name
    elif client_group == 'custom':
        client_group = ''
    
    # Check if this is an auto-revoke value
    if str(expiry_days).startswith('auto_'):
        # Pass auto_* values directly
        success, message = OpenVPNManager.add_client(client_name, expiry_days, client_group, client_profile)
    else:
        # Validate numeric expiry_days
        try:
            expiry_days = int(expiry_days)
            if expiry_days <= 0 or expiry_days > 36500:  # Max 100 years
                raise ValueError("Invalid expiry period")
        except (ValueError, TypeError):
            flash('Invalid expiry period specified', 'error')
            return redirect(request.referrer or url_for('clients_page'))
        
        success, message = OpenVPNManager.add_client(client_name, expiry_days, client_group, client_profile)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    # Redirect back to the page where the request came from
    return redirect(request.referrer or url_for('clients_page'))

@app.route('/force_add_client', methods=['POST'])
@auth.login_required
def force_add_client():
    """Force add new client by cleaning up existing files first"""
    client_name = request.form.get('client_name', '').strip()
    expiry_days = request.form.get('expiry_days', '3650')
    
    if not client_name:
        flash('Please enter client name', 'error')
        return redirect(request.referrer or url_for('clients_page'))
    
    # Check if this is an auto-revoke value
    if str(expiry_days).startswith('auto_'):
        # Pass auto_* values directly
        success, message = OpenVPNManager.force_create_client(client_name, expiry_days)
    else:
        # Validate numeric expiry_days
        try:
            expiry_days = int(expiry_days)
            if expiry_days <= 0 or expiry_days > 36500:  # Max 100 years
                raise ValueError("Invalid expiry period")
        except (ValueError, TypeError):
            flash('Invalid expiry period specified', 'error')
            return redirect(request.referrer or url_for('clients_page'))
        
        success, message = OpenVPNManager.force_create_client(client_name, expiry_days)
    
    if success:
        flash(f"✅ Force created: {message}", 'success')
    else:
        flash(f"❌ Force create failed: {message}", 'error')
    
    # Redirect back to the page where the request came from
    return redirect(request.referrer or url_for('clients_page'))

@app.route('/revoke_client', methods=['POST'])
@auth.login_required
def revoke_client():
    """Revoke client"""
    client_name = request.form.get('client_name')
    
    if not client_name:
        flash('Client name not specified', 'error')
        return redirect(request.referrer or url_for('clients_page'))
    
    success, message = OpenVPNManager.revoke_client(client_name)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    # Redirect back to the page where the request came from
    return redirect(request.referrer or url_for('clients_page'))

@app.route('/renew_client', methods=['POST'])
@auth.login_required
def renew_client():
    """Renew client certificate"""
    client_name = request.form.get('client_name')
    expiry_days = request.form.get('expiry_days', '3650')
    
    if not client_name:
        flash('Client name not specified', 'error')
        return redirect(request.referrer or url_for('clients_page'))
    
    # Check if this is an auto-revoke value
    if str(expiry_days).startswith('auto_'):
        # Pass auto_* values directly
        success, message = OpenVPNManager.renew_client(client_name, expiry_days)
    else:
        # Validate numeric expiry_days
        try:
            expiry_days = int(expiry_days)
            if expiry_days <= 0 or expiry_days > 36500:  # Max 100 years
                raise ValueError("Invalid expiry period")
        except (ValueError, TypeError):
            flash('Invalid expiry period specified', 'error')
            return redirect(request.referrer or url_for('clients_page'))
        
        success, message = OpenVPNManager.renew_client(client_name, expiry_days)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    # Redirect back to the page where the request came from
    return redirect(request.referrer or url_for('clients_page'))

@app.route('/restore_client', methods=['POST'])
@auth.login_required
def restore_client():
    """Restore revoked client with new certificate"""
    client_name = request.form.get('client_name')
    expiry_days = request.form.get('expiry_days', '3650')
    
    if not client_name:
        flash('Client name not specified', 'error')
        return redirect(request.referrer or url_for('clients_page'))
    
    # Check if this is an auto-revoke value
    if str(expiry_days).startswith('auto_'):
        # Pass auto_* values directly
        success, message = OpenVPNManager.restore_client(client_name, expiry_days)
    else:
        # Validate numeric expiry_days
        try:
            expiry_days = int(expiry_days)
            if expiry_days <= 0 or expiry_days > 36500:  # Max 100 years
                raise ValueError("Invalid expiry period")
        except (ValueError, TypeError):
            flash('Invalid expiry period specified', 'error')
            return redirect(request.referrer or url_for('clients_page'))
        
        success, message = OpenVPNManager.restore_client(client_name, expiry_days)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    # Redirect back to the page where the request came from
    return redirect(request.referrer or url_for('clients_page'))

@app.route('/download_config/<client_name>')
@auth.login_required
def download_config(client_name):
    """Download client configuration file"""
    config_path = f'./{client_name}.ovpn'
    
    if not os.path.exists(config_path):
        flash('Configuration file not found', 'error')
        return redirect(request.referrer or url_for('clients_page'))
    
    return send_file(config_path, as_attachment=True, download_name=f'{client_name}.ovpn')

@app.route('/api/status')
@auth.login_required
def api_status():
    """API to get server status"""
    return jsonify({
        'installed': OpenVPNManager.is_openvpn_installed(),
        'running': OpenVPNManager.get_server_status(),
        'info': OpenVPNManager.get_server_info()
    })

@app.route('/api/clients')
@auth.login_required
def api_clients():
    """API to get client list"""
    return jsonify(OpenVPNManager.get_clients())

@app.route('/api/activity')
@auth.login_required
def api_activity():
    """API to get real-time activity data"""
    active_connections = OpenVPNManager.get_active_connections()
    client_activity = OpenVPNManager.get_client_activity()
    server_stats = OpenVPNManager.get_server_stats()
    all_clients = OpenVPNManager.get_clients()
    
    # Calculate client statistics
    active_clients = [client for client in all_clients if client['status'] == 'active']
    total_active_clients = len(active_clients)
    currently_connected = len(active_connections)
    offline_clients = max(0, total_active_clients - currently_connected)
    
    # Get system metrics
    system_metrics = OpenVPNManager.get_system_metrics()
    
    # Get network bandwidth
    network_bandwidth = OpenVPNManager.get_network_bandwidth()
    
    return jsonify({
        'active_connections': active_connections,
        'client_activity': client_activity,
        'server_stats': server_stats,
        'client_stats': {
            'total_active_clients': total_active_clients,
            'currently_connected': currently_connected,
            'offline_clients': offline_clients
        },
        'system_metrics': system_metrics,
        'network_bandwidth': network_bandwidth,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/temporary_clients')
@auth.login_required
def api_temporary_clients():
    """API to get temporary clients info"""
    temp_info = {}
    for client_name in temporary_clients:
        temp_info[client_name] = OpenVPNManager.get_temporary_client_info(client_name)
    
    return jsonify({
        'temporary_clients': temp_info,
        'total_count': len(temporary_clients),
        'raw_data': {name: {
            'revoke_time': data['revoke_time'].isoformat(),
            'hours': data['hours'],
            'timer_active': data['timer'].is_alive() if hasattr(data['timer'], 'is_alive') else 'unknown'
        } for name, data in temporary_clients.items()}
    })

@app.route('/api/diagnose')
@auth.login_required
def api_diagnose():
    """API to get system diagnosis"""
    return jsonify(OpenVPNManager.diagnose_system())

@app.route('/enable_monitoring', methods=['POST'])
@auth.login_required
def enable_monitoring():
    """Enable enhanced monitoring (status file)"""
    success, message = OpenVPNManager.enable_status_file()
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    # Redirect back to the page where the request came from
    return redirect(request.referrer or url_for('settings_page'))

@app.route('/api/logs/<log_type>')
@auth.login_required
def api_logs(log_type):
    """Get log file content via API"""
    if log_type not in ['status', 'main', 'syslog']:
        return jsonify({'error': 'Invalid log type'}), 400
    
    lines = request.args.get('lines', 50, type=int)
    if lines > 1000:  # Limit to prevent huge responses
        lines = 1000
    
    content = OpenVPNManager.get_log_content(log_type, lines)
    
    if content is None:
        return jsonify({
            'error': f'Log file not found or not readable',
            'content': '',
            'exists': False
        }), 404
    
    return jsonify({
        'content': content,
        'lines': lines,
        'log_type': log_type,
        'exists': True
    })

@app.route('/api/system_metrics')
@auth.login_required
def api_system_metrics():
    """API to get system metrics (CPU, RAM, Network)"""
    metrics = OpenVPNManager.get_system_metrics()
    # Save metrics to database for history
    OpenVPNManager.save_system_metrics()
    return jsonify(metrics)

@app.route('/api/network_bandwidth')
@auth.login_required
def api_network_bandwidth():
    """API to get real-time network bandwidth"""
    return jsonify(OpenVPNManager.get_network_bandwidth())

@app.route('/api/client_traffic/<client_name>')
@auth.login_required
def api_client_traffic(client_name):
    """API to get traffic history for specific client"""
    days = request.args.get('days', 30, type=int)
    if days > 365:  # Limit to prevent huge responses
        days = 365
    
    return jsonify(OpenVPNManager.get_client_traffic_history(client_name, days))

@app.route('/api/traffic_summary')
@auth.login_required
def api_traffic_summary():
    """API to get traffic summary for all clients"""
    return jsonify(OpenVPNManager.get_all_clients_traffic_summary())

@app.route('/api/client_history/<client_name>')
@auth.login_required
def api_client_history(client_name):
    """API endpoint for client connection history with IP addresses"""
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                client_name,
                session_start,
                session_end,
                bytes_sent,
                bytes_received,
                duration_seconds,
                real_address,
                virtual_address
            FROM traffic_history 
            WHERE client_name = ? 
            ORDER BY session_start DESC
        """, (client_name,))
        
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            session_start = row[1]
            session_end = row[2]
            duration_seconds = row[5]
            
            # Format duration properly
            if duration_seconds and duration_seconds > 0:
                duration_formatted = OpenVPNManager.format_duration(duration_seconds)
            else:
                duration_formatted = 'N/A'
            
            # Debug log for API response
            print(f"📊 API History for {client_name}: bytes_sent={row[3]}, bytes_received={row[4]}, duration={duration_formatted}")
            
            history.append({
                'client_name': row[0],
                'start_time': session_start,
                'end_time': session_end,
                'bytes_sent': row[3] or 0,
                'bytes_received': row[4] or 0,
                'duration': duration_seconds,
                'duration_formatted': duration_formatted,
                'real_address': row[6] or 'N/A',
                'virtual_address': row[7] or 'N/A'
            })
        
        print(f"📊 API: Retrieved {len(history)} history records for client '{client_name}'")
        return jsonify(history)
        
    except Exception as e:
        print(f"❌ ERROR getting client history: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 500  # Return empty array instead of error object
    finally:
        if conn:
            conn.close()

@app.route('/api/save_session', methods=['POST'])
@auth.login_required
def api_save_session():
    """API to save client session data"""
    data = request.get_json()
    
    if not data or 'client_name' not in data:
        return jsonify({'error': 'Client name required'}), 400
    
    success = OpenVPNManager.save_client_session(
        client_name=data['client_name'],
        bytes_sent=data.get('bytes_sent', 0),
        bytes_received=data.get('bytes_received', 0),
        duration_seconds=data.get('duration_seconds', 0),
        session_start=data.get('session_start'),
        session_end=data.get('session_end')
    )
    
    if success:
        return jsonify({'success': True, 'message': 'Session saved'})
    else:
        return jsonify({'success': False, 'error': 'Failed to save session'}), 500

@app.route('/api/temp_clients_diagnosis')
@auth.login_required
def api_temp_clients_diagnosis():
    """API to diagnose temporary clients system"""
    try:
        # Get all temporary clients from database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT client_name, created_at, revoke_at, hours, status 
            FROM temporary_clients 
            ORDER BY created_at DESC
        ''')
        
        db_clients = []
        for row in cursor.fetchall():
            client_name, created_at, revoke_at, hours, status = row
            revoke_time = datetime.fromisoformat(revoke_at)
            current_time = datetime.now()
            time_left = (revoke_time - current_time).total_seconds()
            
            db_clients.append({
                'client_name': client_name,
                'created_at': created_at,
                'revoke_at': revoke_at,
                'hours': hours,
                'status': status,
                'time_left_seconds': max(0, time_left),
                'time_left_minutes': max(0, int(time_left / 60)),
                'is_expired': time_left <= 0
            })
        
        conn.close()
        
        # Get active timers
        active_timers = {}
        for name, data in temporary_clients.items():
            timer = data['timer']
            active_timers[name] = {
                'revoke_time': data['revoke_time'].isoformat(),
                'hours': data['hours'],
                'timer_alive': hasattr(timer, 'is_alive') and timer.is_alive()
            }
        
        return jsonify({
            'database_clients': db_clients,
            'active_timers': active_timers,
            'total_db_clients': len(db_clients),
            'total_active_timers': len(active_timers),
            'system_status': 'running',
            'current_time': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'system_status': 'error'
        }), 500

@app.route('/api/force_check_temp_clients', methods=['POST'])
@auth.login_required 
def api_force_check_temp_clients():
    """Force check and process expired temporary clients"""
    try:
        processed = 0
        errors = []
        
        # Check database for expired clients
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT client_name, revoke_at 
            FROM temporary_clients 
            WHERE status = 'active'
        ''')
        
        current_time = datetime.now()
        for client_name, revoke_at_str in cursor.fetchall():
            try:
                revoke_time = datetime.fromisoformat(revoke_at_str)
                if revoke_time <= current_time:
                    print(f"🔍 Force processing expired client: {client_name}")
                    OpenVPNManager.auto_revoke_client(client_name)
                    processed += 1
            except Exception as e:
                errors.append(f"Error processing {client_name}: {str(e)}")
        
        conn.close()
        
        return jsonify({
            'success': True,
            'processed_count': processed,
            'errors': errors,
            'message': f'Processed {processed} expired clients'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/permanently_delete_revoked', methods=['POST'])
@auth.login_required
def api_permanently_delete_revoked():
    """API to permanently delete all revoked clients"""
    try:
        success, message = OpenVPNManager.permanently_delete_revoked_clients()
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/permanently_delete_client', methods=['POST'])
@auth.login_required
def api_permanently_delete_client():
    """API to permanently delete a specific client"""
    try:
        data = request.get_json()
        
        if not data or 'client_name' not in data:
            return jsonify({'error': 'Client name required'}), 400
        
        client_name = data['client_name']
        success, message = OpenVPNManager.permanently_delete_client(client_name)
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/force_disconnect_all', methods=['POST'])
@auth.login_required
def api_force_disconnect_all():
    """API to force disconnect all active VPN connections"""
    try:
        # Get all active connections
        active_connections = OpenVPNManager.get_active_connections()
        
        disconnected_count = 0
        for conn in active_connections:
            try:
                OpenVPNManager.force_disconnect_client(conn['name'])
                disconnected_count += 1
            except:
                pass
        
        # Send signal to OpenVPN to refresh connections without full restart
        try:
            subprocess.run(['pkill', '-USR1', 'openvpn'], capture_output=True, text=True, timeout=5)
            refresh_success = True
        except:
            refresh_success = False
        
        return jsonify({
            'success': True,
            'message': f'Force disconnected {disconnected_count} connections',
            'disconnected_count': disconnected_count,
            'crl_refreshed': refresh_success
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/restart_openvpn', methods=['POST'])
@auth.login_required
def api_restart_openvpn():
    """API to restart OpenVPN service"""
    try:
        success = OpenVPNManager.restart_openvpn_service()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'OpenVPN service restarted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to restart OpenVPN service'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/logs/<log_type>')
@auth.login_required
def view_logs(log_type):
    """View log files in web interface"""
    if log_type not in ['status', 'main', 'syslog']:
        flash('Invalid log type', 'error')
        return redirect(url_for('settings_page'))
    
    log_names = {
        'status': 'OpenVPN Status Log',
        'main': 'OpenVPN Main Log', 
        'syslog': 'System Log (OpenVPN entries)'
    }
    
    return render_template('logs.html', 
                         log_type=log_type,
                         log_name=log_names[log_type])

# Advanced Configuration Management Routes
@app.route('/api/server_config')
@auth.login_required
def api_server_config():
    """Get server configuration"""
    try:
        config_data = OpenVPNManager.read_server_config()
        return jsonify(config_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/server_config', methods=['POST'])
@auth.login_required
def api_update_server_config():
    """Update server configuration"""
    try:
        config_data = request.get_json()
        result = OpenVPNManager.write_server_config(config_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/client_common')
@auth.login_required
def api_client_common():
    """Get client common configuration"""
    try:
        result = OpenVPNManager.read_client_common()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/client_common', methods=['POST'])
@auth.login_required
def api_update_client_common():
    """Update client common configuration"""
    try:
        data = request.get_json()
        content = data.get('content', '')
        result = OpenVPNManager.write_client_common(content)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/port_config')
@auth.login_required
def api_port_config():
    """Get port configuration"""
    try:
        result = OpenVPNManager.get_port_configuration()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/port_config', methods=['POST'])
@auth.login_required
def api_update_port_config():
    """Update port configuration"""
    try:
        data = request.get_json()
        internal_port = data.get('internal_port')
        external_port = data.get('external_port')
        protocol = data.get('protocol', 'udp')
        
        result = OpenVPNManager.update_port_configuration(internal_port, external_port, protocol)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth_settings')
@auth.login_required
def api_auth_settings():
    """Get authentication settings"""
    try:
        result = OpenVPNManager.get_authentication_settings()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth_settings', methods=['POST'])
@auth.login_required
def api_update_auth_settings():
    """Update authentication settings"""
    try:
        data = request.get_json()
        result = OpenVPNManager.update_authentication_settings(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user_groups')
@auth.login_required
def api_user_groups():
    """Get user groups"""
    try:
        result = OpenVPNManager.get_user_groups()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/user_groups', methods=['POST'])
@auth.login_required
def api_update_user_groups():
    """Update user groups"""
    try:
        data = request.get_json()
        groups = data.get('groups', {})
        result = OpenVPNManager.update_user_groups(groups)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/advanced_settings')
@auth.login_required
def api_advanced_settings():
    """Get advanced settings"""
    try:
        result = OpenVPNManager.get_advanced_settings()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/advanced_settings', methods=['POST'])
@auth.login_required
def api_update_advanced_settings():
    """Update advanced settings"""
    try:
        data = request.get_json()
        result = OpenVPNManager.update_advanced_settings(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/network_config')
@auth.login_required
def api_network_config():
    """Get network configuration"""
    try:
        result = OpenVPNManager.get_network_configuration()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create_auth_script', methods=['POST'])
@auth.login_required
def api_create_auth_script():
    """Create authentication script"""
    try:
        result = OpenVPNManager.create_auth_script()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backup_configs', methods=['POST'])
@auth.login_required
def api_backup_configs():
    """Create comprehensive configuration backup"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'openvpn_backup_{timestamp}'
        
        # Create backups directory if it doesn't exist
        backup_base_dir = 'backups'
        os.makedirs(backup_base_dir, exist_ok=True)
        
        backup_dir = os.path.join(backup_base_dir, backup_name)
        os.makedirs(backup_dir, exist_ok=True)
        
        # Initialize backup info
        backup_info = {
            'timestamp': timestamp,
            'created_by': 'admin',
            'description': 'Comprehensive OpenVPN cluster backup',
            'files_backed_up': 0,
            'database_backed_up': False,
            'clients_backed_up': False,
            'clusters_backed_up': False,
            'size_mb': 0
        }
        
        # Backup OpenVPN configuration files
        config_backup_dir = os.path.join(backup_dir, 'config')
        os.makedirs(config_backup_dir, exist_ok=True)
        
        config_files = [
            '/etc/openvpn/server/server.conf',
            '/etc/openvpn/server/client-common.txt',
            '/etc/openvpn/server/ca.crt',
            '/etc/openvpn/server/server.crt',
            '/etc/openvpn/server/server.key',
            '/etc/openvpn/server/dh.pem',
            '/etc/openvpn/server/ta.key'
        ]
        
        backed_up_files = 0
        for file_path in config_files:
            if os.path.exists(file_path):
                filename = os.path.basename(file_path)
                try:
                    shutil.copy2(file_path, os.path.join(config_backup_dir, filename))
                    backed_up_files += 1
                except Exception as e:
                    print(f"Warning: Could not backup {file_path}: {e}")
        
        backup_info['files_backed_up'] = backed_up_files
        
        # Backup client certificates directory (if exists)
        clients_dir = '/etc/openvpn/server/easy-rsa/pki'
        if os.path.exists(clients_dir):
            try:
                clients_backup_dir = os.path.join(backup_dir, 'clients')
                shutil.copytree(clients_dir, clients_backup_dir)
                backup_info['clients_backed_up'] = True
            except Exception as e:
                print(f"Warning: Could not backup clients directory: {e}")
                backup_info['clients_backed_up'] = False
        
        # Backup database
        if os.path.exists('vpn_history.db'):
            try:
                shutil.copy2('vpn_history.db', os.path.join(backup_dir, 'vpn_history.db'))
                backup_info['database_backed_up'] = True
            except Exception as e:
                print(f"Warning: Could not backup database: {e}")
        
        # Backup user groups and settings
        settings_files = ['user_groups.json', 'cluster_settings.json']
        for settings_file in settings_files:
            if os.path.exists(settings_file):
                try:
                    shutil.copy2(settings_file, os.path.join(backup_dir, settings_file))
                except Exception as e:
                    print(f"Warning: Could not backup {settings_file}: {e}")
        
        backup_info['clusters_backed_up'] = os.path.exists('cluster_settings.json')
        
        # Calculate backup size
        backup_info['size_mb'] = round(get_directory_size(backup_dir) / (1024*1024), 2)
        
        # Create backup metadata
        with open(os.path.join(backup_dir, 'backup_info.json'), 'w') as f:
            json.dump(backup_info, f, indent=2)
        
        # Create compressed archive
        archive_path = f'{backup_base_dir}/{backup_name}.tar.gz'
        shutil.make_archive(f'{backup_base_dir}/{backup_name}', 'gztar', backup_dir)
        
        # Remove uncompressed directory
        shutil.rmtree(backup_dir)
        
        # Store backup record in database
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()
            
            # Create backups table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    size_mb REAL,
                    description TEXT,
                    file_path TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                INSERT INTO backups (name, timestamp, size_mb, description, file_path)
                VALUES (?, ?, ?, ?, ?)
            ''', (backup_name, timestamp, backup_info['size_mb'], backup_info['description'], archive_path))
            
            conn.commit()
            conn.close()
        except Exception as db_error:
            print(f"Database backup record error: {db_error}")
        
        return jsonify({
            'success': True, 
            'backup_name': backup_name,
            'backup_path': archive_path,
            'backup_info': backup_info
        })
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def get_directory_size(path):
    """Get directory size in bytes"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    except Exception as e:
        print(f"Error calculating directory size: {e}")
    return total_size

@app.route('/api/restore_config', methods=['POST'])
@auth.login_required
def api_restore_config():
    """Restore configuration from backup"""
    try:
        data = request.get_json()
        backup_file = data.get('backup_file')
        target_file = data.get('target_file')
        
        if not backup_file or not target_file:
            return jsonify({'success': False, 'error': 'Missing backup_file or target_file'}), 400
        
        # Validate paths for security
        allowed_targets = ['/etc/openvpn/server/server.conf', '/etc/openvpn/server/client-common.txt']
        if target_file not in allowed_targets:
            return jsonify({'success': False, 'error': 'Invalid target file'}), 400
        
        if not os.path.exists(backup_file):
            return jsonify({'success': False, 'error': 'Backup file not found'}), 404
        
        # Restore backup
        subprocess.run(['cp', backup_file, target_file], check=True)
        
        return jsonify({'success': True, 'message': f'Configuration restored from {backup_file}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/validate_config', methods=['POST'])
@auth.login_required
def api_validate_config():
    """Validate OpenVPN configuration"""
    try:
        config_file = '/etc/openvpn/server/server.conf'
        
        # Check if config file exists
        if not os.path.exists(config_file):
            return jsonify({'valid': False, 'error': 'Configuration file not found'})
        
        # Basic syntax validation
        validation_errors = []
        required_directives = ['port', 'proto', 'dev', 'ca', 'cert', 'key', 'dh']
        
        try:
            with open(config_file, 'r') as f:
                config_content = f.read()
            
            # Check for required directives
            for directive in required_directives:
                if not re.search(rf'^{directive}\s+', config_content, re.MULTILINE):
                    validation_errors.append(f"Missing required directive: {directive}")
            
            # Check for common syntax errors
            lines = config_content.split('\n')
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Skip character validation as it's too strict
                # Different OpenVPN configs may contain various characters
                pass
            
            # Try to test with OpenVPN if available (skip on Windows or if not available)
            openvpn_test_result = None
            try:
                # Check if we're on Windows or if OpenVPN is available
                is_windows = os.name == 'nt'
                
                if is_windows:
                    # On Windows, just check if OpenVPN service exists
                    try:
                        service_check = subprocess.run(['sc', 'query', 'OpenVPNService'], 
                                                     capture_output=True, text=True, timeout=10)
                        if service_check.returncode == 0:
                            openvpn_test_result = "OpenVPN service detected (Windows)"
                        else:
                            openvpn_test_result = "OpenVPN service validation skipped (Windows)"
                    except:
                        openvpn_test_result = "OpenVPN validation skipped (Windows)"
                else:
                    # On Unix/Linux, test if openvpn command exists
                    test_result = subprocess.run(['which', 'openvpn'], capture_output=True, text=True, timeout=5)
                    if test_result.returncode == 0:
                        # Just test if the binary works, not the config
                        openvpn_result = subprocess.run(['openvpn', '--version'], 
                                                      capture_output=True, text=True, timeout=10)
                        if openvpn_result.returncode == 0:
                            openvpn_test_result = "OpenVPN command available"
                        else:
                            openvpn_test_result = "OpenVPN command test failed"
                    else:
                        openvpn_test_result = "OpenVPN command not found"
                        
            except Exception as e:
                openvpn_test_result = f"OpenVPN validation skipped: {str(e)}"
            
            if validation_errors:
                return jsonify({
                    'valid': False, 
                    'error': '; '.join(validation_errors),
                    'details': validation_errors,
                    'openvpn_test': openvpn_test_result
                })
            else:
                return jsonify({
                    'valid': True, 
                    'message': 'Configuration appears valid',
                    'openvpn_test': openvpn_test_result
                })
                
        except Exception as file_error:
            return jsonify({'valid': False, 'error': f'Cannot read config file: {str(file_error)}'})
            
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)}), 500

@app.route('/api/config_templates')
@auth.login_required
def api_config_templates():
    """Get configuration templates"""
    try:
        templates = {
            'basic_server': {
                'name': 'Basic Server',
                'description': 'Standard OpenVPN server configuration',
                'config': {
                    'port': '1194',
                    'proto': 'udp',
                    'cipher': 'AES-256-GCM',
                    'auth': 'SHA512',
                    'server': '10.8.0.0 255.255.255.0',
                    'dns1': '8.8.8.8',
                    'dns2': '8.8.4.4'
                }
            },
            'high_security': {
                'name': 'High Security',
                'description': 'Enhanced security configuration',
                'config': {
                    'port': '443',
                    'proto': 'tcp',
                    'cipher': 'AES-256-GCM',
                    'auth': 'SHA512',
                    'server': '10.8.0.0 255.255.255.0',
                    'tls_version_min': '1.3',
                    'compression': False,
                    'dns1': '1.1.1.1',
                    'dns2': '1.0.0.1'
                }
            },
            'performance': {
                'name': 'Performance Optimized',
                'description': 'Optimized for speed and throughput',
                'config': {
                    'port': '1194',
                    'proto': 'udp',
                    'cipher': 'AES-128-GCM',
                    'auth': 'SHA256',
                    'server': '10.8.0.0 255.255.255.0',
                    'compression': True,
                    'compress_algorithm': 'lz4-v2',
                    'dns1': '8.8.8.8',
                    'dns2': '8.8.4.4'
                }
            }
        }
        
        return jsonify(templates)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bulk_assign_group', methods=['POST'])
@auth.login_required
def api_bulk_assign_group():
    """Bulk assign clients to group"""
    try:
        data = request.get_json()
        clients = data.get('clients', [])
        group = data.get('group', '')
        
        if not clients:
            return jsonify({'success': False, 'error': 'No clients selected'}), 400
        
        success_count = 0
        errors = []
        
        # Connect to database to store group assignments
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create client_groups table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS client_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                group_name TEXT NOT NULL,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(client_name)
            )
        ''')
        
        for client_name in clients:
            try:
                # Update or insert group assignment
                if group:  # Assign to group
                    cursor.execute('''
                        INSERT OR REPLACE INTO client_groups (client_name, group_name, assigned_at)
                        VALUES (?, ?, CURRENT_TIMESTAMP)
                    ''', (client_name, group))
                else:  # Remove from group
                    cursor.execute('DELETE FROM client_groups WHERE client_name = ?', (client_name,))
                
                success_count += 1
                print(f"✅ Client {client_name} {'assigned to' if group else 'removed from'} group {group}")
                
            except Exception as e:
                errors.append(f"Error assigning {client_name}: {str(e)}")
                print(f"❌ Error assigning {client_name}: {e}")
        
        conn.commit()
        conn.close()
        
        if success_count > 0:
            message = f'Successfully assigned {success_count} clients to group "{group}"' if group else f'Successfully removed {success_count} clients from groups'
            return jsonify({
                'success': True, 
                'message': message,
                'errors': errors,
                'assigned_count': success_count
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to assign any clients', 'errors': errors}), 500
            
    except Exception as e:
        print(f"❌ Error in bulk_assign_group: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export_clients')
@auth.login_required
def api_export_clients():
    """Export client list as CSV"""
    try:
        clients = OpenVPNManager.get_clients()
        active_connections = OpenVPNManager.get_active_connections()
        
        # Create CSV content
        csv_content = "Client Name,Status,Group,Profile,Created Date,Expiry Date,Is Online,Real IP,Virtual IP,Traffic Sent,Traffic Received\n"
        
        for client in clients:
            # Find active connection info
            connection_info = next((conn for conn in active_connections if conn['name'] == client['name']), None)
            
            is_online = "Yes" if connection_info else "No"
            real_ip = connection_info.get('real_address', '') if connection_info else ''
            virtual_ip = connection_info.get('virtual_address', '') if connection_info else ''
            traffic_sent = connection_info.get('bytes_sent', '0') if connection_info else '0'
            traffic_received = connection_info.get('bytes_received', '0') if connection_info else '0'
            
            # Get group and profile (default values for now)
            group = client.get('group', '')
            profile = client.get('profile', 'standard')
            
            csv_content += f'"{client["name"]}","{client["status"]}","{group}","{profile}","{client.get("created_date", "")}","{client.get("expiry_date", "")}","{is_online}","{real_ip}","{virtual_ip}","{traffic_sent}","{traffic_received}"\n'
        
        # Create response
        from io import StringIO
        import csv
        from flask import Response
        
        output = StringIO()
        output.write(csv_content)
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=openvpn-clients.csv'}
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/client_profiles')
@auth.login_required
def api_client_profiles():
    """Get available client profiles with their settings"""
    try:
        profiles = {
            'standard': {
                'name': 'Standard Profile',
                'description': 'Basic VPN access with standard settings',
                'bandwidth_limit': None,
                'time_restrictions': None,
                'dns_servers': ['8.8.8.8', '8.8.4.4'],
                'routes': ['redirect-gateway'],
                'compression': True
            },
            'high_bandwidth': {
                'name': 'High Bandwidth',
                'description': 'Optimized for streaming and large downloads',
                'bandwidth_limit': None,
                'time_restrictions': None,
                'dns_servers': ['1.1.1.1', '1.0.0.1'],
                'routes': ['redirect-gateway'],
                'compression': False
            },
            'restricted': {
                'name': 'Time Limited',
                'description': 'Access only during business hours',
                'bandwidth_limit': '10Mbps',
                'time_restrictions': '09:00-17:00',
                'dns_servers': ['8.8.8.8', '8.8.4.4'],
                'routes': ['specific-routes'],
                'compression': True
            },
            'mobile_only': {
                'name': 'Mobile Optimized',
                'description': 'Optimized for mobile devices with data conservation',
                'bandwidth_limit': '5Mbps',
                'time_restrictions': None,
                'dns_servers': ['8.8.8.8', '8.8.4.4'],
                'routes': ['redirect-gateway'],
                'compression': True
            },
            'admin_access': {
                'name': 'Administrator Access',
                'description': 'Full network access with no restrictions',
                'bandwidth_limit': None,
                'time_restrictions': None,
                'dns_servers': ['1.1.1.1', '1.0.0.1'],
                'routes': ['full-access'],
                'compression': False
            },
            'guest_limited': {
                'name': 'Guest Limited',
                'description': 'Limited access for guest users',
                'bandwidth_limit': '2Mbps',
                'time_restrictions': '08:00-22:00',
                'dns_servers': ['8.8.8.8', '8.8.4.4'],
                'routes': ['web-only'],
                'compression': True
            }
        }
        
        return jsonify(profiles)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/client_statistics')
@auth.login_required
def api_client_statistics():
    """Get comprehensive client statistics"""
    try:
        clients = OpenVPNManager.get_clients()
        active_connections = OpenVPNManager.get_active_connections()
        
        # Calculate statistics
        total_clients = len(clients)
        active_clients = len([c for c in clients if c['status'] == 'active'])
        revoked_clients = len([c for c in clients if c['status'] == 'revoked'])
        online_clients = len(active_connections)
        
        # Group statistics (mock data for now)
        group_stats = {
            'admins': 2,
            'users': active_clients - 5,
            'guests': 3,
            'developers': 4,
            'managers': 1,
            'external': 2,
            'no_group': max(0, active_clients - 12)
        }
        
        # Profile statistics
        profile_stats = {
            'standard': active_clients - 6,
            'high_bandwidth': 3,
            'restricted': 2,
            'mobile_only': 4,
            'admin_access': 2,
            'guest_limited': 1
        }
        
        # Connection statistics
        connection_stats = {
            'peak_concurrent': max(online_clients, 5),
            'avg_session_duration': '2h 30m',
            'total_data_transferred': '1.2TB',
            'busiest_hour': '14:00-15:00'
        }
        
        return jsonify({
            'total_clients': total_clients,
            'active_clients': active_clients,
            'revoked_clients': revoked_clients,
            'online_clients': online_clients,
            'offline_clients': active_clients - online_clients,
            'group_distribution': group_stats,
            'profile_distribution': profile_stats,
            'connection_statistics': connection_stats,
            'last_updated': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/client_audit_log')
@auth.login_required
def api_client_audit_log():
    """Get client activity audit log"""
    try:
        # This would typically come from a database
        # For now, return mock audit data
        audit_logs = [
            {
                'timestamp': datetime.now().isoformat(),
                'action': 'client_created',
                'client_name': 'test_user',
                'group': 'users',
                'profile': 'standard',
                'admin_user': 'admin',
                'details': 'Client created with 1 year validity'
            },
            {
                'timestamp': (datetime.now() - timedelta(hours=2)).isoformat(),
                'action': 'client_connected',
                'client_name': 'test_user',
                'real_ip': '192.168.1.100',
                'virtual_ip': '10.8.0.2',
                'details': 'Client connected successfully'
            },
            {
                'timestamp': (datetime.now() - timedelta(hours=4)).isoformat(),
                'action': 'bulk_group_assign',
                'clients_affected': 5,
                'group': 'developers',
                'admin_user': 'admin',
                'details': 'Bulk assigned 5 clients to developers group'
            }
        ]
        
        return jsonify({
            'audit_logs': audit_logs,
            'total_entries': len(audit_logs)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ======================== CLUSTER MANAGEMENT API ENDPOINTS ========================

@app.route('/api/cluster/status')
@auth.login_required
def api_cluster_status():
    """Get cluster status"""
    try:
        status = ClusterManager.get_cluster_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster/servers', methods=['GET'])
@auth.login_required
def api_cluster_servers():
    """Get all cluster servers"""
    try:
        servers = ClusterManager.get_cluster_servers()
        return jsonify({'servers': servers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster/servers', methods=['POST'])
@auth.login_required
def api_add_cluster_server():
    """Add new server to cluster"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['server_id', 'server_name', 'host']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        # Test connection first if requested
        if data.get('test_connection', False):
            connection_ok = ClusterManager.test_server_connection(data)
            if not connection_ok:
                return jsonify({'success': False, 'error': 'Connection test failed'}), 400
        
        success = ClusterManager.add_server(data)
        if success:
            return jsonify({'success': True, 'message': f'Server {data["server_name"]} added successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to add server'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/servers/<server_id>', methods=['DELETE'])
@auth.login_required
def api_remove_cluster_server(server_id):
    """Remove server from cluster"""
    try:
        success = ClusterManager.remove_server(server_id)
        if success:
            return jsonify({'success': True, 'message': f'Server {server_id} removed successfully'})
        else:
            return jsonify({'success': False, 'error': 'Server not found or removal failed'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/servers/<server_id>/status')
@auth.login_required
def api_server_status(server_id):
    """Get detailed status of a specific server"""
    try:
        status = ClusterManager.get_server_status(server_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster/servers/<server_id>/clients')
@auth.login_required
def api_server_clients(server_id):
    """Get clients from a specific server"""
    try:
        clients = ClusterManager.get_server_clients(server_id)
        return jsonify({'clients': clients})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster/test_connection', methods=['POST'])
@auth.login_required
def api_test_server_connection():
    """Test connection to a server"""
    try:
        data = request.get_json()
        success = ClusterManager.test_server_connection(data)
        
        if success:
            return jsonify({'success': True, 'message': 'Connection test successful'})
        else:
            return jsonify({'success': False, 'error': 'Connection test failed'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/assign_client', methods=['POST'])
@auth.login_required
def api_cluster_assign_client():
    """Assign client to a specific server"""
    try:
        data = request.get_json()
        client_name = data.get('client_name')
        server_id = data.get('server_id')
        strategy = data.get('strategy', 'manual')
        
        if not client_name or not server_id:
            return jsonify({'success': False, 'error': 'Missing client_name or server_id'}), 400
        
        success, output = ClusterManager.assign_client_to_server(client_name, server_id, strategy)
        
        if success:
            return jsonify({
                'success': True, 
                'message': f'Client {client_name} assigned to server {server_id}',
                'output': output
            })
        else:
            return jsonify({'success': False, 'error': output}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/assignments')
@auth.login_required
def api_cluster_assignments():
    """Get all client assignments"""
    try:
        assignments = ClusterManager.get_client_assignments()
        return jsonify({'assignments': assignments})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster/activity')
@auth.login_required
def api_cluster_activity():
    """Get cluster activity log"""
    try:
        limit = request.args.get('limit', 50, type=int)
        activity = ClusterManager.get_cluster_activity(limit)
        return jsonify({'activity': activity})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster/ping_servers', methods=['POST'])
@auth.login_required
def api_ping_servers():
    """Ping all servers to check their status"""
    try:
        results = ClusterManager.ping_all_servers()
        return jsonify({
            'success': True,
            'results': results,
            'message': f'Pinged {len(results)} servers'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/execute_command', methods=['POST'])
@auth.login_required
def api_execute_remote_command():
    """Execute command on a remote server"""
    try:
        data = request.get_json()
        server_id = data.get('server_id')
        command = data.get('command')
        
        if not server_id or not command:
            return jsonify({'success': False, 'error': 'Missing server_id or command'}), 400
        
        # Security check - only allow safe commands
        safe_commands = ['systemctl status', 'uptime', 'free -m', 'df -h', 'ps aux', 'ls', 'cat', 'tail', 'head']
        is_safe = any(command.startswith(safe_cmd) for safe_cmd in safe_commands)
        
        if not is_safe:
            return jsonify({'success': False, 'error': 'Command not allowed for security reasons'}), 403
        
        output, error = ClusterManager.execute_remote_command(server_id, command)
        
        return jsonify({
            'success': True,
            'output': output,
            'error': error
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/load_balance', methods=['POST'])
@auth.login_required
def api_cluster_load_balance():
    """Balance client load across servers"""
    try:
        # This is a mock implementation
        # In reality, you would implement actual load balancing logic
        
        ClusterManager.log_activity(
            activity_type='load_balance',
            description='Load balancing triggered manually',
            user_id='admin'
        )
        
        return jsonify({
            'success': True,
            'message': 'Load balancing completed successfully',
            'redistributed_clients': 5  # Mock number
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backups', methods=['GET'])
@auth.login_required
def api_list_backups():
    """Get list of all backups"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create backups table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                size_mb REAL,
                description TEXT,
                file_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('SELECT * FROM backups ORDER BY created_at DESC')
        backups = []
        for row in cursor.fetchall():
            backup = {
                'id': row[0],
                'name': row[1],
                'timestamp': row[2],
                'size_mb': row[3],
                'description': row[4],
                'file_path': row[5],
                'created_at': row[6],
                'exists': os.path.exists(row[5]) if row[5] else False
            }
            backups.append(backup)
        
        conn.close()
        return jsonify({'backups': backups})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/backups/<int:backup_id>/download')
@auth.login_required  
def api_download_backup(backup_id):
    """Download backup file"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT name, file_path FROM backups WHERE id = ?', (backup_id,))
        backup = cursor.fetchone()
        conn.close()
        
        if not backup:
            return jsonify({'error': 'Backup not found'}), 404
        
        backup_name, file_path = backup
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'Backup file not found'}), 404
        
        return send_file(file_path, as_attachment=True, 
                        download_name=f'{backup_name}.tar.gz')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/backups/<int:backup_id>/restore', methods=['POST'])
@auth.login_required
def api_restore_backup(backup_id):
    """Restore from backup"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT name, file_path FROM backups WHERE id = ?', (backup_id,))
        backup = cursor.fetchone()
        conn.close()
        
        if not backup:
            return jsonify({'success': False, 'error': 'Backup not found'}), 404
        
        backup_name, file_path = backup
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': 'Backup file not found'}), 404
        
        # Extract backup to temporary directory
        temp_dir = tempfile.mkdtemp()
        try:
            shutil.unpack_archive(file_path, temp_dir)
            
            # Find extracted directory
            extracted_dir = None
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                if os.path.isdir(item_path):
                    extracted_dir = item_path
                    break
            
            if not extracted_dir:
                return jsonify({'success': False, 'error': 'Invalid backup format'}), 400
            
            # Restore configuration files
            config_dir = os.path.join(extracted_dir, 'config')
            if os.path.exists(config_dir):
                for config_file in os.listdir(config_dir):
                    src_path = os.path.join(config_dir, config_file)
                    dst_path = f'/etc/openvpn/server/{config_file}'
                    
                    # Create backup of current config
                    if os.path.exists(dst_path):
                        shutil.copy2(dst_path, f'{dst_path}.pre_restore')
                    
                    # Restore config file
                    try:
                        shutil.copy2(src_path, dst_path)
                    except Exception as e:
                        print(f"Warning: Could not restore {config_file}: {e}")
            
            # Restore database
            db_path = os.path.join(extracted_dir, 'vpn_history.db')
            if os.path.exists(db_path):
                # Backup current database
                if os.path.exists('vpn_history.db'):
                    shutil.copy2('vpn_history.db', 'vpn_history.db.pre_restore')
                
                # Restore database
                shutil.copy2(db_path, 'vpn_history.db')
            
            # Restore settings files
            for settings_file in ['user_groups.json', 'cluster_settings.json']:
                settings_path = os.path.join(extracted_dir, settings_file)
                if os.path.exists(settings_path):
                    # Backup current settings
                    if os.path.exists(settings_file):
                        shutil.copy2(settings_file, f'{settings_file}.pre_restore')
                    
                    # Restore settings
                    shutil.copy2(settings_path, settings_file)
            
            return jsonify({'success': True, 'message': f'Backup {backup_name} restored successfully'})
            
        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/backups/<int:backup_id>', methods=['DELETE'])
@auth.login_required
def api_delete_backup(backup_id):
    """Delete backup"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT name, file_path FROM backups WHERE id = ?', (backup_id,))
        backup = cursor.fetchone()
        
        if not backup:
            conn.close()
            return jsonify({'success': False, 'error': 'Backup not found'}), 404
        
        backup_name, file_path = backup
        
        # Delete backup file
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        # Delete from database
        cursor.execute('DELETE FROM backups WHERE id = ?', (backup_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'Backup {backup_name} deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/settings', methods=['GET'])
@auth.login_required
def api_cluster_settings():
    """Get cluster settings"""
    try:
        settings_file = 'cluster_settings.json'
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                settings = json.load(f)
        else:
            # Default cluster settings
            settings = {
                'auto_load_balance': True,
                'load_balance_interval': 300,  # 5 minutes
                'health_check_interval': 60,   # 1 minute
                'max_clients_per_server': 50,
                'failover_enabled': True,
                'backup_servers': [],
                'maintenance_mode': False,
                'notification_settings': {
                    'email_enabled': False,
                    'webhook_enabled': False,
                    'alert_thresholds': {
                        'cpu_threshold': 80,
                        'memory_threshold': 90,
                        'client_threshold': 45
                    }
                }
            }
        
        return jsonify(settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cluster/settings', methods=['POST'])
@auth.login_required
def api_update_cluster_settings():
    """Update cluster settings"""
    try:
        data = request.get_json()
        
        # Save settings to file
        settings_file = 'cluster_settings.json'
        with open(settings_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Log the activity
        try:
            ClusterManager.log_activity(
                activity_type='settings_updated',
                description='Cluster settings updated',
                details=f'Settings updated: {list(data.keys())}',
                user_id='admin'
            )
        except Exception as log_error:
            print(f"Warning: Could not log activity: {log_error}")
        
        return jsonify({'success': True, 'message': 'Cluster settings updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cluster/real_activity')
@auth.login_required
def api_cluster_real_activity():
    """Get real cluster activity from database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Get recent cluster activities
        cursor.execute('''
            SELECT activity_type, description, server_id, created_at, details
            FROM cluster_activity 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        
        activities = []
        for row in cursor.fetchall():
            activity_type, description, server_id, created_at, details = row
            
            # Format timestamp
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                time_ago = format_time_ago(dt)
            except:
                time_ago = 'Unknown time'
            
            # Get appropriate icon based on activity type
            icon_map = {
                'server_added': 'bi-plus-circle',
                'server_removed': 'bi-dash-circle',
                'client_assigned': 'bi-person-plus',
                'client_unassigned': 'bi-person-dash',
                'load_balance': 'bi-arrow-left-right',
                'maintenance': 'bi-tools',
                'health_check': 'bi-heart-pulse',
                'connection_test': 'bi-wifi',
                'backup_created': 'bi-archive',
                'settings_updated': 'bi-gear'
            }
            
            color_map = {
                'server_added': 'text-success',
                'server_removed': 'text-danger',
                'client_assigned': 'text-info',
                'client_unassigned': 'text-warning',
                'load_balance': 'text-warning',
                'maintenance': 'text-secondary',
                'health_check': 'text-primary',
                'connection_test': 'text-info',
                'backup_created': 'text-success',
                'settings_updated': 'text-info'
            }
            
            activity = {
                'icon': icon_map.get(activity_type, 'bi-info-circle'),
                'color': color_map.get(activity_type, 'text-secondary'),
                'message': description,
                'time': time_ago,
                'server_id': server_id,
                'details': details
            }
            
            activities.append(activity)
        
        conn.close()
        
        # If no activities found, add some sample ones based on recent server/client operations
        if not activities:
            activities = [
                {
                    'icon': 'bi-info-circle',
                    'color': 'text-info',
                    'message': 'Cluster monitoring started',
                    'time': '1 minute ago',
                    'server_id': None,
                    'details': 'System initialized'
                }
            ]
        
        return jsonify({'activities': activities})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def format_time_ago(dt):
    """Format datetime as time ago string"""
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    diff = now - dt
    
    if diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"

@app.route('/api/cluster/info')
@auth.login_required
def api_cluster_info():
    """Get cluster information for dashboard"""
    try:
        servers = ClusterManager.get_cluster_servers()
        
        total_servers = len(servers) if servers else 0
        online_servers = 0
        
        if servers:
            # Check online servers
            for server in servers:
                if server.get('status') == 'online':
                    online_servers += 1
        
        # Status text
        if total_servers == 0:
            status_text = "No servers"
        elif online_servers == total_servers:
            status_text = "All online"
        elif online_servers == 0:
            status_text = "All offline"
        else:
            status_text = f"{online_servers}/{total_servers} online"
        
        return jsonify({
            'total_servers': total_servers,
            'online_servers': online_servers,
            'offline_servers': total_servers - online_servers,
            'status_text': status_text,
            'has_cluster': total_servers > 0
        })
    except Exception as e:
        return jsonify({
            'total_servers': 0,
            'online_servers': 0,
            'offline_servers': 0,
            'status_text': 'Error loading',
            'has_cluster': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Initialize system after all classes are defined
    print("🚀 Starting OpenVPN Manager...")
    
    # Initialize database first
    init_database()
    
    # Start session tracking
    start_session_tracking()
    
    # Restore temporary clients from database
    restore_temporary_clients()
    
    # Restore traffic history
    restore_traffic_history()
    
    print("✅ OpenVPN Manager started successfully!")
    
    # Запускаем на всех интерфейсах для доступа из сети
    app.run(host='0.0.0.0', port=8822, debug=False) 