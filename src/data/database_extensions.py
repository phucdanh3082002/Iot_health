"""
Database Manager Extensions
Additional methods for new schema features (Device, DeviceOwnership, SyncQueue)
These will be integrated into DatabaseManager class
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
import json
from sqlalchemy import desc, and_


class DatabaseManagerExtensions:
    """
    Extension methods for DatabaseManager to handle new schema features
    This class provides methods that will be added to DatabaseManager
    """
    
    # ═══════════════════════════════════════════════════════════════════
    # DEVICE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════
    
    def create_device(self, device_data: Dict[str, Any]) -> Optional[str]:
        """
        Create or update device record
        
        Args:
            device_data: Device information {
                'device_id': str (required),
                'device_name': str (required),
                'device_type': str,
                'location': str,
                'firmware_version': str,
                'os_version': str,
                ...
            }
            
        Returns:
            device_id if successful, None if error
        """
        try:
            from .models import Device
            
            with self.get_session() as session:
                # Check if device exists
                device = session.query(Device).filter_by(
                    device_id=device_data['device_id']
                ).first()
                
                if device:
                    # Update existing device
                    for key, value in device_data.items():
                        if hasattr(device, key) and key != 'device_id':
                            setattr(device, key, value)
                    device.updated_at = datetime.utcnow()
                    device.last_seen = datetime.utcnow()
                    self.logger.info(f"Updated device: {device_data['device_id']}")
                else:
                    # Create new device
                    device = Device(
                        device_id=device_data['device_id'],
                        device_name=device_data['device_name'],
                        device_type=device_data.get('device_type', 'blood_pressure_monitor'),
                        location=device_data.get('location'),
                        ip_address=device_data.get('ip_address'),
                        firmware_version=device_data.get('firmware_version'),
                        os_version=device_data.get('os_version'),
                        is_active=device_data.get('is_active', True),
                        last_seen=datetime.utcnow()
                    )
                    session.add(device)
                    self.logger.info(f"Created device: {device_data['device_id']}")
                
                return device_data['device_id']
                
        except Exception as e:
            self.logger.error(f"Error creating/updating device: {e}", exc_info=True)
            return None
    
    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Get device information
        
        Args:
            device_id: Device identifier
            
        Returns:
            Device data dictionary or None if not found
        """
        try:
            from .models import Device
            
            with self.get_session() as session:
                device = session.query(Device).filter_by(device_id=device_id).first()
                
                if not device:
                    return None
                
                return {
                    'id': device.id,
                    'device_id': device.device_id,
                    'device_name': device.device_name,
                    'device_type': device.device_type,
                    'location': device.location,
                    'ip_address': device.ip_address,
                    'firmware_version': device.firmware_version,
                    'os_version': device.os_version,
                    'is_active': device.is_active,
                    'last_seen': device.last_seen.isoformat() if device.last_seen else None,
                    'pairing_code': device.pairing_code,
                    'created_at': device.created_at.isoformat() if device.created_at else None,
                    'updated_at': device.updated_at.isoformat() if device.updated_at else None
                }
                
        except Exception as e:
            self.logger.error(f"Error getting device: {e}")
            return None
    
    def update_device_heartbeat(self, device_id: str, ip_address: str = None) -> bool:
        """
        Update device last_seen timestamp (heartbeat)
        
        Args:
            device_id: Device identifier
            ip_address: Optional IP address to update
            
        Returns:
            bool: True if update successful
        """
        try:
            from .models import Device
            
            with self.get_session() as session:
                device = session.query(Device).filter_by(device_id=device_id).first()
                
                if not device:
                    self.logger.warning(f"Device {device_id} not found for heartbeat")
                    return False
                
                device.last_seen = datetime.utcnow()
                if ip_address:
                    device.ip_address = ip_address
                
                return True
                
        except Exception as e:
            self.logger.error(f"Error updating device heartbeat: {e}")
            return False
    
    def generate_pairing_code(self, device_id: str) -> Optional[str]:
        """
        Generate pairing code for device QR code
        
        Args:
            device_id: Device identifier
            
        Returns:
            Pairing code string or None if error
        """
        try:
            import secrets
            from .models import Device
            
            # Generate cryptographically secure random code
            pairing_code = secrets.token_urlsafe(16)
            
            with self.get_session() as session:
                device = session.query(Device).filter_by(device_id=device_id).first()
                
                if not device:
                    self.logger.error(f"Device {device_id} not found")
                    return None
                
                device.pairing_code = pairing_code
                
                # Generate QR data (JSON)
                qr_data = {
                    'device_id': device_id,
                    'device_name': device.device_name,
                    'pairing_code': pairing_code,
                    'timestamp': datetime.utcnow().isoformat()
                }
                device.pairing_qr_data = json.dumps(qr_data)
                device.updated_at = datetime.utcnow()
                
                self.logger.info(f"Generated pairing code for device {device_id}")
                return pairing_code
                
        except Exception as e:
            self.logger.error(f"Error generating pairing code: {e}")
            return None
    
    # ═══════════════════════════════════════════════════════════════════
    # DEVICE OWNERSHIP MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════
    
    def add_device_ownership(self, user_id: str, device_id: str, role: str = 'owner', nickname: str = None) -> Optional[int]:
        """
        Add user ownership/access to device
        
        Args:
            user_id: User identifier
            device_id: Device identifier
            role: User role (owner, caregiver, viewer)
            nickname: Optional device nickname
            
        Returns:
            Ownership ID if successful, None if error
        """
        try:
            from .models import DeviceOwnership
            
            with self.get_session() as session:
                # Check if ownership already exists
                existing = session.query(DeviceOwnership).filter_by(
                    user_id=user_id,
                    device_id=device_id
                ).first()
                
                if existing:
                    # Update existing
                    existing.role = role
                    if nickname:
                        existing.nickname = nickname
                    existing.added_at = datetime.utcnow()
                    self.logger.info(f"Updated ownership: user={user_id}, device={device_id}")
                    return existing.id
                else:
                    # Create new
                    ownership = DeviceOwnership(
                        user_id=user_id,
                        device_id=device_id,
                        role=role,
                        nickname=nickname,
                        added_at=datetime.utcnow()
                    )
                    session.add(ownership)
                    session.flush()
                    self.logger.info(f"Added ownership: user={user_id}, device={device_id}")
                    return ownership.id
                
        except Exception as e:
            self.logger.error(f"Error adding device ownership: {e}")
            return None
    
    def get_user_devices(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all devices owned/accessible by user
        
        Args:
            user_id: User identifier
            
        Returns:
            List of device data dictionaries
        """
        try:
            from .models import DeviceOwnership, Device
            
            with self.get_session() as session:
                ownerships = session.query(DeviceOwnership, Device).join(
                    Device, DeviceOwnership.device_id == Device.device_id
                ).filter(DeviceOwnership.user_id == user_id).all()
                
                devices = []
                for ownership, device in ownerships:
                    devices.append({
                        'device_id': device.device_id,
                        'device_name': device.device_name,
                        'device_type': device.device_type,
                        'location': device.location,
                        'is_active': device.is_active,
                        'last_seen': device.last_seen.isoformat() if device.last_seen else None,
                        'role': ownership.role,
                        'nickname': ownership.nickname,
                        'added_at': ownership.added_at.isoformat() if ownership.added_at else None
                    })
                
                return devices
                
        except Exception as e:
            self.logger.error(f"Error getting user devices: {e}")
            return []
    
    def remove_device_ownership(self, user_id: str, device_id: str) -> bool:
        """
        Remove user access to device
        
        Args:
            user_id: User identifier
            device_id: Device identifier
            
        Returns:
            bool: True if removal successful
        """
        try:
            from .models import DeviceOwnership
            
            with self.get_session() as session:
                deleted = session.query(DeviceOwnership).filter_by(
                    user_id=user_id,
                    device_id=device_id
                ).delete()
                
                if deleted > 0:
                    self.logger.info(f"Removed ownership: user={user_id}, device={device_id}")
                    return True
                else:
                    self.logger.warning(f"No ownership found to remove: user={user_id}, device={device_id}")
                    return False
                
        except Exception as e:
            self.logger.error(f"Error removing device ownership: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════
    # SYNC QUEUE MANAGEMENT (Store & Forward)
    # ═══════════════════════════════════════════════════════════════════
    
    def enqueue_for_sync(self, table_name: str, operation: str, record_data: Dict[str, Any], priority: int = 5) -> Optional[int]:
        """
        Add item to sync queue for later cloud sync
        
        Args:
            table_name: Target table name
            operation: Operation type (INSERT, UPDATE, DELETE)
            record_data: Data snapshot
            priority: Priority level (1=highest, 10=lowest)
            
        Returns:
            Queue item ID if successful, None if error
        """
        try:
            from .models import SyncQueue
            
            # Get device_id from config
            device_id = self.full_config.get('cloud', {}).get('device', {}).get('device_id', 'unknown')
            
            with self.get_session() as session:
                queue_item = SyncQueue(
                    device_id=device_id,
                    table_name=table_name,
                    operation=operation,
                    record_id=str(record_data.get('id', '')),
                    data_snapshot=record_data,
                    priority=priority,
                    sync_status='pending',
                    sync_attempts=0
                )
                session.add(queue_item)
                session.flush()
                
                self.logger.info(f"Enqueued for sync: table={table_name}, operation={operation}, id={queue_item.id}")
                return queue_item.id
                
        except Exception as e:
            self.logger.error(f"Error enqueueing for sync: {e}")
            return None
    
    def get_pending_sync_items(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get pending sync queue items
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of queue item dictionaries
        """
        try:
            from .models import SyncQueue
            
            with self.get_session() as session:
                items = session.query(SyncQueue).filter_by(
                    sync_status='pending'
                ).order_by(
                    SyncQueue.priority.asc(),
                    SyncQueue.created_at.asc()
                ).limit(limit).all()
                
                result = []
                for item in items:
                    result.append({
                        'id': item.id,
                        'device_id': item.device_id,
                        'table_name': item.table_name,
                        'operation': item.operation,
                        'record_id': item.record_id,
                        'data_snapshot': item.data_snapshot,
                        'priority': item.priority,
                        'created_at': item.created_at.isoformat() if item.created_at else None,
                        'sync_attempts': item.sync_attempts
                    })
                
                return result
                
        except Exception as e:
            self.logger.error(f"Error getting pending sync items: {e}")
            return []
    
    def update_sync_item_status(self, queue_id: int, status: str, error_message: str = None) -> bool:
        """
        Update sync queue item status
        
        Args:
            queue_id: Queue item ID
            status: New status (pending, syncing, success, failed)
            error_message: Optional error message
            
        Returns:
            bool: True if update successful
        """
        try:
            from .models import SyncQueue
            
            with self.get_session() as session:
                item = session.query(SyncQueue).filter_by(id=queue_id).first()
                
                if not item:
                    self.logger.warning(f"Sync queue item {queue_id} not found")
                    return False
                
                item.sync_status = status
                item.sync_attempts += 1
                item.last_sync_attempt = datetime.utcnow()
                
                if error_message:
                    item.error_message = error_message
                
                self.logger.debug(f"Updated sync item {queue_id}: status={status}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error updating sync item status: {e}")
            return False
    
    def delete_sync_item(self, queue_id: int) -> bool:
        """
        Delete sync queue item (after successful sync)
        
        Args:
            queue_id: Queue item ID
            
        Returns:
            bool: True if deletion successful
        """
        try:
            from .models import SyncQueue
            
            with self.get_session() as session:
                deleted = session.query(SyncQueue).filter_by(id=queue_id).delete()
                
                if deleted > 0:
                    self.logger.debug(f"Deleted sync queue item {queue_id}")
                    return True
                else:
                    return False
                
        except Exception as e:
            self.logger.error(f"Error deleting sync item: {e}")
            return False
    
    def get_sync_queue_stats(self) -> Dict[str, Any]:
        """
        Get sync queue statistics
        
        Returns:
            Dictionary with queue statistics
        """
        try:
            from .models import SyncQueue
            
            with self.get_session() as session:
                total = session.query(SyncQueue).count()
                pending = session.query(SyncQueue).filter_by(sync_status='pending').count()
                failed = session.query(SyncQueue).filter_by(sync_status='failed').count()
                
                return {
                    'total_items': total,
                    'pending_items': pending,
                    'failed_items': failed,
                    'success_rate': round((total - failed) / total * 100, 2) if total > 0 else 0
                }
                
        except Exception as e:
            self.logger.error(f"Error getting sync queue stats: {e}")
            return {'total_items': 0, 'pending_items': 0, 'failed_items': 0, 'success_rate': 0}


# ═══════════════════════════════════════════════════════════════════
# INTEGRATION INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════════
"""
To integrate these methods into DatabaseManager:

1. Add this import at top of database.py:
   from .database_extensions import DatabaseManagerExtensions

2. Make DatabaseManager inherit from DatabaseManagerExtensions:
   class DatabaseManager(DatabaseManagerExtensions):
       ...

3. All methods above will be available on DatabaseManager instances

Example usage:
    db = DatabaseManager(config)
    
    # Device management
    db.create_device({'device_id': 'rpi_001', 'device_name': 'Living Room Monitor'})
    device = db.get_device('rpi_001')
    db.update_device_heartbeat('rpi_001', '192.168.1.100')
    
    # Device ownership
    db.add_device_ownership('user123', 'rpi_001', 'owner', 'My Monitor')
    devices = db.get_user_devices('user123')
    
    # Sync queue
    db.enqueue_for_sync('health_records', 'INSERT', {'id': 123, ...})
    pending = db.get_pending_sync_items(50)
    db.update_sync_item_status(1, 'success')
"""
