#!/usr/bin/env python3
"""
Database Diagnosis Script for OpenVPN Manager
Checks if data is being written to database correctly
"""

import sqlite3
import os
from datetime import datetime

DATABASE_PATH = 'vpn_history.db'

def check_database():
    """Check database status and content"""
    print("🔍 OpenVPN Manager Database Diagnosis")
    print("=" * 50)
    
    # Check if database file exists
    if not os.path.exists(DATABASE_PATH):
        print("❌ Database file does not exist!")
        return
    
    file_size = os.path.getsize(DATABASE_PATH)
    print(f"📁 Database file: {DATABASE_PATH}")
    print(f"📊 File size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"\n📋 Tables found: {len(tables)}")
        for table in tables:
            print(f"  • {table[0]}")
        
        # Check traffic_history table
        print("\n📈 Traffic History Analysis:")
        cursor.execute('SELECT COUNT(*) FROM traffic_history')
        total_records = cursor.fetchone()[0]
        print(f"  Total records: {total_records}")
        
        if total_records > 0:
            # Get unique clients
            cursor.execute('SELECT COUNT(DISTINCT client_name) FROM traffic_history')
            unique_clients = cursor.fetchone()[0]
            print(f"  Unique clients: {unique_clients}")
            
            # Get total traffic
            cursor.execute('SELECT SUM(bytes_sent + bytes_received) FROM traffic_history')
            total_traffic = cursor.fetchone()[0] or 0
            print(f"  Total traffic: {total_traffic/1024/1024:.2f} MB")
            
            # Get recent records
            print("\n📅 Recent Records (last 5):")
            cursor.execute('''
                SELECT client_name, bytes_sent, bytes_received, timestamp 
                FROM traffic_history 
                ORDER BY timestamp DESC 
                LIMIT 5
            ''')
            
            for record in cursor.fetchall():
                client, sent, received, timestamp = record
                print(f"  • {client}: {sent/1024/1024:.2f}MB↑ {received/1024/1024:.2f}MB↓ at {timestamp}")
        
        # Check temporary_clients table
        print("\n⏰ Temporary Clients:")
        cursor.execute('SELECT COUNT(*) FROM temporary_clients')
        temp_count = cursor.fetchone()[0]
        print(f"  Total temporary clients: {temp_count}")
        
        if temp_count > 0:
            cursor.execute('SELECT client_name, status, revoke_at FROM temporary_clients ORDER BY created_at DESC LIMIT 3')
            for record in cursor.fetchall():
                client, status, revoke_at = record
                print(f"  • {client}: {status} (revoke: {revoke_at})")
        
        # Check system_metrics table
        print("\n📊 System Metrics:")
        cursor.execute('SELECT COUNT(*) FROM system_metrics')
        metrics_count = cursor.fetchone()[0]
        print(f"  Total metrics records: {metrics_count}")
        
        if metrics_count > 0:
            cursor.execute('SELECT cpu_percent, memory_percent, timestamp FROM system_metrics ORDER BY timestamp DESC LIMIT 1')
            record = cursor.fetchone()
            if record:
                cpu, memory, timestamp = record
                print(f"  Latest: CPU {cpu}%, RAM {memory}% at {timestamp}")
        
        conn.close()
        
        # Test write capability
        print("\n🔧 Testing Database Write...")
        test_write()
        
        print("\n✅ Database diagnosis completed!")
        
    except Exception as e:
        print(f"💥 Database error: {e}")
        import traceback
        traceback.print_exc()

def test_write():
    """Test if we can write to database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Try to insert test record
        test_client = f"test_write_{datetime.now().strftime('%H%M%S')}"
        cursor.execute('''
            INSERT INTO traffic_history 
            (client_name, bytes_sent, bytes_received, duration_seconds)
            VALUES (?, ?, ?, ?)
        ''', (test_client, 1024, 2048, 30))
        
        conn.commit()
        
        # Verify it was inserted
        cursor.execute('SELECT COUNT(*) FROM traffic_history WHERE client_name = ?', (test_client,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            print("  ✅ Write test successful!")
            
            # Clean up test record
            cursor.execute('DELETE FROM traffic_history WHERE client_name = ?', (test_client,))
            conn.commit()
            print("  🧹 Test record cleaned up")
        else:
            print("  ❌ Write test failed - record not found")
        
        conn.close()
        
    except Exception as e:
        print(f"  💥 Write test error: {e}")

if __name__ == "__main__":
    check_database() 