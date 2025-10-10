"""
MLX90614 Temperature Sensor Driver (GY-906)
Driver cho cảm biến nhiệt độ hồng ngoại MLX90614 (GY-906)
"""

from typing import Dict, Any, Optional
import logging
import time
from .base_sensor import BaseSensor

try:
    from smbus2 import SMBus
except ImportError:
    print("Chưa cài đặt thư viện smbus2! Hãy chạy: pip install smbus2")
    SMBus = None


class MLX90614Sensor(BaseSensor):
    """
    Driver cho MLX90614 infrared temperature sensor (GY-906)
    
    Attributes:
        i2c_bus (int): I2C bus number (thường là 1 trên RPi)
        i2c_address (int): I2C address của MLX90614 (mặc định 0x5A)
        ambient_temp_reg (int): Register cho ambient temperature
        object_temp_reg (int): Register cho object temperature
        bus (SMBus): I2C bus instance
        ambient_temperature (float): Nhiệt độ môi trường (°C)
        object_temperature (float): Nhiệt độ đối tượng (°C)
        temperature_offset (float): Offset hiệu chỉnh nhiệt độ
    """
    
    # ==================== INITIALIZATION & SETUP ====================
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MLX90614 temperature sensor
        
        Args:
            config: Configuration dictionary for MLX90614 sensor
        """
        super().__init__("MLX90614", config)
        
        # I2C configuration
        self.i2c_bus = config.get('i2c_bus', 1)
        self.i2c_address = config.get('i2c_address', 0x5A)
        
        # MLX90614 registers
        self.ambient_temp_reg = 0x06  # Ta (ambient temperature)
        self.object_temp_reg = 0x07   # Tobj1 (object temperature)
        
        # Sensor properties
        self.bus = None
        self.ambient_temperature = 0.0
        self.object_temperature = 0.0
        self.temperature_offset = config.get('temperature_offset', 0.0)
        
        # Measurement settings
        self.use_object_temp = config.get('use_object_temp', True)  # True để đo nhiệt độ cơ thể
        self.smooth_factor = config.get('smooth_factor', 0.1)  # Smoothing factor
        self.last_temp = None
    
    def initialize(self) -> bool:
        """
        Initialize MLX90614 sensor hardware
        
        Returns:
            bool: True if initialization successful
        """
        if SMBus is None:
            self.logger.error("smbus2 library not available")
            return False
            
        try:
            self.bus = SMBus(self.i2c_bus)
            
            # Test communication by reading ambient temperature
            test_data = self.bus.read_word_data(self.i2c_address, self.ambient_temp_reg)
            test_temp = (test_data * 0.02) - 273.15
            
            if -40 <= test_temp <= 85:  # Valid range for ambient temp
                self.logger.info(f"MLX90614 initialized successfully at I2C address 0x{self.i2c_address:02X}")
                self.logger.info(f"Initial ambient temperature: {test_temp:.2f}°C")
                return True
            else:
                self.logger.error(f"Invalid temperature reading: {test_temp:.2f}°C")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to initialize MLX90614: {e}")
            if self.bus:
                try:
                    self.bus.close()
                except:
                    pass
                self.bus = None
            return False
    
    # ==================== DATA READING & PROCESSING ====================
    
    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        """
        Read raw temperature data from MLX90614
        
        Returns:
            Dict with 'ambient_temp', 'object_temp' or None if error
        """
        if not self.bus:
            return None
            
        try:
            # Add small delay to prevent I2C bus congestion
            time.sleep(0.01)
            
            # Read ambient temperature with retry
            ambient_data = None
            for attempt in range(3):
                try:
                    ambient_data = self.bus.read_word_data(self.i2c_address, self.ambient_temp_reg)
                    break
                except OSError:
                    if attempt < 2:
                        time.sleep(0.05)  # 50ms retry delay
                    else:
                        raise
            
            ambient_temp = (ambient_data * 0.02) - 273.15
            
            # Small delay between reads
            time.sleep(0.01)
            
            # Read object temperature with retry
            object_data = None
            for attempt in range(3):
                try:
                    object_data = self.bus.read_word_data(self.i2c_address, self.object_temp_reg)
                    break
                except OSError:
                    if attempt < 2:
                        time.sleep(0.05)  # 50ms retry delay
                    else:
                        raise
            
            object_temp = (object_data * 0.02) - 273.15
            
            return {
                'ambient_temp': ambient_temp,
                'object_temp': object_temp,
                'raw_ambient': ambient_data,
                'raw_object': object_data
            }
            
        except Exception as e:
            self.logger.error(f"Failed to read MLX90614 data: {e}")
            return None
    
    def process_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process raw temperature data with smoothing and validation
        
        Args:
            raw_data: Raw temperature readings
            
        Returns:
            Dict with processed temperature data or None if error
        """
        try:
            ambient_temp = raw_data['ambient_temp']
            object_temp = raw_data['object_temp']
            
            # Validate readings
            if not (-40 <= ambient_temp <= 85):
                self.logger.warning(f"Ambient temperature out of range: {ambient_temp:.2f}°C")
                return None
                
            if not (-70 <= object_temp <= 380):
                self.logger.warning(f"Object temperature out of range: {object_temp:.2f}°C")
                return None
            
            # Apply temperature offset
            ambient_temp += self.temperature_offset
            object_temp += self.temperature_offset
            
            # Choose primary temperature reading
            primary_temp = object_temp if self.use_object_temp else ambient_temp
            
            # Apply smoothing filter
            if self.last_temp is not None:
                primary_temp = self.last_temp + self.smooth_factor * (primary_temp - self.last_temp)
            self.last_temp = primary_temp
            
            # Update instance variables
            self.ambient_temperature = ambient_temp
            self.object_temperature = object_temp
            
            # Determine temperature status
            temp_status = self._get_temperature_status(primary_temp)
            
            processed_data = {
                'temperature': round(primary_temp, 2),
                'ambient_temperature': round(ambient_temp, 2),
                'object_temperature': round(object_temp, 2),
                'temperature_unit': 'celsius',
                'sensor_type': 'MLX90614',
                'measurement_type': 'object' if self.use_object_temp else 'ambient',
                'status': temp_status,
                'raw_data': raw_data
            }
            
            return processed_data
            
        except Exception as e:
            self.logger.error(f"Failed to process MLX90614 data: {e}")
            return None
    
    # ==================== TEMPERATURE CONVERSION & STATUS ====================
    
    def _get_temperature_status(self, temperature: float) -> str:
        """
        Determine temperature status based on thresholds
        
        Args:
            temperature: Temperature in Celsius
            
        Returns:
            Status string: 'normal', 'low', 'high', 'critical'
        """
        # Thresholds for body temperature (có thể config từ ngoài)
        if temperature < 35.0:
            return 'critical_low'
        elif temperature < 36.0:
            return 'low'
        elif temperature <= 37.5:
            return 'normal'
        elif temperature <= 39.0:
            return 'high'
        else:
            return 'critical_high'
    
    def get_celsius(self) -> float:
        """
        Get current temperature in Celsius
        
        Returns:
            Temperature in Celsius
        """
        return self.object_temperature if self.use_object_temp else self.ambient_temperature
    
    def get_fahrenheit(self) -> float:
        """
        Get current temperature in Fahrenheit
        
        Returns:
            Temperature in Fahrenheit
        """
        celsius = self.get_celsius()
        return (celsius * 9/5) + 32
    
    # ==================== CALIBRATION & CONFIGURATION ====================
    
    def set_measurement_type(self, use_object: bool) -> bool:
        """
        Set measurement type (object or ambient)
        
        Args:
            use_object: True for object temperature, False for ambient
            
        Returns:
            bool: True if successful
        """
        self.use_object_temp = use_object
        self.logger.info(f"Set measurement type to: {'object' if use_object else 'ambient'}")
        return True
    
    def calibrate_offset(self, reference_temp: float) -> bool:
        """
        Calibrate temperature offset using reference temperature
        
        Args:
            reference_temp: Reference temperature in Celsius
            
        Returns:
            bool: True if calibration successful
        """
        try:
            raw_data = self.read_raw_data()
            if raw_data:
                current_temp = raw_data['object_temp'] if self.use_object_temp else raw_data['ambient_temp']
                self.temperature_offset = reference_temp - current_temp
                self.logger.info(f"Calibrated temperature offset to: {self.temperature_offset:.2f}°C")
                return True
        except Exception as e:
            self.logger.error(f"Calibration failed: {e}")
        return False
    
    # ==================== CLEANUP ====================
    
    def stop(self) -> bool:
        """
        Stop sensor and cleanup resources
        
        Returns:
            bool: True if successful
        """
        result = super().stop()
        
        if self.bus:
            try:
                self.bus.close()
                self.bus = None
                self.logger.info("MLX90614 I2C bus closed")
            except Exception as e:
                self.logger.error(f"Error closing I2C bus: {e}")
                
        return result

from typing import Dict, Any, Optional, List
import logging
from .base_sensor import BaseSensor


class TemperatureSensor(BaseSensor):
    """
    Driver cho temperature sensor (DS18B20 1-Wire hoặc MLX90614 I2C)
    
    Attributes:
        sensor_type (str): Loại sensor ("DS18B20" hoặc "MLX90614")
        gpio_pin (int): GPIO pin cho 1-Wire (DS18B20)
        i2c_address (int): I2C address (MLX90614)
        temperature (float): Giá trị nhiệt độ hiện tại
        unit (str): Đơn vị nhiệt độ ("C" hoặc "F")
    """
    
    # ==================== INITIALIZATION & SETUP ====================
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize temperature sensor
        
        Args:
            config: Configuration dictionary for temperature sensor
        """
        super().__init__("Temperature", config)
    
    def initialize(self) -> bool:
        """
        Initialize temperature sensor hardware
        
        Returns:
            bool: True if initialization successful
        """
        pass
    
    # ==================== DATA PROCESSING ====================
    
    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        """
        Read raw temperature data from sensor
        
        Returns:
            Dict with raw temperature value or None if error
        """
        pass
    
    def process_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process raw temperature data
        
        Args:
            raw_data: Raw temperature value
            
        Returns:
            Dict with 'temperature', 'unit', 'timestamp' or None if error
        """
        pass
    
    # ==================== SENSOR-SPECIFIC READING ====================
    
    def _read_ds18b20(self) -> Optional[float]:
        """
        Read temperature from DS18B20 sensor via 1-Wire
        
        Returns:
            Temperature in Celsius or None if error
        """
        pass
    
    def _read_mlx90614(self) -> Optional[Dict[str, float]]:
        """
        Read temperature from MLX90614 sensor via I2C
        
        Returns:
            Dict with 'ambient' and 'object' temperatures or None if error
        """
        pass
    
    def _find_ds18b20_devices(self) -> List[str]:
        """
        Find all DS18B20 devices on 1-Wire bus
        
        Returns:
            List of device IDs
        """
        pass
    
    # ==================== UTILITY METHODS ====================
    
    def set_temperature_unit(self, unit: str) -> bool:
        """
        Set temperature unit
        
        Args:
            unit: Temperature unit ("C" or "F")
            
        Returns:
            bool: True if set successfully
        """
        pass
    
    def convert_temperature(self, temp_celsius: float, target_unit: str) -> float:
        """
        Convert temperature between Celsius and Fahrenheit
        
        Args:
            temp_celsius: Temperature in Celsius
            target_unit: Target unit ("C" or "F")
            
        Returns:
            Converted temperature
        """
        pass
    
    # ==================== CALIBRATION & INFO ====================
    
    def get_sensor_info(self) -> Dict[str, Any]:
        """
        Get temperature sensor information
        
        Returns:
            Dict with sensor type, status, and capabilities
        """
        pass
    
    def calibrate_sensor(self, reference_temp: float) -> bool:
        """
        Calibrate sensor với reference temperature
        
        Args:
            reference_temp: Reference temperature for calibration
            
        Returns:
            bool: True if calibration successful
        """
        pass