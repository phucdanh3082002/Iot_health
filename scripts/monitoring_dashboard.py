#!/usr/bin/env python3
"""
Cloud Sync Monitoring Dashboard
Query và hiển thị metrics từ MySQL monitoring views
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import yaml
from datetime import datetime
from typing import Dict, Any, List
from tabulate import tabulate
from sqlalchemy import create_engine, text


class MonitoringDashboard:
    """
    Dashboard để monitor cloud sync và IoT health system
    """
    
    def __init__(self, cloud_config: Dict[str, Any]):
        """
        Initialize monitoring dashboard
        
        Args:
            cloud_config: Cloud configuration từ app_config.yaml
        """
        self.cloud_config = cloud_config
        self.engine = None
        self._connect()
    
    def _connect(self):
        """Connect to MySQL cloud database"""
        try:
            mysql_config = self.cloud_config.get('mysql', {})
            
            host = mysql_config.get('host', 'localhost')
            port = mysql_config.get('port', 3306)
            database = mysql_config.get('database', 'iot_health_cloud')
            user = mysql_config.get('user', 'root')
            
            # Get password
            password_env = mysql_config.get('password_env', 'MYSQL_CLOUD_PASSWORD')
            password = os.environ.get(password_env, mysql_config.get('password', ''))
            
            # Build connection URL
            connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            
            # Create engine
            self.engine = create_engine(
                connection_url,
                pool_pre_ping=True,
                connect_args={'server_public_key': None}
            )
            
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            print(f"✅ Connected to MySQL: {host}:{port}/{database}")
            
        except Exception as e:
            print(f"❌ Failed to connect to MySQL: {e}")
            raise
    
    def get_system_status(self) -> List[Dict]:
        """Get real-time system status"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM v_system_status"))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error getting system status: {e}")
            return []
    
    def get_device_health(self) -> List[Dict]:
        """Get device health status"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        device_id,
                        device_name,
                        location,
                        connection_status,
                        minutes_since_last_seen,
                        records_today,
                        records_24h,
                        alerts_today,
                        ROUND(avg_data_quality, 3) as avg_quality
                    FROM v_device_health
                """))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error getting device health: {e}")
            return []
    
    def get_sync_performance(self, hours: int = 24) -> List[Dict]:
        """Get sync performance metrics"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT 
                        device_id,
                        sync_date,
                        sync_hour,
                        total_records,
                        synced_count,
                        pending_count,
                        conflict_count,
                        success_rate_pct,
                        ROUND(avg_quality, 3) as avg_quality
                    FROM v_sync_performance
                    WHERE sync_date >= CURDATE() - INTERVAL {hours} HOUR
                    ORDER BY sync_date DESC, sync_hour DESC
                    LIMIT 20
                """))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error getting sync performance: {e}")
            return []
    
    def get_recent_errors(self, hours: int = 24) -> List[Dict]:
        """Get recent errors"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT 
                        error_date,
                        error_hour,
                        level,
                        module,
                        device_id,
                        error_count,
                        unique_errors
                    FROM v_error_dashboard
                    WHERE error_date >= CURDATE() - INTERVAL {hours} HOUR
                    ORDER BY error_date DESC, error_hour DESC, error_count DESC
                    LIMIT 20
                """))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error getting recent errors: {e}")
            return []
    
    def get_active_alerts(self) -> List[Dict]:
        """Get active alerts summary"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT 
                        alert_date,
                        severity,
                        vital_sign,
                        device_id,
                        total_alerts,
                        unacknowledged,
                        unresolved,
                        ROUND(avg_response_minutes, 1) as avg_response_min
                    FROM v_alert_summary
                    WHERE alert_date >= CURDATE() - INTERVAL 1 DAY
                    ORDER BY alert_date DESC, 
                             FIELD(severity, 'critical', 'high', 'medium', 'low')
                    LIMIT 20
                """))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error getting active alerts: {e}")
            return []
    
    def get_data_quality(self, days: int = 7) -> List[Dict]:
        """Get data quality metrics"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT 
                        device_id,
                        measurement_date,
                        total_measurements,
                        ROUND(avg_quality, 3) as avg_quality,
                        excellent_count,
                        good_count,
                        fair_count,
                        poor_count,
                        completeness_pct
                    FROM v_data_quality
                    WHERE measurement_date >= CURDATE() - INTERVAL {days} DAY
                    ORDER BY measurement_date DESC, device_id
                    LIMIT 20
                """))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error getting data quality: {e}")
            return []
    
    def get_daily_summary(self, days: int = 7) -> List[Dict]:
        """Get daily summary"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"""
                    SELECT * FROM v_daily_summary
                    WHERE summary_date >= CURDATE() - INTERVAL {days} DAY
                    ORDER BY summary_date DESC
                """))
                return [dict(row._mapping) for row in result]
        except Exception as e:
            print(f"Error getting daily summary: {e}")
            return []
    
    def print_dashboard(self):
        """Print comprehensive dashboard to console"""
        print("\n" + "="*100)
        print("📊 IOT HEALTH CLOUD SYNC - MONITORING DASHBOARD")
        print("="*100)
        print(f"⏰ Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # System Status
        print("🖥️  SYSTEM STATUS:")
        print("-" * 100)
        status = self.get_system_status()
        if status:
            # Group by category
            categories = {}
            for item in status:
                cat = item['metric_category']
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append({
                    'Metric': item['metric_name'],
                    'Value': item['metric_value'],
                    'Unit': item['metric_unit'] or ''
                })
            
            for cat, metrics in categories.items():
                print(f"\n  {cat}:")
                print(tabulate(metrics, headers='keys', tablefmt='simple'))
        else:
            print("  No data available")
        
        # Device Health
        print("\n" + "-" * 100)
        print("🔧 DEVICE HEALTH:")
        print("-" * 100)
        devices = self.get_device_health()
        if devices:
            print(tabulate(devices, headers='keys', tablefmt='grid'))
        else:
            print("  No devices found")
        
        # Sync Performance
        print("\n" + "-" * 100)
        print("📈 SYNC PERFORMANCE (Last 24h):")
        print("-" * 100)
        sync = self.get_sync_performance(24)
        if sync:
            print(tabulate(sync[:10], headers='keys', tablefmt='grid'))
        else:
            print("  No sync activity")
        
        # Recent Errors
        print("\n" + "-" * 100)
        print("❌ RECENT ERRORS (Last 24h):")
        print("-" * 100)
        errors = self.get_recent_errors(24)
        if errors:
            print(tabulate(errors, headers='keys', tablefmt='grid'))
        else:
            print("  ✅ No errors found")
        
        # Active Alerts
        print("\n" + "-" * 100)
        print("🚨 ACTIVE ALERTS:")
        print("-" * 100)
        alerts = self.get_active_alerts()
        if alerts:
            print(tabulate(alerts, headers='keys', tablefmt='grid'))
        else:
            print("  ✅ No active alerts")
        
        # Data Quality
        print("\n" + "-" * 100)
        print("📊 DATA QUALITY (Last 7 days):")
        print("-" * 100)
        quality = self.get_data_quality(7)
        if quality:
            print(tabulate(quality[:7], headers='keys', tablefmt='grid'))
        else:
            print("  No quality data")
        
        # Daily Summary
        print("\n" + "-" * 100)
        print("📅 DAILY SUMMARY (Last 7 days):")
        print("-" * 100)
        summary = self.get_daily_summary(7)
        if summary:
            print(tabulate(summary, headers='keys', tablefmt='grid'))
        else:
            print("  No summary data")
        
        print("\n" + "="*100 + "\n")
    
    def get_health_check(self) -> Dict[str, Any]:
        """
        Perform health check với thresholds
        Returns warnings/errors nếu có vấn đề
        """
        health = {
            'status': 'healthy',
            'warnings': [],
            'errors': [],
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # Check device connectivity
            devices = self.get_device_health()
            offline_devices = [d for d in devices if d['connection_status'] == 'Offline']
            if offline_devices:
                health['warnings'].append(
                    f"{len(offline_devices)} device(s) offline: {', '.join([d['device_id'] for d in offline_devices])}"
                )
            
            # Check sync performance
            sync = self.get_sync_performance(24)
            if sync:
                avg_success_rate = sum(s['success_rate_pct'] for s in sync) / len(sync)
                if avg_success_rate < 90:
                    health['warnings'].append(f"Low sync success rate: {avg_success_rate:.1f}%")
                if avg_success_rate < 70:
                    health['errors'].append(f"Critical sync success rate: {avg_success_rate:.1f}%")
                    health['status'] = 'critical'
            
            # Check errors
            errors = self.get_recent_errors(1)
            critical_errors = [e for e in errors if e['level'] == 'CRITICAL']
            if critical_errors:
                total_critical = sum(e['error_count'] for e in critical_errors)
                health['errors'].append(f"{total_critical} critical error(s) in last hour")
                health['status'] = 'critical'
            
            # Check unacknowledged alerts
            alerts = self.get_active_alerts()
            unack_critical = sum(
                a['unacknowledged'] for a in alerts 
                if a['severity'] in ['critical', 'high']
            )
            if unack_critical > 0:
                health['warnings'].append(f"{unack_critical} unacknowledged critical alert(s)")
            
            # Update status
            if health['warnings'] and health['status'] == 'healthy':
                health['status'] = 'warning'
            
        except Exception as e:
            health['status'] = 'error'
            health['errors'].append(f"Health check failed: {e}")
        
        return health
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()


def main():
    """Main function để test dashboard"""
    
    # Load config
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'app_config.yaml'
    )
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    cloud_config = config.get('cloud', {})
    
    if not cloud_config.get('enabled', False):
        print("❌ Cloud sync is disabled in config")
        return
    
    # Create dashboard
    try:
        dashboard = MonitoringDashboard(cloud_config)
        
        # Print full dashboard
        dashboard.print_dashboard()
        
        # Health check
        health = dashboard.get_health_check()
        print("🏥 HEALTH CHECK:")
        print(f"   Status: {health['status'].upper()}")
        
        if health['warnings']:
            print("\n⚠️  Warnings:")
            for w in health['warnings']:
                print(f"   - {w}")
        
        if health['errors']:
            print("\n❌ Errors:")
            for e in health['errors']:
                print(f"   - {e}")
        
        if health['status'] == 'healthy':
            print("\n   ✅ All systems operational")
        
        # Cleanup
        dashboard.close()
        
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
