"""
Base Sensor Abstract Class
Định nghĩa interface chung cho tất cả các sensor trong hệ thống
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
import threading
import time
import logging
from datetime import datetime


class BaseSensor(ABC):
    """
    Abstract base class cho tất cả sensors trong IoT Health Monitoring System
    
    Attributes:
        name (str): Tên của sensor
        config (Dict): Configuration parameters
        is_running (bool): Trạng thái hoạt động của sensor
        sample_rate (float): Tần số lấy mẫu (Hz)
        logger (logging.Logger): Logger instance
        data_lock (threading.Lock): Lock để thread-safe access
        latest_data (Dict): Dữ liệu mới nhất từ sensor
        error_count (int): Số lần lỗi liên tiếp
        max_error_count (int): Số lỗi tối đa trước khi dừng
        data_callback (Callable): Callback function khi có data mới
        reading_thread (threading.Thread): Thread đọc dữ liệu
    """
    
    # ==================== INITIALIZATION & SETUP ====================
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize base sensor
        
        Args:
            name: Tên sensor
            config: Dictionary chứa cấu hình sensor
        """
        self.name = name
        self.config = config
        self.is_running = False
        self.sample_rate = config.get('sample_rate', 1.0)
        self.logger = logging.getLogger(f"Sensor.{name}")
        
        # Thread safety
        self.data_lock = threading.Lock()
        self.latest_data = None
        
        # Error handling
        self.error_count = 0
        self.max_error_count = config.get('max_error_count', 10)
        
        # Callback for new data
        self.data_callback = None
        
        # Reading thread
        self.reading_thread = None
        
        self.logger.info(f"Initialized {name} sensor with sample rate {self.sample_rate} Hz")
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate cấu hình sensor
        
        Args:
            config: Dictionary cấu hình
            
        Returns:
            bool: True nếu config hợp lệ
        """
        required_keys = ['sample_rate']
        
        for key in required_keys:
            if key not in config:
                self.logger.error(f"Missing required config key: {key}")
                return False
                
        # Validate sample rate
        sample_rate = config.get('sample_rate', 0)
        if not isinstance(sample_rate, (int, float)) or sample_rate <= 0:
            self.logger.error(f"Invalid sample_rate: {sample_rate}")
            return False
            
        return True
    
    # ==================== LIFECYCLE MANAGEMENT ====================
    
    def start(self) -> bool:
        """
        Bắt đầu đọc dữ liệu sensor
        
        Returns:
            bool: True nếu start thành công
        """
        if self.is_running:
            self.logger.warning(f"{self.name} sensor is already running")
            return True
            
        if not self.initialize():
            self.logger.error(f"Failed to initialize {self.name} sensor")
            return False
            
        self.is_running = True
        self.error_count = 0
        
        # Start reading thread
        self.reading_thread = threading.Thread(target=self._reading_loop, daemon=True)
        self.reading_thread.start()
        
        self.logger.info(f"Started {self.name} sensor")
        return True
    
    def stop(self) -> bool:
        """
        Dừng đọc dữ liệu sensor
        
        Returns:
            bool: True nếu stop thành công
        """
        if not self.is_running:
            return True
            
        self.is_running = False
        
        # Wait for thread to finish
        if self.reading_thread and self.reading_thread.is_alive():
            self.reading_thread.join(timeout=2.0)
            
        self.logger.info(f"Stopped {self.name} sensor")
        return True
    
    # ==================== DATA HANDLING ====================
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Khởi tạo hardware sensor
        
        Returns:
            bool: True nếu khởi tạo thành công
        """
        pass
    
    @abstractmethod
    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        """
        Đọc dữ liệu thô từ sensor
        
        Returns:
            Dict chứa raw data hoặc None nếu lỗi
        """
        pass
    
    @abstractmethod
    def process_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Xử lý dữ liệu thô thành dữ liệu có nghĩa
        
        Args:
            raw_data: Dữ liệu thô từ sensor
            
        Returns:
            Dict chứa processed data hoặc None nếu lỗi
        """
        pass
    
    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """
        Lấy dữ liệu mới nhất đã xử lý
        
        Returns:
            Dict chứa latest processed data
        """
        with self.data_lock:
            return self.latest_data.copy() if self.latest_data else None
    
    def set_data_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """
        Set callback function cho khi có data mới
        
        Args:
            callback: Function nhận (sensor_name, data) khi có data mới
        """
        self.data_callback = callback
    
    # ==================== READING LOOP ====================
    
    def _reading_loop(self):
        """
        Main reading loop chạy trong thread riêng
        """
        sleep_time = 1.0 / self.sample_rate
        
        while self.is_running:
            try:
                start_time = time.time()
                
                # Read and process data
                raw_data = self.read_raw_data()
                if raw_data is not None:
                    # Check if we have new data to process
                    has_new_data = True
                    if isinstance(raw_data, dict) and 'read_size' in raw_data:
                        has_new_data = raw_data['read_size'] > 0
                    
                    if has_new_data:
                        processed_data = self.process_data(raw_data)
                        if processed_data is not None:
                            # Add timestamp
                            processed_data['timestamp'] = datetime.now().isoformat()
                            processed_data['sensor'] = self.name
                            
                            # Update latest data
                            with self.data_lock:
                                self.latest_data = processed_data
                            
                            # Call callback if set
                            if self.data_callback:
                                try:
                                    self.data_callback(self.name, processed_data)
                                except Exception as e:
                                    self.logger.error(f"Error in data callback: {e}")
                            
                            # Reset error count on successful read
                            self.error_count = 0
                        else:
                            self._handle_error("Failed to process data")
                    # No new data is not an error for some sensors (like MAX30102)
                else:
                    self._handle_error("Failed to read raw data")
                    
                # Sleep for remaining time to maintain sample rate
                elapsed = time.time() - start_time
                remaining_sleep = sleep_time - elapsed
                if remaining_sleep > 0:
                    time.sleep(remaining_sleep)
                    
            except Exception as e:
                self._handle_error(f"Exception in reading loop: {e}")
                time.sleep(sleep_time)
    
    def _handle_error(self, error_msg: str):
        """
        Handle sensor errors
        
        Args:
            error_msg: Error message
        """
        self.error_count += 1
        self.logger.error(f"{self.name} sensor error ({self.error_count}/{self.max_error_count}): {error_msg}")
        
        if self.error_count >= self.max_error_count:
            self.logger.critical(f"{self.name} sensor exceeded max error count, stopping")
            self.is_running = False
    
    # ==================== UTILITY METHODS ====================
    
    def set_sample_rate(self, rate: float) -> bool:
        """
        Thiết lập tần số lấy mẫu
        
        Args:
            rate: Tần số mong muốn (Hz)
        
        Returns:
            bool: True nếu set thành công
        """
        if rate <= 0:
            self.logger.error("Sample rate must be positive")
            return False
            
        self.sample_rate = rate
        self.logger.info(f"Set {self.name} sample rate to {rate} Hz")
        return True
    
    def get_sensor_info(self) -> Dict[str, Any]:
        """
        Lấy thông tin sensor
        
        Returns:
            Dict chứa thông tin sensor
        """
        return {
            'name': self.name,
            'is_running': self.is_running,
            'sample_rate': self.sample_rate,
            'error_count': self.error_count,
            'max_error_count': self.max_error_count,
            'has_data': self.latest_data is not None,
            'config': self.config.copy()
        }
    
    def self_test(self) -> bool:
        """
        Kiểm tra tình trạng sensor
        
        Returns:
            bool: True nếu sensor hoạt động bình thường
        """
        try:
            # Test basic sensor functionality
            if not self.initialize():
                return False
                
            # Try to read data once
            raw_data = self.read_raw_data()
            if raw_data is None:
                return False
                
            # Try to process data
            processed_data = self.process_data(raw_data)
            if processed_data is None:
                return False
                
            self.logger.info(f"{self.name} sensor self-test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"{self.name} sensor self-test failed: {e}")
            return False
    
    def reset_error_count(self):
        """
        Reset error counter về 0
        """
        self.error_count = 0
        self.logger.info(f"{self.name} sensor error count reset")
    
    def get_status(self) -> str:
        """
        Get current sensor status
        
        Returns:
            Status string: 'running', 'stopped', 'error', 'initializing'
        """
        if not self.is_running:
            return 'stopped'
        elif self.error_count >= self.max_error_count:
            return 'error'
        elif self.latest_data is None:
            return 'initializing'
        else:
            return 'running'