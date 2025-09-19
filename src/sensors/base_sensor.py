"""
Base Sensor Abstract Class
Định nghĩa interface chung cho tất cả các sensor trong hệ thống
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import threading
import time
import logging


class BaseSensor(ABC):
    """
    Abstract base class cho tất cả sensors trong IoT Health Monitoring System
    
    Attributes:
        name (str): Tên của sensor
        config (Dict): Configuration parameters
        is_running (bool): Trạng thái hoạt động của sensor
        sample_rate (float): Tần số lấy mẫu (Hz)
        logger (logging.Logger): Logger instance
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize base sensor
        
        Args:
            name: Tên sensor
            config: Dictionary chứa cấu hình sensor
        """
        pass
    
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
    
    def start(self) -> bool:
        """
        Bắt đầu đọc dữ liệu sensor
        
        Returns:
            bool: True nếu start thành công
        """
        pass
    
    def stop(self) -> bool:
        """
        Dừng đọc dữ liệu sensor
        
        Returns:
            bool: True nếu stop thành công
        """
        pass
    
    def get_latest_data(self) -> Optional[Dict[str, Any]]:
        """
        Lấy dữ liệu mới nhất đã xử lý
        
        Returns:
            Dict chứa latest processed data
        """
        pass
    
    def set_sample_rate(self, rate: float) -> bool:
        """
        Thiết lập tần số lấy mẫu
        
        Args:
            rate: Tần số mong muốn (Hz)
            
        Returns:
            bool: True nếu thiết lập thành công
        """
        pass
    
    def get_sensor_info(self) -> Dict[str, Any]:
        """
        Lấy thông tin sensor
        
        Returns:
            Dict chứa thông tin sensor
        """
        pass
    
    def self_test(self) -> bool:
        """
        Kiểm tra tình trạng sensor
        
        Returns:
            bool: True nếu sensor hoạt động bình thường
        """
        pass
    
    def _sensor_thread(self):
        """
        Thread function cho việc đọc sensor liên tục
        """
        pass
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate cấu hình sensor
        
        Args:
            config: Dictionary cấu hình
            
        Returns:
            bool: True nếu config hợp lệ
        """
        pass