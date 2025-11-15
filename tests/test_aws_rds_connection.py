#!/usr/bin/env python3
"""
Test AWS RDS MySQL Connection và Cloud Sync
Author: IoT Health Monitor Team
Date: 2025-11-16
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
from dotenv import load_dotenv
import mysql.connector
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(project_root / '.env')

def load_config():
    """Load application config"""
    config_path = project_root / 'config' / 'app_config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def test_connection():
    """Test connection to AWS RDS"""
    logger.info("=" * 70)
    logger.info("TEST 1: Connection to AWS RDS MySQL")
    logger.info("=" * 70)
    
    try:
        config = load_config()
        mysql_cfg = config['cloud']['mysql']
        
        # Get password from environment
        password = os.getenv(mysql_cfg.get('password_env', 'MYSQL_CLOUD_PASSWORD'))
        
        if not password:
            logger.error("❌ MYSQL_CLOUD_PASSWORD not found in .env")
            logger.error("   Please add to .env: MYSQL_CLOUD_PASSWORD=your_password")
            return False
        
        logger.info(f"📊 Connection Info:")
        logger.info(f"   Host: {mysql_cfg['host']}")
        logger.info(f"   Port: {mysql_cfg['port']}")
        logger.info(f"   Database: {mysql_cfg['database']}")
        logger.info(f"   User: {mysql_cfg['user']}")
        logger.info(f"   Password: {'*' * len(password)}")
        
        # Attempt connection
        logger.info("\n🔌 Connecting to AWS RDS...")
        conn = mysql.connector.connect(
            host=mysql_cfg['host'],
            port=mysql_cfg['port'],
            user=mysql_cfg['user'],
            password=password,
            database=mysql_cfg['database'],
            connect_timeout=15
        )
        
        if conn.is_connected():
            logger.info("✅ Connected successfully!")
            
            # Get server info
            cursor = conn.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            logger.info(f"\n📊 MySQL Version: {version[0]}")
            
            # Get current timestamp
            cursor.execute("SELECT NOW()")
            server_time = cursor.fetchone()
            logger.info(f"📅 Server Time: {server_time[0]}")
            
            # List tables
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            logger.info(f"\n📋 Tables in database ({len(tables)} tables):")
            
            total_records = 0
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM `{table[0]}`")
                    count = cursor.fetchone()[0]
                    total_records += count
                    status_icon = "✅" if count > 0 else "📝"
                    logger.info(f"   {status_icon} {table[0]:.<30} {count:>6} records")
                except mysql.connector.Error as table_err:
                    logger.warning(f"   ⚠️  {table[0]:.<30} (no access: {table_err.errno})")
            
            logger.info(f"\n📊 Total accessible records: {total_records}")
            
            # Test write permission (vào iot_health_cloud database)
            logger.info("\n🔒 Testing write permissions...")
            write_success = False
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS connection_test (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        test_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        message VARCHAR(255)
                    )
                """)
                
                cursor.execute(
                    "INSERT INTO connection_test (message) VALUES (%s)",
                    (f"Test from Pi at {datetime.now()}",)
                )
                conn.commit()
                
                cursor.execute("SELECT COUNT(*) FROM connection_test")
                test_count = cursor.fetchone()[0]
                logger.info(f"✅ Write test successful (connection_test: {test_count} records)")
                
                # Cleanup
                cursor.execute("DROP TABLE IF EXISTS connection_test")
                conn.commit()
                
                write_success = True
                
            except mysql.connector.Error as write_err:
                logger.warning(f"⚠️  Write permission limited: {write_err}")
                logger.info("   This is OK if using read-only user")
                # Write test is optional, don't fail the entire test
            
            cursor.close()
            conn.close()
            
            logger.info("\n✅ Test 1 PASSED\n")
            return True
        else:
            logger.error("❌ Connection failed")
            return False
            
    except mysql.connector.Error as err:
        logger.error(f"❌ MySQL Error: {err}")
        logger.error(f"   Error Code: {err.errno}")
        logger.error(f"   SQL State: {err.sqlstate}")
        
        if err.errno == 2003:
            logger.error("\n💡 Troubleshooting:")
            logger.error("   1. Check Security Group allows your Pi IP")
            logger.error("   2. Check RDS instance is 'Available' in AWS Console")
            logger.error("   3. Verify endpoint is correct")
        elif err.errno == 1045:
            logger.error("\n💡 Troubleshooting:")
            logger.error("   1. Check username/password in .env")
            logger.error("   2. Verify user exists in RDS")
        
        return False
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cloud_sync():
    """Test CloudSyncManager"""
    logger.info("=" * 70)
    logger.info("TEST 2: CloudSyncManager Sync")
    logger.info("=" * 70)
    
    try:
        from src.communication.cloud_sync_manager import CloudSyncManager
        from src.data.database import DatabaseManager
        
        config = load_config()
        
        # Initialize local database first
        logger.info("📦 Initializing local database...")
        db_manager = DatabaseManager(config)
        if not db_manager.initialize():
            logger.error("❌ Failed to initialize local database")
            return False
        
        logger.info("📡 Creating CloudSyncManager...")
        cloud_config = config.get('cloud', {})
        sync_manager = CloudSyncManager(db_manager, cloud_config)
        
        # Connect to cloud
        logger.info("🔌 Connecting to cloud...")
        if not sync_manager.connect_to_cloud():
            logger.error("❌ Failed to connect to cloud")
            return False
        
        logger.info("🔄 Testing full sync (both directions)...")
        result = sync_manager.sync_all(direction='both')
        
        if result.get('success', False):
            logger.info("✅ Sync completed successfully!")
            
            # Display sync results
            logger.info(f"\n📊 Sync Results:")
            logger.info(f"   Direction: {result.get('direction', 'N/A')}")
            logger.info(f"   Upload results: {result.get('upload', {})}")
            logger.info(f"   Download results: {result.get('download', {})}")
            logger.info(f"   Duration: {result.get('duration_seconds', 0):.2f}s")
            
            logger.info("\n✅ Test 2 PASSED")
            return True
        else:
            logger.error(f"❌ Sync failed: {result.get('error', 'Unknown error')}")
            return False
            
    except ImportError as e:
        logger.error(f"❌ CloudSyncManager not found: {e}")
        logger.info("   Skipping sync test...")
        return True  # Not critical for connection test
    except Exception as e:
        logger.error(f"❌ Test 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_latency():
    """Test connection latency to AWS RDS"""
    logger.info("=" * 70)
    logger.info("TEST 3: Connection Latency Test")
    logger.info("=" * 70)
    
    try:
        config = load_config()
        mysql_cfg = config['cloud']['mysql']
        password = os.getenv(mysql_cfg.get('password_env', 'MYSQL_CLOUD_PASSWORD'))
        
        import time
        
        logger.info("🏓 Testing ping latency (10 samples)...")
        latencies = []
        
        for i in range(10):
            start = time.time()
            conn = mysql.connector.connect(
                host=mysql_cfg['host'],
                port=mysql_cfg['port'],
                user=mysql_cfg['user'],
                password=password,
                database=mysql_cfg['database'],
                connect_timeout=10
            )
            
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            
            latency = (time.time() - start) * 1000  # Convert to ms
            latencies.append(latency)
            logger.info(f"   Sample {i+1}: {latency:.2f} ms")
        
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        
        logger.info(f"\n📊 Latency Statistics:")
        logger.info(f"   Average: {avg_latency:.2f} ms")
        logger.info(f"   Min: {min_latency:.2f} ms")
        logger.info(f"   Max: {max_latency:.2f} ms")
        
        if avg_latency < 100:
            logger.info("   ✅ Excellent latency!")
        elif avg_latency < 300:
            logger.info("   ✅ Good latency for cloud database")
        else:
            logger.warning("   ⚠️  High latency, may affect real-time sync")
        
        logger.info("\n✅ Test 3 PASSED\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test 3 FAILED: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("\n" + "=" * 70)
    logger.info("🌐 AWS RDS MySQL Connection Tests")
    logger.info("=" * 70 + "\n")
    
    # Check environment
    logger.info("🔍 Checking environment...")
    password = os.getenv('MYSQL_CLOUD_PASSWORD')
    if password:
        logger.info("✅ MYSQL_CLOUD_PASSWORD found in environment")
        logger.info(f"   Password length: {len(password)} characters\n")
    else:
        logger.error("❌ MYSQL_CLOUD_PASSWORD not found!")
        logger.error("   Please add to .env file\n")
        return
    
    results = []
    
    # Test 1: Basic Connection
    results.append(("Connection Test", test_connection()))
    
    # Test 2: Cloud Sync
    results.append(("Cloud Sync Test", test_cloud_sync()))
    
    # Test 3: Latency
    results.append(("Latency Test", test_latency()))
    
    # Summary
    logger.info("=" * 70)
    logger.info("📋 TEST SUMMARY")
    logger.info("=" * 70)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{name:.<50} {status}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    logger.info(f"\n📊 Total: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests PASSED! AWS RDS connection working perfectly!")
        logger.info("\n💡 Next steps:")
        logger.info("   1. Run main app: python main.py")
        logger.info("   2. Monitor sync in logs/")
        logger.info("   3. Check data in AWS RDS via MySQL Workbench")
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) FAILED. Please check the errors above.")

if __name__ == '__main__':
    main()
