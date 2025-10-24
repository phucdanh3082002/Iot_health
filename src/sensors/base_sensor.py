"""
Base Sensor Abstract Class - Enhanced Version
Định nghĩa interface chung cho tất cả các sensor trong hệ thống

IMPROVEMENTS:
1. Flexible return types: read_raw_data() returns Any (Dict|int|float|Tuple)
2. Abstract cleanup() method for hardware resource management
3. Timeout vs error handling: _handle_timeout() vs _handle_error()
4. _is_valid_reading() hook for sensor-specific validation
5. Blocking mode support for low-SPS sensors (e.g., HX710B)
6. get_raw_value() utility method for debugging/calibration
7. Calibration data passed to __init__ for process_data() access
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Callable, Dict
import threading
import time
import logging
from datetime import datetime


class BaseSensor(ABC):
    """
    Abstract base class cho tất cả sensors trong IoT Health Monitoring System
    
    Supports:
    - High-speed continuous sensors (MAX30102): Dict return with buffers
    - Low-speed blocking ADC (HX710B): int/float return with wait-for-ready
    - Temperature sensors (MLX90614): float return with I2C read
    
    Attributes:
        name (str): Tên của sensor
        config (Dict): Configuration parameters
        is_running (bool): Trạng thái hoạt động của sensor
        sample_rate (float): Tần số lấy mẫu (Hz) - used when blocking_mode=False
        blocking_mode (bool): True for sensors with wait-for-ready (e.g., HX710B)
        read_timeout_ms (int): Timeout cho read operation (ms) - for blocking mode
        calibration (Dict): Calibration parameters (offset, slope, etc.)
        logger (logging.Logger): Logger instance
        data_lock (threading.Lock): Lock để thread-safe access
        latest_data (Dict): Dữ liệu mới nhất từ sensor
        error_count (int): Số lần lỗi liên tiếp (NOT incremented for timeouts)
        timeout_count (int): Số lần timeout liên tiếp
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
                - sample_rate (float): Tần số lấy mẫu (Hz) - for non-blocking mode
                - blocking_mode (bool): True nếu sensor wait-for-ready (e.g., HX710B ADC)
                - read_timeout_ms (int): Timeout cho read operation (ms) - for blocking mode
                - max_error_count (int): Số lỗi tối đa (default: 10)
                - calibration (Dict): Calibration params (offset, slope, etc.)
        """
        self.name = name
        self.config = config
        self.is_running = False
        
        # Reading mode configuration
        self.blocking_mode = config.get('blocking_mode', False)
        self.sample_rate = config.get('sample_rate', 1.0)  # Hz for non-blocking mode
        self.read_timeout_ms = config.get('read_timeout_ms', 1000)  # ms for blocking mode
        
        # Calibration data (accessible by process_data)
        self.calibration = config.get('calibration', {})
        
        self.logger = logging.getLogger(f"Sensor.{name}")
        
        # Thread safety
        self.data_lock = threading.Lock()
        self.latest_data = None
        
        # Error handling (distinguish timeout vs error)
        self.error_count = 0
        self.timeout_count = 0
        self.max_error_count = config.get('max_error_count', 10)
        
        # Callback for new data
        self.data_callback = None
        
        # Reading thread
        self.reading_thread = None
        
        mode_str = "blocking" if self.blocking_mode else f"non-blocking @ {self.sample_rate} Hz"
        self.logger.info(f"Initialized {name} sensor ({mode_str})")
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate cấu hình sensor
        
        Args:
            config: Dictionary cấu hình
            
        Returns:
            bool: True nếu config hợp lệ
        """
        # Sample rate required for non-blocking mode
        if not config.get('blocking_mode', False):
            if 'sample_rate' not in config:
                self.logger.error("Missing required config key: sample_rate (for non-blocking mode)")
                return False
            
            sample_rate = config.get('sample_rate', 0)
            if not isinstance(sample_rate, (int, float)) or sample_rate <= 0:
                self.logger.error(f"Invalid sample_rate: {sample_rate}")
                return False
        
        # Timeout required for blocking mode
        if config.get('blocking_mode', False):
            timeout = config.get('read_timeout_ms', 0)
            if timeout <= 0:
                self.logger.warning(f"Invalid or missing read_timeout_ms: {timeout}, using default 1000ms")
                config['read_timeout_ms'] = 1000
                
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
        self.timeout_count = 0
        
        # Start reading thread
        self.reading_thread = threading.Thread(target=self._reading_loop, daemon=True)
        self.reading_thread.start()
        
        self.logger.info(f"Started {self.name} sensor")
        return True
    
    def stop(self) -> bool:
        """
        Dừng đọc dữ liệu sensor và cleanup hardware resources
        
        Returns:
            bool: True nếu stop thành công
        """
        if not self.is_running:
            return True
            
        self.is_running = False
        
        # Wait for thread to finish
        if self.reading_thread and self.reading_thread.is_alive():
            self.reading_thread.join(timeout=2.0)
        
        # Cleanup hardware resources (GPIO, I2C, etc.)
        try:
            self.cleanup()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            
        self.logger.info(f"Stopped {self.name} sensor")
        return True
    
    # ==================== DATA HANDLING ====================
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        Khởi tạo hardware sensor (GPIO, I2C, SPI setup)
        
        Returns:
            bool: True nếu khởi tạo thành công
        """
        pass
    
    @abstractmethod
    def cleanup(self):
        """
        Cleanup hardware resources khi stop sensor
        
        Ví dụ:
        - GPIO.cleanup() cho GPIO pins
        - bus.close() cho I2C/SPI
        - driver.cleanup() cho external drivers
        
        NOTE: Không raise exception, log error nếu có vấn đề
        """
        pass
    
    @abstractmethod
    def read_raw_data(self) -> Optional[Any]:
        """
        Đọc dữ liệu thô từ sensor
        
        Return types tùy sensor:
        - Dict: High-speed continuous sensors (MAX30102) -> {'ir': [...], 'red': [...], 'read_size': N}
        - int: ADC sensors (HX710B) -> raw counts
        - float: Single-value sensors (MLX90614) -> temperature
        - Tuple: Multi-channel sensors -> (ch1, ch2, ch3)
        - None: Lỗi đọc
        
        NOTE: 
        - For blocking_mode=True: method BLOCKS until data ready or timeout
        - For blocking_mode=False: method returns immediately
        
        Returns:
            Raw data (type depends on sensor) or None if error
        """
        pass
    
    @abstractmethod
    def process_data(self, raw_data: Any) -> Optional[Dict[str, Any]]:
        """
        Xử lý dữ liệu thô thành dữ liệu có nghĩa
        
        Args:
            raw_data: Dữ liệu thô từ sensor (Dict|int|float|Tuple)
            
        Returns:
            Dict chứa processed data hoặc None nếu lỗi
            
        Example:
            # For HX710B ADC:
            raw_data = 123456 (int counts)
            -> {'pressure_mmhg': 120.5, 'counts': 123456, 'valid': True}
            
            # For MAX30102:
            raw_data = {'ir': [...], 'red': [...]}
            -> {'heart_rate': 75, 'spo2': 98, 'valid': True}
        
        NOTE: Can access self.calibration for offset/slope/etc.
        """
        pass
    
    # ==================== OPTIONAL OVERRIDE HOOKS ====================
    
    def _is_valid_reading(self, raw_data: Any) -> bool:
        """
        Override hook để validate raw reading (sensor-specific)
        
        Ví dụ:
        - HX710B: check saturation (counts == 0x7FFFFF or counts == -0x800000)
        - MAX30102: check read_size > 0
        - MLX90614: check value in valid range
        
        Args:
            raw_data: Raw data từ read_raw_data()
            
        Returns:
            bool: True nếu reading hợp lệ (default: always True)
        """
        return True  # Default: accept all readings
    
    # ==================== DATA HANDLING ====================
    
    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """
        Lấy dữ liệu mới nhất đã xử lý
        
        Returns:
            Dict chứa latest processed data
        """
        with self.data_lock:
            return self.latest_data.copy() if self.latest_data else None
    
    def get_raw_value(self) -> Optional[Any]:
        """
        Lấy raw value mới nhất (for debugging/calibration)
        
        Returns:
            Raw data type (int|float|Dict|Tuple) or None
        """
        try:
            raw_data = self.read_raw_data()
            if raw_data is not None and self._is_valid_reading(raw_data):
                return raw_data
            return None
        except Exception as e:
            self.logger.error(f"Error getting raw value: {e}")
            return None
    
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
        
        Behavior:
        - blocking_mode=False: sleep-based loop với sample_rate (Hz)
        - blocking_mode=True: continuous loop, read_raw_data() blocks until ready
        """
        # Calculate sleep time for non-blocking mode
        sleep_time = 1.0 / self.sample_rate if not self.blocking_mode else 0.01
        
        while self.is_running:
            try:
                start_time = time.time()
                
                # Read raw data (blocks if blocking_mode=True)
                raw_data = self.read_raw_data()
                
                if raw_data is not None:
                    # Validate reading (sensor-specific hook)
                    if not self._is_valid_reading(raw_data):
                        self.logger.debug("Invalid reading, skipping")
                        continue
                    
                    # Process data
                    processed_data = self.process_data(raw_data)
                    if processed_data is not None:
                        # Add metadata
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
                        
                        # Reset error/timeout counts on successful read
                        self.error_count = 0
                        self.timeout_count = 0
                    else:
                        self._handle_error("Failed to process data")
                else:
                    # raw_data is None could be timeout or error
                    # Subclass should log specific reason
                    self._handle_timeout("read_raw_data() returned None")
                    
                # Sleep for remaining time to maintain sample rate (non-blocking mode only)
                if not self.blocking_mode:
                    elapsed = time.time() - start_time
                    remaining_sleep = sleep_time - elapsed
                    if remaining_sleep > 0:
                        time.sleep(remaining_sleep)
                    
            except Exception as e:
                self._handle_error(f"Exception in reading loop: {e}")
                time.sleep(sleep_time)
    
    def _handle_timeout(self, msg: str):
        """
        Handle sensor timeout (KHÔNG increment error_count)
        
        Timeout ≠ Error:
        - Timeout: sensor chưa sẵn sàng (e.g., HX710B DOUT=HIGH)
        - Error: hardware failure, invalid data, exception
        
        Args:
            msg: Timeout message
        """
        self.timeout_count += 1
        if self.timeout_count % 10 == 0:  # Log every 10 timeouts
            self.logger.warning(f"{self.name} timeout ({self.timeout_count} consecutive): {msg}")
    
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
        Thiết lập tần số lấy mẫu (chỉ cho non-blocking mode)
        
        Args:
            rate: Tần số mong muốn (Hz)
        
        Returns:
            bool: True nếu set thành công
        """
        if self.blocking_mode:
            self.logger.warning("Cannot set sample_rate in blocking mode")
            return False
            
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
            'blocking_mode': self.blocking_mode,
            'sample_rate': self.sample_rate if not self.blocking_mode else 'N/A',
            'read_timeout_ms': self.read_timeout_ms if self.blocking_mode else 'N/A',
            'error_count': self.error_count,
            'timeout_count': self.timeout_count,
            'max_error_count': self.max_error_count,
            'has_data': self.latest_data is not None,
            'has_calibration': len(self.calibration) > 0,
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
                self.logger.error("Self-test failed: read_raw_data() returned None")
                return False
            
            if not self._is_valid_reading(raw_data):
                self.logger.error("Self-test failed: invalid reading")
                return False
                
            # Try to process data
            processed_data = self.process_data(raw_data)
            if processed_data is None:
                self.logger.error("Self-test failed: process_data() returned None")
                return False
            
            # Cleanup after test
            self.cleanup()
                
            self.logger.info(f"{self.name} sensor self-test passed")
            return True
            
        except Exception as e:
            self.logger.error(f"{self.name} sensor self-test failed: {e}")
            return False
    
    def reset_error_count(self):
        """
        Reset error/timeout counters về 0
        """
        self.error_count = 0
        self.timeout_count = 0
        self.logger.info(f"{self.name} sensor error/timeout counters reset")
    
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