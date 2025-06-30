#!/usr/bin/env python3
"""
Script for automatic checking and revocation of expired temporary OpenVPN clients
Used with cron for regular execution
"""

import os
import sys
import sqlite3
import subprocess
import re
import glob
from datetime import datetime, timedelta

# Configuration (adjust for your system)
DATABASE_PATH = 'vpn_history.db'  # Should match the database in app.py
EASYRSA_DIR = '/etc/openvpn/server/easy-rsa'
SCRIPT_PATH = '/opt/vpn/openvpn-install.sh'

def log_message(message):
    """Logging with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def check_expired_clients():
    """Check and revoke expired temporary clients"""
    try:
        # Connect to database
        if not os.path.exists(DATABASE_PATH):
            log_message("❌ Database not found")
            return
        
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Ensure required tables exist
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS client_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_name TEXT NOT NULL,
                    group_name TEXT NOT NULL,
                    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(client_name)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cluster_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT,
                    activity_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    details TEXT,
                    user_id TEXT DEFAULT 'system',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
        except Exception as e:
            log_message(f"Warning: Could not create tables: {e}")
        
        # Get expired clients
        current_time = datetime.now()
        cursor.execute('''
            SELECT client_name, revoke_at 
            FROM temporary_clients 
            WHERE status = 'active' AND revoke_at <= ?
        ''', (current_time.isoformat(),))
        
        expired_clients = cursor.fetchall()
        
        if not expired_clients:
            log_message("✅ No expired clients found")
            conn.close()
            return
        
        log_message(f"⚠️ Found {len(expired_clients)} expired clients")
        
        revoked_count = 0
        failed_count = 0
        
        # Revoke each expired client
        for client_name, revoke_at in expired_clients:
            try:
                log_message(f"🔄 Processing: {client_name} (expired: {revoke_at})")
                
                # Revoke via EasyRSA
                success = revoke_client_direct(client_name)
                
                if success:
                    # Update temporary clients status
                    cursor.execute('''
                        UPDATE temporary_clients 
                        SET status = 'revoked', revoked_at = ?
                        WHERE client_name = ?
                    ''', (current_time.isoformat(), client_name))
                    
                    # Update related database records
                    update_database_records(client_name, cursor)
                    
                    revoked_count += 1
                    log_message(f"✅ Client {client_name} successfully revoked")
                else:
                    failed_count += 1
                    log_message(f"❌ Failed to revoke client {client_name}")
                    
            except Exception as e:
                failed_count += 1
                log_message(f"💥 Error revoking {client_name}: {str(e)}")
        
        # Save all changes
        try:
            conn.commit()
            log_message(f"💾 Database changes committed")
        except Exception as e:
            log_message(f"❌ Error committing database changes: {e}")
            conn.rollback()
        
        conn.close()
        
        # Summary
        log_message(f"📊 Summary: {revoked_count} revoked, {failed_count} failed")
        
        if revoked_count > 0:
            log_message("🔄 OpenVPN will automatically apply CRL changes")
            
            # Optionally restart OpenVPN service for immediate effect
            # Uncomment the line below if you want to restart the service
            # restart_openvpn_service()
        
        log_message("✅ Check completed successfully")
        
    except Exception as e:
        log_message(f"💥 General error: {str(e)}")
        return

def revoke_client_direct(client_name):
    """Direct client revocation via EasyRSA with improved logging"""
    try:
        # Clean client name for security
        clean_name = re.sub(r'[^0-9a-zA-Z_-]', '_', client_name)
        
        # Change to EasyRSA directory
        old_cwd = os.getcwd()
        
        try:
            os.chdir(EASYRSA_DIR)
        except Exception as e:
            log_message(f"Cannot access EasyRSA directory: {e}")
            return False
        
        try:
            # Check if client certificate exists
            cert_path = f"pki/issued/{clean_name}.crt"
            if not os.path.exists(cert_path):
                log_message(f"Certificate for {clean_name} not found")
                return False
            
            # Revoke the certificate
            revoke_cmd = ['./easyrsa', '--batch', 'revoke', clean_name]
            log_message(f"Executing: {' '.join(revoke_cmd)}")
            
            result = subprocess.run(
                revoke_cmd,
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode != 0:
                # Check if already revoked
                if "Already revoked" in result.stderr or "already revoked" in result.stderr:
                    log_message(f"Certificate {clean_name} was already revoked")
                else:
                    log_message(f"Revocation failed: {result.stderr}")
                    return False
            
            # Generate updated CRL
            crl_cmd = ['./easyrsa', '--batch', '--days=3650', 'gen-crl']
            log_message("Generating new CRL...")
            
            result = subprocess.run(
                crl_cmd,
                capture_output=True, text=True, timeout=60
            )
            
            if result.returncode != 0:
                log_message(f"CRL generation failed: {result.stderr}")
                return False
            
            # Copy CRL to OpenVPN directory
            crl_source = "pki/crl.pem"
            crl_dest = "/etc/openvpn/server/crl.pem"
            
            if os.path.exists(crl_source):
                try:
                    subprocess.run(['cp', crl_source, crl_dest], check=True, timeout=30)
                    log_message("CRL copied to OpenVPN directory")
                    
                    # Set proper permissions
                    try:
                        subprocess.run(['chown', 'nobody:nogroup', crl_dest], timeout=10)
                        subprocess.run(['chmod', '644', crl_dest], timeout=10)
                    except subprocess.TimeoutExpired:
                        log_message("Warning: Timeout setting CRL permissions")
                    except Exception:
                        pass  # Continue even if permission setting fails
                        
                except subprocess.TimeoutExpired:
                    log_message("Error: Timeout copying CRL")
                    return False
                except Exception as e:
                    log_message(f"Error copying CRL: {e}")
                    return False
            else:
                log_message("Warning: CRL file not found after generation")
            
            # Remove client configuration files
            cleanup_client_files(clean_name)
            
            log_message(f"Client {clean_name} successfully revoked")
            return True
            
        finally:
            os.chdir(old_cwd)
            
    except Exception as e:
        log_message(f"Error in revoke_client_direct: {str(e)}")
        return False

def cleanup_client_files(client_name):
    """Clean up client files after revocation"""
    try:
        # Files to remove
        files_to_remove = [
            f"/root/{client_name}.ovpn",
            f"/home/*/Desktop/{client_name}.ovpn",
            f"/tmp/{client_name}.ovpn"
        ]
        
        # Certificate files in easy-rsa
        easyrsa_files = [
            f"{EASYRSA_DIR}/pki/private/{client_name}.key",
            f"{EASYRSA_DIR}/pki/issued/{client_name}.crt",
            f"{EASYRSA_DIR}/pki/reqs/{client_name}.req"
        ]
        
        files_to_remove.extend(easyrsa_files)
        
        removed_count = 0
        for file_path in files_to_remove:
            # Handle wildcard paths
            if '*' in file_path:
                try:
                    for match in glob.glob(file_path):
                        if os.path.exists(match):
                            os.remove(match)
                            removed_count += 1
                except:
                    pass
            else:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        removed_count += 1
                    except Exception as e:
                        log_message(f"Warning: Could not remove {file_path}: {e}")
        
        if removed_count > 0:
            log_message(f"Cleaned up {removed_count} client files")
            
    except Exception as e:
        log_message(f"Error during file cleanup: {e}")

def update_database_records(client_name, cursor):
    """Update database records after revocation"""
    try:
        current_time = datetime.now().isoformat()
        
        # Remove from client_groups table if exists
        try:
            cursor.execute('DELETE FROM client_groups WHERE client_name = ?', (client_name,))
            log_message(f"Removed {client_name} from client groups")
        except Exception as e:
            log_message(f"Warning: Could not update client_groups: {e}")
        
        # Log activity to cluster_activity table
        try:
            cursor.execute('''
                INSERT INTO cluster_activity (
                    activity_type, description, details, user_id, created_at
                ) VALUES (?, ?, ?, ?, ?)
            ''', (
                'client_revoked',
                f'Client {client_name} automatically revoked due to expiration',
                f'Expired client {client_name} revoked by automatic cleanup script',
                'system',
                current_time
            ))
            log_message(f"Logged revocation activity for {client_name}")
        except Exception as e:
            log_message(f"Warning: Could not log to cluster_activity: {e}")
        
    except Exception as e:
        log_message(f"Error updating database records: {e}")

def restart_openvpn_service():
    """Restart OpenVPN service"""
    try:
        result = subprocess.run(
            ['systemctl', 'restart', 'openvpn-server@server.service'],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode == 0:
            log_message("✅ OpenVPN service restarted")
            return True
        else:
            log_message(f"⚠️ Restart error: {result.stderr}")
            return False
            
    except Exception as e:
        log_message(f"💥 OpenVPN restart error: {str(e)}")
        return False

if __name__ == "__main__":
    # Check if running as root
    if os.geteuid() != 0:
        log_message("Script must be run as root user")
        sys.exit(1)
    
    log_message("=== Starting expired clients check ===")
    check_expired_clients()
    log_message("=== Check completed ===") 