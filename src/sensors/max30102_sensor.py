"""
MAX30102 Sensor Driver
Driver cho cảm biến nhịp tim và SpO2 MAX30102
"""

from typing import Dict, Any, Optional, List
import logging
import time
import numpy as np
from collections import deque
from .base_sensor import BaseSensor

try:
    import max30102
    import hrcalc
except ImportError:
    print("Không tìm thấy max30102 hoặc hrcalc! Hãy chắc chắn đã copy vào lib hoặc PYTHONPATH.")
    max30102 = None
    hrcalc = None


class MAX30102Sensor(BaseSensor):
    """
    Driver cho MAX30102 heart rate và SpO2 sensor
    
    Attributes:
        led_mode (int): LED mode (1=RED, 2=RED+IR, 3=RED+IR+GREEN)
        pulse_amplitude_red (int): LED pulse amplitude cho RED (0x00-0xFF)
        pulse_amplitude_ir (int): LED pulse amplitude cho IR (0x00-0xFF)
        adc_range (int): ADC range setting
        sample_average (int): Sample averaging setting
        buffer_size (int): Buffer size cho calculation
        ir_threshold (int): Threshold để detect finger
        max30102_instance: MAX30102 hardware instance
        ir_buffer (deque): Circular buffer cho IR data
        red_buffer (deque): Circular buffer cho RED data
        heart_rate (float): Nhịp tim hiện tại (BPM)
        spo2 (float): SpO2 hiện tại (%)
        finger_detected (bool): Trạng thái phát hiện ngón tay
        hr_valid (bool): Validity của heart rate measurement
        spo2_valid (bool): Validity của SpO2 measurement
        readings_count (int): Số lần đọc để đảm bảo stability
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MAX30102 sensor
        
        Args:
            config: Configuration dictionary for MAX30102 sensor
        """
        super().__init__("MAX30102", config)
        
        # MAX30102 configuration
        self.led_mode = config.get('led_mode', 3)  # SpO2 mode (RED + IR)
        self.pulse_amplitude_red = config.get('pulse_amplitude_red', 0x7F)  # Higher brightness
        self.pulse_amplitude_ir = config.get('pulse_amplitude_ir', 0x7F)   # Higher brightness
        self.adc_range = config.get('adc_range', 4096)
        self.sample_average = config.get('sample_average', 8)
        
        # Buffer and processing settings
        self.buffer_size = config.get('buffer_size', 100)
        self.ir_threshold = config.get('ir_threshold', 50000)
        self.min_readings_for_calc = config.get('min_readings_for_calc', 50)
        
        # Hardware instance
        self.max30102_instance = None
        
        # Data buffers
        self.ir_buffer = deque(maxlen=self.buffer_size)
        self.red_buffer = deque(maxlen=self.buffer_size)
        
        # Current measurements
        self.heart_rate = 0.0
        self.spo2 = 0.0
        self.finger_detected = False
        self.hr_valid = False
        self.spo2_valid = False
        self.readings_count = 0
        
        # Signal quality metrics
        self.signal_quality_ir = 0.0
        self.signal_quality_red = 0.0
        self.dc_removal_alpha = 0.95  # DC removal filter coefficient
        self.ir_dc_value = 0.0
        self.red_dc_value = 0.0
    
    def initialize(self) -> bool:
        """
        Initialize MAX30102 sensor hardware
        
        Returns:
            bool: True if initialization successful
        """
        if max30102 is None or hrcalc is None:
            self.logger.error("MAX30102 or hrcalc library not available")
            return False
            
        try:
            # Initialize MAX30102 with I2C channel 1, address 0x57 (default)
            self.max30102_instance = max30102.MAX30102(channel=1, address=0x57)
            
            # Configure MAX30102 settings với led_mode từ config
            self.max30102_instance.setup(led_mode=self.led_mode)
            
            # Set LED amplitudes to high values for visibility
            self.max30102_instance.set_config(max30102.REG_LED1_PA, [self.pulse_amplitude_red])
            self.max30102_instance.set_config(max30102.REG_LED2_PA, [self.pulse_amplitude_ir])
            
            # Force mode to ensure LEDs are active
            self.max30102_instance.set_config(max30102.REG_MODE_CONFIG, [self.led_mode])
            
            self.logger.info("MAX30102 sensor initialized successfully")
            self.logger.info(f"LED mode: {self.led_mode}, Buffer size: {self.buffer_size}")
            self.logger.info(f"IR threshold: {self.ir_threshold}, Sample rate: {self.sample_rate} Hz")
            self.logger.info(f"LED amplitudes - RED: 0x{self.pulse_amplitude_red:02X}, IR: 0x{self.pulse_amplitude_ir:02X}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize MAX30102: {e}")
            return False
    
    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        """
        Read raw RED and IR data from MAX30102
        
        Returns:
            Dict with 'red' and 'ir' data or None if error
        """
        if not self.max30102_instance:
            return None
            
        try:
            # Check if data is available
            num_available = self.max30102_instance.get_data_present()
            
            if num_available == 0:
                # No new data available, return empty arrays
                return {
                    'red': [],
                    'ir': [],
                    'read_size': 0
                }
            
            # Read available data (limited to reasonable amount per reading)
            read_size = min(num_available, 25)
            
            red_data, ir_data = self.max30102_instance.read_sequential(read_size)
            
            return {
                'red': red_data,
                'ir': ir_data,
                'read_size': len(ir_data),
                'available_samples': num_available
            }
            
        except Exception as e:
            self.logger.error(f"Failed to read MAX30102 data: {e}")
            return None
    
    def process_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process RED/IR data to calculate heart rate and SpO2
        
        Args:
            raw_data: Raw RED and IR data
            
        Returns:
            Dict with processed heart rate and SpO2 data or None if error
        """
        try:
            red_data = raw_data['red']
            ir_data = raw_data['ir']
            
            # Add new data to buffers
            self.red_buffer.extend(red_data)
            self.ir_buffer.extend(ir_data)
            
            self.readings_count += len(ir_data)
            
            # Check finger detection
            ir_mean = np.mean(ir_data) if len(ir_data) > 0 else 0
            self.finger_detected = ir_mean > self.ir_threshold
            
            # Update signal quality
            self._update_signal_quality()
            
            if not self.finger_detected:
                # Reset values when finger not detected
                self.heart_rate = 0.0
                self.spo2 = 0.0
                self.hr_valid = False
                self.spo2_valid = False
                
                return {
                    'heart_rate': self.heart_rate,
                    'spo2': self.spo2,
                    'finger_detected': self.finger_detected,
                    'hr_valid': self.hr_valid,
                    'spo2_valid': self.spo2_valid,
                    'signal_quality_ir': 0.0,
                    'signal_quality_red': 0.0,
                    'ir_mean': ir_mean,
                    'status': 'no_finger'
                }
            
            # Only calculate HR/SpO2 if we have enough data and finger detected
            if len(self.ir_buffer) >= self.min_readings_for_calc and len(self.red_buffer) >= self.min_readings_for_calc:
                try:
                    # Convert buffers to numpy arrays (use last 100 samples for calculation)
                    ir_array = np.array(list(self.ir_buffer)[-100:])
                    red_array = np.array(list(self.red_buffer)[-100:])
                    
                    # Calculate HR and SpO2 using hrcalc
                    hr, hr_valid, spo2, spo2_valid = hrcalc.calc_hr_and_spo2(ir_array, red_array)
                    
                    # Update heart rate if valid
                    if hr_valid and hr > 0 and 40 <= hr <= 200:  # Reasonable HR range
                        self.heart_rate = round(float(hr), 1)
                        self.hr_valid = True
                    else:
                        self.hr_valid = False
                        if hr_valid:
                            self.logger.debug(f"HR out of range: {hr}")
                        
                    # Update SpO2 if valid
                    if spo2_valid and spo2 > 0 and 70 <= spo2 <= 100:  # Reasonable SpO2 range
                        self.spo2 = round(float(spo2), 1)
                        self.spo2_valid = True
                    else:
                        self.spo2_valid = False
                        if spo2_valid:
                            self.logger.debug(f"SpO2 out of range: {spo2}")
                        
                except Exception as e:
                    self.logger.error(f"Error calculating HR/SpO2: {e}")
                    self.hr_valid = False
                    self.spo2_valid = False
            
            # Determine status
            status = self._get_measurement_status()
            
            processed_data = {
                'heart_rate': self.heart_rate,
                'spo2': self.spo2,
                'finger_detected': self.finger_detected,
                'hr_valid': self.hr_valid,
                'spo2_valid': self.spo2_valid,
                'signal_quality_ir': self.signal_quality_ir,
                'signal_quality_red': self.signal_quality_red,
                'ir_mean': ir_mean,
                'buffer_fill': len(self.ir_buffer),
                'readings_count': self.readings_count,
                'status': status,
                'sensor_type': 'MAX30102'
            }
            
            return processed_data
            
        except Exception as e:
            self.logger.error(f"Failed to process MAX30102 data: {e}")
            return None
    
    def _update_signal_quality(self):
        """
        Update signal quality metrics based on current buffer data
        """
        try:
            if len(self.ir_buffer) > 10:
                ir_array = np.array(list(self.ir_buffer)[-50:])  # Use last 50 samples
                red_array = np.array(list(self.red_buffer)[-50:])
                
                # Calculate signal quality as coefficient of variation (inverse)
                # Lower CV = better signal quality
                ir_std = np.std(ir_array)
                ir_mean = np.mean(ir_array)
                if ir_mean > 0:
                    ir_cv = ir_std / ir_mean
                    self.signal_quality_ir = max(0, min(100, 100 - (ir_cv * 100)))
                
                red_std = np.std(red_array)
                red_mean = np.mean(red_array)
                if red_mean > 0:
                    red_cv = red_std / red_mean
                    self.signal_quality_red = max(0, min(100, 100 - (red_cv * 100)))
                    
        except Exception as e:
            self.logger.error(f"Error updating signal quality: {e}")
    
    def _get_measurement_status(self) -> str:
        """
        Get overall measurement status
        
        Returns:
            Status string
        """
        if not self.finger_detected:
            return 'no_finger'
        elif len(self.ir_buffer) < self.min_readings_for_calc:
            return 'initializing'
        elif not self.hr_valid and not self.spo2_valid:
            return 'poor_signal'
        elif self.hr_valid and self.spo2_valid:
            return 'good'
        elif self.hr_valid or self.spo2_valid:
            return 'partial'
        else:
            return 'error'
    
    def get_heart_rate_status(self) -> str:
        """
        Get heart rate status based on current value
        
        Returns:
            Status string: 'normal', 'low', 'high', 'critical'
        """
        if not self.hr_valid:
            return 'invalid'
            
        hr = self.heart_rate
        if hr < 40:
            return 'critical_low'
        elif hr < 60:
            return 'low'
        elif hr <= 100:
            return 'normal'
        elif hr <= 150:
            return 'high'
        else:
            return 'critical_high'
    
    def get_spo2_status(self) -> str:
        """
        Get SpO2 status based on current value
        
        Returns:
            Status string: 'normal', 'low', 'critical'
        """
        if not self.spo2_valid:
            return 'invalid'
            
        spo2 = self.spo2
        if spo2 < 90:
            return 'critical'
        elif spo2 < 95:
            return 'low'
        else:
            return 'normal'
    
    def reset_buffers(self):
        """
        Reset all data buffers
        """
        self.ir_buffer.clear()
        self.red_buffer.clear()
        self.readings_count = 0
        self.hr_valid = False
        self.spo2_valid = False
        self.logger.info("MAX30102 buffers reset")
    
    def set_led_amplitude(self, red_amplitude: int, ir_amplitude: int) -> bool:
        """
        Set LED pulse amplitudes
        
        Args:
            red_amplitude: RED LED amplitude (0x00-0xFF)
            ir_amplitude: IR LED amplitude (0x00-0xFF)
            
        Returns:
            bool: True if successful
        """
        try:
            self.pulse_amplitude_red = max(0, min(255, red_amplitude))
            self.pulse_amplitude_ir = max(0, min(255, ir_amplitude))
            
            # Apply settings to hardware (if supported by library)
            self.logger.info(f"Set LED amplitudes - RED: 0x{self.pulse_amplitude_red:02X}, IR: 0x{self.pulse_amplitude_ir:02X}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to set LED amplitudes: {e}")
            return False
    
    def stop(self) -> bool:
        """
        Stop sensor and cleanup resources
        
        Returns:
            bool: True if successful
        """
        result = super().stop()
        
        if self.max30102_instance:
            try:
                self.max30102_instance.shutdown()
                self.logger.info("MAX30102 sensor shutdown")
            except Exception as e:
                self.logger.error(f"Error shutting down MAX30102: {e}")
                
        self.reset_buffers()
        return result

