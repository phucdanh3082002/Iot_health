"""
Auto-Sync Scheduler
Tự động sync data mỗi X phút theo config
"""

import threading
import time
import logging
from datetime import datetime
from typing import Optional


class SyncScheduler:
    """
    Background scheduler for automatic cloud synchronization
    
    Runs sync operations at specified intervals in background thread
    """
    
    def __init__(self, cloud_sync_manager, interval_seconds: int = 300):
        """
        Initialize sync scheduler
        
        Args:
            cloud_sync_manager: CloudSyncManager instance
            interval_seconds: Sync interval in seconds (default 5 minutes)
        """
        self.logger = logging.getLogger(__name__)
        self.cloud_sync_manager = cloud_sync_manager
        self.interval_seconds = interval_seconds
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self.logger.info(f"SyncScheduler initialized with {interval_seconds}s interval")
    
    def start(self):
        """Start the background sync scheduler"""
        if self._running:
            self.logger.warning("Sync scheduler already running")
            return
        
        self._running = True
        self._stop_event.clear()
        
        # Start background thread
        self._thread = threading.Thread(
            target=self._sync_loop,
            name="CloudSyncScheduler",
            daemon=True  # Daemon thread will exit when main program exits
        )
        self._thread.start()
        
        self.logger.info(f"Sync scheduler started (interval: {self.interval_seconds}s)")
    
    def stop(self):
        """Stop the background sync scheduler"""
        if not self._running:
            return
        
        self.logger.info("Stopping sync scheduler...")
        self._running = False
        self._stop_event.set()
        
        # Wait for thread to finish (with timeout)
        if self._thread:
            self._thread.join(timeout=10)
        
        self.logger.info("Sync scheduler stopped")
    
    def _sync_loop(self):
        """
        Main sync loop running in background thread
        Performs sync at regular intervals
        """
        self.logger.info("Sync loop started")
        
        # Wait initial interval before first sync
        next_sync_time = time.time() + self.interval_seconds
        
        while self._running:
            try:
                # Sleep until next sync time (interruptible)
                while time.time() < next_sync_time and self._running:
                    if self._stop_event.wait(timeout=1):  # Check every second
                        break
                
                if not self._running:
                    break
                
                # Perform sync
                self._perform_sync()
                
                # Schedule next sync
                next_sync_time = time.time() + self.interval_seconds
                
            except Exception as e:
                self.logger.error(f"Error in sync loop: {e}", exc_info=True)
                # Continue running despite errors
                next_sync_time = time.time() + self.interval_seconds
        
        self.logger.info("Sync loop ended")
    
    def _perform_sync(self):
        """
        Perform a single sync operation
        Logs results and errors
        """
        try:
            start_time = datetime.now()
            self.logger.info("=" * 50)
            self.logger.info(f"Starting scheduled sync at {start_time.strftime('%H:%M:%S')}")
            
            # Connect to cloud if not already connected
            if not self.cloud_sync_manager.is_online:
                self.logger.info("Connecting to cloud...")
                try:
                    self.cloud_sync_manager.connect_to_cloud()
                    self.logger.info("Successfully connected to cloud")
                except Exception as e:
                    self.logger.error(f"Failed to connect to cloud: {e}")
                    self.logger.warning("Cloud offline - skipping sync")
                    return
            
            # Double-check connection
            if not self.cloud_sync_manager.check_cloud_connection():
                self.logger.warning("Cloud connection check failed - skipping sync")
                return
            
            # Perform incremental sync (faster than full sync)
            # Sync records from last 10 minutes to catch any missed
            from datetime import timedelta
            since = datetime.now() - timedelta(minutes=10)
            result = self.cloud_sync_manager.sync_incremental(since)
            
            # Log results
            elapsed = (datetime.now() - start_time).total_seconds()
            
            # Check if sync had any activity or errors
            records_synced = result.get('records_synced', 0)
            alerts_synced = result.get('alerts_synced', 0)
            errors = result.get('errors', [])
            
            if errors:
                self.logger.error(f"Sync failed after {elapsed:.2f}s: {errors}")
            elif records_synced > 0 or alerts_synced > 0:
                self.logger.info(f"Sync completed in {elapsed:.2f}s")
                self.logger.info(f"  Synced: {records_synced} records, {alerts_synced} alerts")
            else:
                self.logger.info(f"Sync completed in {elapsed:.2f}s (no new data to sync)")
            
            self.logger.info("=" * 50)
            
        except Exception as e:
            self.logger.error(f"Sync error: {e}", exc_info=True)
    
    def trigger_sync_now(self):
        """
        Trigger immediate sync (in addition to scheduled syncs)
        Non-blocking - runs in current thread
        """
        if not self._running:
            self.logger.warning("Sync scheduler not running - cannot trigger immediate sync")
            return False
        
        try:
            self.logger.info("Triggering immediate sync...")
            self._perform_sync()
            return True
        except Exception as e:
            self.logger.error(f"Immediate sync failed: {e}")
            return False
    
    def get_status(self) -> dict:
        """
        Get scheduler status
        
        Returns:
            dict: Status information
        """
        return {
            'running': self._running,
            'interval_seconds': self.interval_seconds,
            'thread_alive': self._thread.is_alive() if self._thread else False,
            'next_sync_in': None  # TODO: Calculate time until next sync
        }
