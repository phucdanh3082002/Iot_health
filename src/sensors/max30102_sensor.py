"""
MAX30102 Sensor Driver với tích hợp thư viện MAX30102 và HRCalc
Driver cho cảm biến nhịp tim và SpO2 MAX30102 với thuật toán lọc tối ưu
Tích hợp trực tiếp MAX30102 hardware driver và Heart Rate calculation algorithms
"""

from typing import Dict, Any, Optional, List, Tuple
import logging
import time
import numpy as np
from collections import deque
from .base_sensor import BaseSensor

# Tích hợp smbus cho I2C communication
try:
    import smbus
except ImportError:
    print("Warning: smbus not available - MAX30102 sẽ không hoạt động trên hardware thật")
    smbus = None


# ========================================
# MAX30102 Hardware Driver - Tích hợp trực tiếp
# ========================================

# MAX30102 Register addresses
REG_INTR_STATUS_1 = 0x00
REG_INTR_STATUS_2 = 0x01
REG_INTR_ENABLE_1 = 0x02
REG_INTR_ENABLE_2 = 0x03
REG_FIFO_WR_PTR = 0x04
REG_OVF_COUNTER = 0x05
REG_FIFO_RD_PTR = 0x06
REG_FIFO_DATA = 0x07
REG_FIFO_CONFIG = 0x08
REG_MODE_CONFIG = 0x09
REG_SPO2_CONFIG = 0x0A
REG_LED1_PA = 0x0C
REG_LED2_PA = 0x0D
REG_PILOT_PA = 0x10
REG_MULTI_LED_CTRL1 = 0x11
REG_MULTI_LED_CTRL2 = 0x12
REG_TEMP_INTR = 0x1F
REG_TEMP_FRAC = 0x20
REG_TEMP_CONFIG = 0x21
REG_PROX_INT_THRESH = 0x30
REG_REV_ID = 0xFE
REG_PART_ID = 0xFF


class MAX30102Hardware:
    """
    MAX30102 Hardware Driver - Tích hợp trực tiếp từ thư viện max30102.py
    """
    
    def __init__(self, channel=1, address=0x57):
        """
        Initialize MAX30102 hardware communication
        
        Args:
            channel: I2C channel (default=1)
            address: I2C address (default=0x57)
        """
        self.address = address
        self.channel = channel
        self.bus = None
        
        if smbus is not None:
            self.bus = smbus.SMBus(self.channel)
            self.reset()
            time.sleep(1)  # Wait 1 sec after reset
            
            # Read & clear interrupt register
            reg_data = self.bus.read_i2c_block_data(self.address, REG_INTR_STATUS_1, 1)
            self.setup()
    
    def shutdown(self):
        """Shutdown the device"""
        if self.bus:
            self.bus.write_i2c_block_data(self.address, REG_MODE_CONFIG, [0x80])
    
    def reset(self):
        """Reset the device - clears all settings"""
        if self.bus:
            self.bus.write_i2c_block_data(self.address, REG_MODE_CONFIG, [0x40])
    
    def setup(self, led_mode=0x03):
        """
        Setup device with optimal values for heart rate and SpO2 measurement
        
        Args:
            led_mode: LED mode (0x02=RED only, 0x03=RED+IR SpO2, 0x07=multi-LED)
        """
        if not self.bus:
            return
            
        # INTR setting - Enable FIFO almost full & PPG ready interrupts
        self.bus.write_i2c_block_data(self.address, REG_INTR_ENABLE_1, [0xc0])
        self.bus.write_i2c_block_data(self.address, REG_INTR_ENABLE_2, [0x00])
        
        # FIFO pointers reset
        self.bus.write_i2c_block_data(self.address, REG_FIFO_WR_PTR, [0x00])
        self.bus.write_i2c_block_data(self.address, REG_OVF_COUNTER, [0x00])
        self.bus.write_i2c_block_data(self.address, REG_FIFO_RD_PTR, [0x00])
        
        # FIFO Configuration: sample avg=4, rollover=false, almost full=17
        self.bus.write_i2c_block_data(self.address, REG_FIFO_CONFIG, [0x4f])
        
        # Mode Configuration: SpO2 mode or multi-LED
        self.bus.write_i2c_block_data(self.address, REG_MODE_CONFIG, [led_mode])
        
        # SpO2 Configuration: ADC range=4096nA, sample rate=100Hz, LED pulse-width=411uS
        self.bus.write_i2c_block_data(self.address, REG_SPO2_CONFIG, [0x27])
        
        # LED pulse amplitudes - ~7mA for LED1 and LED2
        self.bus.write_i2c_block_data(self.address, REG_LED1_PA, [0x24])
        self.bus.write_i2c_block_data(self.address, REG_LED2_PA, [0x24])
        
        # Pilot LED amplitude - ~25mA
        self.bus.write_i2c_block_data(self.address, REG_PILOT_PA, [0x7f])
    
    def set_config(self, reg, value):
        """Set configuration register"""
        if self.bus:
            self.bus.write_i2c_block_data(self.address, reg, value)
    
    def get_data_present(self):
        """Get number of samples available in FIFO"""
        if not self.bus:
            return 0
            
        read_ptr = self.bus.read_byte_data(self.address, REG_FIFO_RD_PTR)
        write_ptr = self.bus.read_byte_data(self.address, REG_FIFO_WR_PTR)
        
        if read_ptr == write_ptr:
            return 0
        else:
            num_samples = write_ptr - read_ptr
            # Account for pointer wrap around
            if num_samples < 0:
                num_samples += 32
            return num_samples
    
    def read_fifo(self):
        """
        Read one sample from FIFO data register
        
        Returns:
            Tuple[int, int]: (red_led, ir_led) values or (None, None) if error
        """
        if not self.bus:
            return None, None
            
        try:
            # Read interrupt status registers (values discarded)
            reg_INTR1 = self.bus.read_i2c_block_data(self.address, REG_INTR_STATUS_1, 1)
            reg_INTR2 = self.bus.read_i2c_block_data(self.address, REG_INTR_STATUS_2, 1)
            
            # Read 6-byte FIFO data
            d = self.bus.read_i2c_block_data(self.address, REG_FIFO_DATA, 6)
            
            # Extract 18-bit values and mask MSB [23:18]
            red_led = (d[0] << 16 | d[1] << 8 | d[2]) & 0x03FFFF
            ir_led = (d[3] << 16 | d[4] << 8 | d[5]) & 0x03FFFF
            
            return red_led, ir_led
            
        except Exception as e:
            return None, None
    
    def read_sequential(self, amount=100):
        """
        Read multiple samples sequentially - blocking function
        
        Args:
            amount: Number of samples to read
            
        Returns:
            Tuple[List[int], List[int]]: (red_buffer, ir_buffer)
        """
        red_buf = []
        ir_buf = []
        count = amount
        
        while count > 0:
            num_bytes = self.get_data_present()
            while num_bytes > 0:
                red, ir = self.read_fifo()
                if red is not None and ir is not None:
                    red_buf.append(red)
                    ir_buf.append(ir)
                    num_bytes -= 1
                    count -= 1
                else:
                    break
        
        return red_buf, ir_buf


# ========================================
# Heart Rate Calculation - Tích hợp trực tiếp từ hrcalc.py
# ========================================

# Heart rate calculation constants
SAMPLE_FREQ = 25  # 25 samples per second
MA_SIZE = 4  # Moving average size - DO NOT CHANGE
BUFFER_SIZE = 100  # Sampling frequency * 4


class HRCalculator:
    """
    Heart Rate and SpO2 Calculator - Tích hợp trực tiếp từ hrcalc.py
    Calculates HR and SpO2 by detecting PPG peaks and AC/DC ratios
    """
    
    @staticmethod
    def calc_hr_and_spo2(ir_data, red_data):
        """
        Calculate heart rate and SpO2 from IR and RED data
        
        Args:
            ir_data: IR LED data array
            red_data: RED LED data array
            
        Returns:
            Tuple[float, bool, float, bool]: (hr, hr_valid, spo2, spo2_valid)
        """
        # Convert to numpy arrays
        ir_data = np.array(ir_data)
        red_data = np.array(red_data)
        
        # Get DC mean for IR
        ir_mean = int(np.mean(ir_data))
        
        # Remove DC mean and invert signal for peak detection
        x = -1 * (ir_data - ir_mean)
        
        # Apply 4-point moving average
        for i in range(x.shape[0] - MA_SIZE):
            x[i] = np.sum(x[i:i+MA_SIZE]) / MA_SIZE
        
        # Calculate adaptive threshold
        n_th = int(np.mean(x))
        n_th = max(30, min(60, n_th))  # Clamp between 30-60
        
        # Find peaks (valleys in inverted signal)
        ir_valley_locs, n_peaks = HRCalculator.find_peaks(x, BUFFER_SIZE, n_th, 4, 15)
        
        # Calculate heart rate
        peak_interval_sum = 0
        if n_peaks >= 2:
            for i in range(1, n_peaks):
                peak_interval_sum += (ir_valley_locs[i] - ir_valley_locs[i-1])
            peak_interval_sum = int(peak_interval_sum / (n_peaks - 1))
            hr = int(SAMPLE_FREQ * 60 / peak_interval_sum)
            hr_valid = True
        else:
            hr = -999  # Unable to calculate - too few peaks
            hr_valid = False
        
        # Calculate SpO2
        exact_ir_valley_locs_count = n_peaks
        
        # Validate valley locations
        for i in range(exact_ir_valley_locs_count):
            if ir_valley_locs[i] > BUFFER_SIZE:
                spo2 = -999  # Invalid - valley location out of range
                spo2_valid = False
                return hr, hr_valid, spo2, spo2_valid
        
        # Calculate AC/DC ratios for SpO2
        i_ratio_count = 0
        ratio = []
        
        # Find max values between valley locations
        for k in range(exact_ir_valley_locs_count-1):
            red_dc_max = -16777216
            ir_dc_max = -16777216
            red_dc_max_index = -1
            ir_dc_max_index = -1
            
            if ir_valley_locs[k+1] - ir_valley_locs[k] > 3:
                # Find maximum values in current segment
                for i in range(ir_valley_locs[k], ir_valley_locs[k+1]):
                    if ir_data[i] > ir_dc_max:
                        ir_dc_max = ir_data[i]
                        ir_dc_max_index = i
                    if red_data[i] > red_dc_max:
                        red_dc_max = red_data[i]
                        red_dc_max_index = i
                
                # Calculate AC components (subtract linear DC)
                red_ac = int((red_data[ir_valley_locs[k+1]] - red_data[ir_valley_locs[k]]) * 
                           (red_dc_max_index - ir_valley_locs[k]))
                red_ac = red_data[ir_valley_locs[k]] + int(red_ac / (ir_valley_locs[k+1] - ir_valley_locs[k]))
                red_ac = red_data[red_dc_max_index] - red_ac
                
                ir_ac = int((ir_data[ir_valley_locs[k+1]] - ir_data[ir_valley_locs[k]]) * 
                          (ir_dc_max_index - ir_valley_locs[k]))
                ir_ac = ir_data[ir_valley_locs[k]] + int(ir_ac / (ir_valley_locs[k+1] - ir_valley_locs[k]))
                ir_ac = ir_data[ir_dc_max_index] - ir_ac
                
                # Calculate ratio
                nume = red_ac * ir_dc_max
                denom = ir_ac * red_dc_max
                
                if (denom > 0 and i_ratio_count < 5) and nume != 0:
                    # Handle overflow with bit masking for 32-bit compatibility
                    ratio.append(int(((nume * 100) & 0xffffffff) / denom))
                    i_ratio_count += 1
        
        # Use median ratio for stability
        ratio = sorted(ratio)
        mid_index = int(i_ratio_count / 2)
        
        ratio_ave = 0
        if mid_index > 1:
            ratio_ave = int((ratio[mid_index-1] + ratio[mid_index])/2)
        else:
            if len(ratio) != 0:
                ratio_ave = ratio[mid_index]
        
        # Convert ratio to SpO2 percentage
        if ratio_ave > 2 and ratio_ave < 184:
            # SpO2 calibration formula
            spo2 = -45.060 * (ratio_ave**2) / 10000.0 + 30.054 * ratio_ave / 100.0 + 94.845
            spo2_valid = True
        else:
            spo2 = -999
            spo2_valid = False
        
        return hr, hr_valid, spo2, spo2_valid
    
    @staticmethod
    def find_peaks(x, size, min_height, min_dist, max_num):
        """
        Find at most MAX_NUM peaks above MIN_HEIGHT separated by at least MIN_DISTANCE
        
        Args:
            x: Signal data
            size: Data size
            min_height: Minimum peak height
            min_dist: Minimum distance between peaks
            max_num: Maximum number of peaks
            
        Returns:
            Tuple[List[int], int]: (peak_locations, num_peaks)
        """
        ir_valley_locs, n_peaks = HRCalculator.find_peaks_above_min_height(x, size, min_height, max_num)
        ir_valley_locs, n_peaks = HRCalculator.remove_close_peaks(n_peaks, ir_valley_locs, x, min_dist)
        n_peaks = min([n_peaks, max_num])
        return ir_valley_locs, n_peaks
    
    @staticmethod
    def find_peaks_above_min_height(x, size, min_height, max_num):
        """Find all peaks above minimum height"""
        i = 0
        n_peaks = 0
        ir_valley_locs = []
        
        while i < size - 1:
            if x[i] > min_height and x[i] > x[i-1]:  # Left edge of potential peak
                n_width = 1
                # Find flat peaks
                while i + n_width < size - 1 and x[i] == x[i+n_width]:
                    n_width += 1
                # Right edge of peak
                if x[i] > x[i+n_width] and n_peaks < max_num:
                    ir_valley_locs.append(i)
                    n_peaks += 1
                    i += n_width + 1
                else:
                    i += n_width
            else:
                i += 1
        
        return ir_valley_locs, n_peaks
    
    @staticmethod
    def remove_close_peaks(n_peaks, ir_valley_locs, x, min_dist):
        """Remove peaks separated by less than minimum distance"""
        # Sort peaks by height (descending)
        sorted_indices = sorted(ir_valley_locs, key=lambda i: x[i])
        sorted_indices.reverse()
        
        # Remove close peaks
        i = -1
        while i < n_peaks:
            old_n_peaks = n_peaks
            n_peaks = i + 1
            j = i + 1
            while j < old_n_peaks:
                n_dist = (sorted_indices[j] - sorted_indices[i]) if i != -1 else (sorted_indices[j] + 1)
                if n_dist > min_dist or n_dist < -1 * min_dist:
                    sorted_indices[n_peaks] = sorted_indices[j]
                    n_peaks += 1
                j += 1
            i += 1
        
        # Sort final peaks by position
        sorted_indices[:n_peaks] = sorted(sorted_indices[:n_peaks])
        return sorted_indices, n_peaks


class MAX30102Sensor(BaseSensor):
    """
    Driver cho MAX30102 heart rate và SpO2 sensor với thuật toán lọc tối ưu
    
    Attributes:
        led_mode (int): LED mode (1=RED, 2=RED+IR, 3=RED+IR+GREEN)
        pulse_amplitude_red (int): LED pulse amplitude cho RED (0x00-0xFF)
        pulse_amplitude_ir (int): LED pulse amplitude cho IR (0x00-0xFF)
        sample_rate (int): Sample rate (Hz)
        buffer_size (int): Buffer size cho calculation
        ir_threshold (int): Threshold để detect finger
        max30102_instance: MAX30102 hardware instance
        ir_buffer (deque): Circular buffer cho IR data
        red_buffer (deque): Circular buffer cho RED data
        
        # Filtered data buffers
        ir_filtered_buffer (deque): Lọc bandpass cho IR
        red_filtered_buffer (deque): Lọc bandpass cho RED
        
        # Measurement results
        heart_rate (float): Nhịp tim hiện tại (BPM)
        spo2 (float): SpO2 hiện tại (%)
        finger_detected (bool): Trạng thái phát hiện ngón tay
        hr_valid (bool): Validity của heart rate measurement
        spo2_valid (bool): Validity của SpO2 measurement
        
        # Measurement history for filtering
        hr_history (List[float]): Lịch sử nhịp tim để lọc median
        spo2_history (List[float]): Lịch sử SpO2 để lọc median
        
        # Filter parameters
        lowpass_alpha (float): Hệ số lọc thông thấp
        median_window_size (int): Kích thước cửa sổ lọc median
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
        self.sample_rate = config.get('sample_rate', 100)  # Hz
        
        # Buffer and processing settings
        self.buffer_size = config.get('buffer_size', 200)  # Larger buffer for better analysis
        self.ir_threshold = config.get('ir_threshold', 50000)
        self.min_readings_for_calc = config.get('min_readings_for_calc', 100)
        
        # Hardware instance
        self.max30102_instance = None
        
        # Raw data buffers
        self.ir_buffer = deque(maxlen=self.buffer_size)
        self.red_buffer = deque(maxlen=self.buffer_size)
        
        # Filtered data buffers
        self.ir_filtered_buffer = deque(maxlen=self.buffer_size)
        self.red_filtered_buffer = deque(maxlen=self.buffer_size)
        
        # Current measurements
        self.heart_rate = 0.0
        self.spo2 = 0.0
        self.finger_detected = False
        self.hr_valid = False
        self.spo2_valid = False
        self.readings_count = 0
        
        # History for median filtering
        self.hr_history = deque(maxlen=5)  # Keep last 5 HR measurements
        self.spo2_history = deque(maxlen=5)  # Keep last 5 SpO2 measurements
        
        # Filter parameters
        self.lowpass_alpha = 0.1  # Low-pass filter coefficient
        self.median_window_size = 5
        self.dc_removal_alpha = 0.95  # DC removal filter coefficient
        self.ir_dc_value = 0.0
        self.red_dc_value = 0.0
        
        # Signal quality metrics
        self.signal_quality_ir = 0.0
        self.signal_quality_red = 0.0
        
        # Peak detection parameters
        self.min_peak_distance = 20  # Minimum distance between peaks (samples)
        self.peak_threshold_factor = 0.3  # Peak threshold as fraction of signal range
    
    def initialize(self) -> bool:
        """
        Initialize MAX30102 sensor hardware với tích hợp driver
        
        Returns:
            bool: True if initialization successful
        """
        try:
            # Initialize MAX30102 hardware với tích hợp driver
            self.max30102_instance = MAX30102Hardware(channel=1, address=0x57)
            
            # Configure MAX30102 settings
            self.max30102_instance.setup(led_mode=self.led_mode)
            
            # Set LED amplitudes to high values for better signal
            self.max30102_instance.set_config(REG_LED1_PA, [self.pulse_amplitude_red])
            self.max30102_instance.set_config(REG_LED2_PA, [self.pulse_amplitude_ir])
            
            # Configure sample rate and ADC range for optimal performance
            # 0x27 = SPO2_ADC_RGE=4096, SPO2_SR=100Hz, LED_PW=411us
            self.max30102_instance.set_config(REG_SPO2_CONFIG, [0x27])
            
            # Force mode to ensure LEDs are active
            self.max30102_instance.set_config(REG_MODE_CONFIG, [self.led_mode])
            
            self.logger.info("MAX30102 sensor initialized successfully với tích hợp driver")
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
            
            # Debug: check for data variation
            if len(ir_data) > 1:
                ir_variation = np.std(ir_data)
                ir_range = max(ir_data) - min(ir_data)
                self.logger.debug(f"FIFO read: {len(ir_data)} samples, IR_std={ir_variation:.1f}, IR_range={ir_range}")
                if ir_variation == 0:
                    self.logger.warning(f"No variation in FIFO data! All IR values: {ir_data[:5]}")
            
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
        Process RED/IR data với thuật toán lọc tối ưu
        
        Args:
            raw_data: Raw RED and IR data
            
        Returns:
            Dict with processed heart rate and SpO2 data or None if error
        """
        try:
            red_data = raw_data['red']
            ir_data = raw_data['ir']
            
            # Add new data to raw buffers
            self.red_buffer.extend(red_data)
            self.ir_buffer.extend(ir_data)
            
            self.readings_count += len(ir_data)
            
            # Check finger detection với adaptive threshold
            # Use historical buffer data for better variation detection
            if len(self.ir_buffer) >= 10:
                # Use last 10 samples from buffer for finger detection
                buffer_data = list(self.ir_buffer)[-10:]
                ir_mean = np.mean(buffer_data) 
                self.finger_detected = self._detect_finger_advanced(buffer_data)
            else:
                # Fallback to current batch if buffer not full enough
                ir_mean = np.mean(ir_data) if len(ir_data) > 0 else 0
                self.finger_detected = self._detect_finger_advanced(ir_data)
            
            # Update signal quality
            self._update_signal_quality()
            
            if not self.finger_detected:
                # Reset values when finger not detected
                self._reset_measurements()
                
                return {
                    'heart_rate': self.heart_rate,
                    'spo2': self.spo2,
                    'finger_detected': self.finger_detected,
                    'hr_valid': self.hr_valid,
                    'spo2_valid': self.spo2_valid,
                    'signal_quality_ir': 0.0,
                    'signal_quality_red': 0.0,
                    'ir_mean': ir_mean,
                    'status': 'no_finger',
                    'debug_ir_data': ir_data  # For debugging
                }
            
            # Apply advanced filtering
            if len(self.ir_buffer) >= 50:  # Minimum data for filtering
                self._apply_advanced_filtering()
            
            # Calculate HR/SpO2 với advanced algorithms
            if len(self.ir_filtered_buffer) >= self.min_readings_for_calc:
                self._calculate_hr_spo2_advanced()
            
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
                'sensor_type': 'MAX30102',
                'debug_ir_data': ir_data  # For debugging finger detection
            }
            
            return processed_data
            
        except Exception as e:
            self.logger.error(f"Failed to process MAX30102 data: {e}")
            return None
    
    def _detect_finger_advanced(self, ir_data: List[int]) -> bool:
        """
        Improved finger detection - prioritize IR value over variation
        
        Args:
            ir_data: IR sensor data
            
        Returns:
            bool: True if finger detected
        """
        try:
            if len(ir_data) == 0:
                return False
                
            ir_mean = np.mean(ir_data)
            ir_std = np.std(ir_data)
            ir_range = np.max(ir_data) - np.min(ir_data) if len(ir_data) > 1 else 0
            
            # Debug: log values để hiểu sensor behavior
            self.logger.debug(f"Finger detection: IR_mean={ir_mean:.0f}, IR_std={ir_std:.0f}, IR_range={ir_range:.0f}, threshold={self.ir_threshold}")
            
            # STRATEGY 1: Primary finger detection dựa trên IR value cao
            # Khi ngón tay đặt lên, IR tăng đáng kể so với baseline
            finger_present_by_ir = ir_mean > self.ir_threshold
            
            # STRATEGY 2: Pulse detection cho established finger
            # Chỉ yêu cầu variation khi đã có finger established
            has_variation = ir_std > 5 or ir_range > 5  # Very low threshold for any movement
            
            # STRATEGY 3: Check against too much noise
            not_too_noisy = ir_std < 5000  # High noise limit
            
            # DECISION LOGIC với priority:
            # 1. Nếu IR cao đáng kể → finger detected ngay (không cần variation)
            # 2. Nếu có variation nhỏ → cũng OK (có thể là pulse bắt đầu)
            
            if finger_present_by_ir:
                # IR cao → finger detected, không quan tâm variation ban đầu
                finger_detected = True
                detection_reason = "high_ir_value"
            elif has_variation and not_too_noisy:
                # Có variation + không quá noisy → có thể là finger đang đặt
                finger_detected = True 
                detection_reason = "variation_detected"
            else:
                finger_detected = False
                detection_reason = "insufficient_signal"
            
            # Enhanced logging cho debugging
            if finger_detected:
                self.logger.debug(f"Finger DETECTED ({detection_reason}): IR={ir_mean:.0f}, Std={ir_std:.0f}, Range={ir_range:.0f}")
            else:
                reasons = []
                if not finger_present_by_ir:
                    reasons.append(f"IR_mean({ir_mean:.0f}) <= {self.ir_threshold}")
                if not has_variation:
                    reasons.append(f"No_variation(std={ir_std:.0f}, range={ir_range:.0f})")
                if not not_too_noisy:
                    reasons.append(f"Too_noisy(std={ir_std:.0f})")
                
                self.logger.debug(f"Finger NOT detected: {', '.join(reasons)}")
            
            return finger_detected
            
        except Exception as e:
            self.logger.error(f"Error in finger detection: {e}")
            return False
    
    def _apply_advanced_filtering(self):
        """
        Apply advanced filtering techniques to raw data
        """
        try:
            # Get recent data
            ir_raw = np.array(list(self.ir_buffer)[-100:])
            red_raw = np.array(list(self.red_buffer)[-100:])
            
            if len(ir_raw) < 50:
                return
            
            # 1. DC Component Removal với adaptive filtering
            ir_filtered = self._remove_dc_component(ir_raw)
            red_filtered = self._remove_dc_component(red_raw)
            
            # 2. Bandpass filter (0.5 - 5 Hz) for heart rate frequency range
            ir_filtered = self._apply_bandpass_filter(ir_filtered)
            red_filtered = self._apply_bandpass_filter(red_filtered)
            
            # 3. Moving average filter để smooth signal
            ir_filtered = self._apply_moving_average(ir_filtered, window=5)
            red_filtered = self._apply_moving_average(red_filtered, window=5)
            
            # 4. Outlier removal
            ir_filtered = self._remove_outliers(ir_filtered)
            red_filtered = self._remove_outliers(red_filtered)
            
            # Update filtered buffers
            if len(ir_filtered) > 0:
                self.ir_filtered_buffer.extend(ir_filtered[-50:])  # Keep last 50 filtered samples
                self.red_filtered_buffer.extend(red_filtered[-50:])
                
        except Exception as e:
            self.logger.error(f"Error in advanced filtering: {e}")
    
    def _remove_dc_component(self, data: np.ndarray) -> np.ndarray:
        """
        Remove DC component using high-pass filter
        
        Args:
            data: Input signal
            
        Returns:
            DC-removed signal
        """
        try:            
            # Simple DC removal by subtracting mean
            dc_mean = np.mean(data)
            return data - dc_mean
            
        except Exception as e:
            self.logger.error(f"Error removing DC component: {e}")
            return data
    
    def _apply_bandpass_filter(self, data: np.ndarray) -> np.ndarray:
        """
        Apply bandpass filter (0.5 - 5 Hz) for heart rate range
        
        Args:
            data: Input signal
            
        Returns:
            Filtered signal
        """
        try:
            if len(data) < 20:
                return data
                
            # Design Butterworth bandpass filter
            nyquist = self.sample_rate / 2
            low_cutoff = 0.5 / nyquist   # 0.5 Hz (30 BPM)
            high_cutoff = 5.0 / nyquist  # 5 Hz (300 BPM)
            
            # Ensure cutoff frequencies are valid
            low_cutoff = max(0.01, min(0.49, low_cutoff))
            high_cutoff = max(0.02, min(0.49, high_cutoff))
            
            if high_cutoff <= low_cutoff:
                high_cutoff = low_cutoff + 0.1
            
            # Use simple bandpass filter implementation
            return self._simple_bandpass_filter(data)
                
        except Exception as e:
            self.logger.error(f"Error in bandpass filter: {e}")
            return data
    
    def _simple_bandpass_filter(self, data: np.ndarray) -> np.ndarray:
        """
        Simple bandpass filter implementation
        
        Args:
            data: Input signal
            
        Returns:
            Filtered signal
        """
        try:
            # Simple moving average for low-pass
            window = 5
            if len(data) < window:
                return data
                
            filtered = np.convolve(data, np.ones(window)/window, mode='same')
            
            # High-pass by subtracting longer-term average
            long_window = min(20, len(data) // 2)
            if long_window > window:
                long_avg = np.convolve(data, np.ones(long_window)/long_window, mode='same')
                filtered = filtered - long_avg * 0.5
                
            return filtered
            
        except Exception as e:
            self.logger.error(f"Error in simple bandpass filter: {e}")
            return data
    
    def _apply_moving_average(self, data: np.ndarray, window: int = 5) -> np.ndarray:
        """
        Apply moving average filter
        
        Args:
            data: Input signal
            window: Window size
            
        Returns:
            Smoothed signal
        """
        try:
            if len(data) < window:
                return data
                
            return np.convolve(data, np.ones(window)/window, mode='same')
            
        except Exception as e:
            self.logger.error(f"Error in moving average: {e}")
            return data
    
    def _remove_outliers(self, data: np.ndarray, factor: float = 2.5) -> np.ndarray:
        """
        Remove outliers using IQR method
        
        Args:
            data: Input signal
            factor: IQR multiplication factor for outlier detection
            
        Returns:
            Signal with outliers removed
        """
        try:
            if len(data) < 10:
                return data
                
            Q1 = np.percentile(data, 25)
            Q3 = np.percentile(data, 75)
            IQR = Q3 - Q1
            
            lower_bound = Q1 - factor * IQR
            upper_bound = Q3 + factor * IQR
            
            # Replace outliers with median
            median_val = np.median(data)
            cleaned = np.where((data < lower_bound) | (data > upper_bound), median_val, data)
            
            return cleaned
            
        except Exception as e:
            self.logger.error(f"Error removing outliers: {e}")
            return data
    
    def _calculate_hr_spo2_advanced(self):
        """
        Calculate HR and SpO2 using tích hợp HRCalculator algorithms
        """
        try:
            if len(self.ir_buffer) < 100 or len(self.red_buffer) < 100:
                return
                
            # Get raw data for HRCalculator (works better with raw data)
            ir_data = list(self.ir_buffer)[-100:]  # Last 100 samples
            red_data = list(self.red_buffer)[-100:]
            
            # Use tích hợp HRCalculator để tính HR và SpO2
            hr_new, hr_valid_new, spo2_new, spo2_valid_new = HRCalculator.calc_hr_and_spo2(ir_data, red_data)
            
            # Validate và cập nhật measurements
            if hr_valid_new and hr_new > 0:
                # Additional validation cho HR
                if self._validate_heart_rate_advanced(hr_new):
                    self.hr_history.append(hr_new)
                    # Use median filtering for stability
                    if len(self.hr_history) >= 3:
                        self.heart_rate = np.median(list(self.hr_history))
                        self.hr_valid = True
                    else:
                        self.heart_rate = hr_new
                        self.hr_valid = True
                    
                    self.logger.debug(f"HR calculated: {hr_new:.1f} BPM (filtered: {self.heart_rate:.1f})")
                else:
                    self.logger.debug(f"HR validation failed: {hr_new}")
            else:
                self.logger.debug("HR calculation invalid từ HRCalculator")
            
            if spo2_valid_new and spo2_new > 0:
                # Additional validation cho SpO2
                if self._validate_spo2_advanced(spo2_new):
                    self.spo2_history.append(spo2_new)
                    # Use median filtering for stability
                    if len(self.spo2_history) >= 3:
                        self.spo2 = np.median(list(self.spo2_history))
                        self.spo2_valid = True
                    else:
                        self.spo2 = spo2_new
                        self.spo2_valid = True
                    
                    self.logger.debug(f"SpO2 calculated: {spo2_new:.1f}% (filtered: {self.spo2:.1f}%)")
                else:
                    self.logger.debug(f"SpO2 validation failed: {spo2_new}")
            else:
                self.logger.debug("SpO2 calculation invalid từ HRCalculator")
                    
        except Exception as e:
            self.logger.error(f"Error in tích hợp HR/SpO2 calculation: {e}")
    
    def _calculate_heart_rate_peaks(self, ir_data: np.ndarray) -> float:
        """
        Calculate heart rate using peak detection
        
        Args:
            ir_data: Filtered IR data
            
        Returns:
            Heart rate in BPM
        """
        try:
            if len(ir_data) < 50:
                return 0.0
            
            # Find peaks with minimum distance
            peak_threshold = np.std(ir_data) * self.peak_threshold_factor
            min_peak_height = np.mean(ir_data) + peak_threshold
            
            # Use simple peak detection method
            peaks = self._find_peaks_simple(ir_data, min_peak_height, self.min_peak_distance)
            
            if len(peaks) < 2:
                return 0.0
            
            # Calculate average interval between peaks
            peak_intervals = np.diff(peaks)
            avg_interval = np.median(peak_intervals)  # Use median for robustness
            
            # Convert to BPM
            heart_rate = (self.sample_rate * 60.0) / avg_interval
            
            return round(heart_rate, 1)
            
        except Exception as e:
            self.logger.error(f"Error calculating HR from peaks: {e}")
            return 0.0
    
    def _find_peaks_simple(self, data: np.ndarray, min_height: float, min_distance: int) -> np.ndarray:
        """
        Simple peak detection implementation
        
        Args:
            data: Input signal
            min_height: Minimum peak height
            min_distance: Minimum distance between peaks
            
        Returns:
            Array of peak indices
        """
        try:
            peaks = []
            last_peak = -min_distance
            
            for i in range(1, len(data) - 1):
                if (data[i] > data[i-1] and 
                    data[i] > data[i+1] and 
                    data[i] > min_height and
                    i - last_peak >= min_distance):
                    peaks.append(i)
                    last_peak = i
            
            return np.array(peaks)
            
        except Exception as e:
            self.logger.error(f"Error in simple peak detection: {e}")
            return np.array([])
    
    def _calculate_spo2_ratio(self, ir_data: np.ndarray, red_data: np.ndarray) -> float:
        """
        Calculate SpO2 using AC/DC ratio method
        
        Args:
            ir_data: Filtered IR data
            red_data: Filtered RED data
            
        Returns:
            SpO2 percentage
        """
        try:
            if len(ir_data) < 50 or len(red_data) < 50:
                return 0.0
            
            # Calculate AC and DC components
            ir_ac = np.std(ir_data)
            ir_dc = np.mean(ir_data)
            red_ac = np.std(red_data)
            red_dc = np.mean(red_data)
            
            # Avoid division by zero
            if ir_dc == 0 or red_dc == 0 or ir_ac == 0 or red_ac == 0:
                return 0.0
            
            # Calculate R ratio
            r_ratio = (red_ac / red_dc) / (ir_ac / ir_dc)
            
            # Apply calibration formula (empirical)
            # This is a simplified version - may need calibration with reference oximeter
            if r_ratio > 0.5 and r_ratio < 3.0:
                spo2 = 110 - 25 * r_ratio
            else:
                return 0.0
            
            return round(max(0, min(100, spo2)), 1)
            
        except Exception as e:
            self.logger.error(f"Error calculating SpO2 ratio: {e}")
            return 0.0
    
    def _validate_heart_rate_advanced(self, hr: float) -> bool:
        """
        Advanced heart rate validation with trend analysis
        
        Args:
            hr: Heart rate to validate
            
        Returns:
            bool: True if valid
        """
        try:
            # Basic range check
            if not (40 <= hr <= 200):
                return False
            
            # Check against history for sudden changes
            if len(self.hr_history) > 0:
                last_hr = self.hr_history[-1]
                # Allow maximum 30 BPM change between readings
                if abs(hr - last_hr) > 30:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating HR: {e}")
            return False
    
    def _validate_spo2_advanced(self, spo2: float) -> bool:
        """
        Advanced SpO2 validation with trend analysis
        
        Args:
            spo2: SpO2 to validate
            
        Returns:
            bool: True if valid
        """
        try:
            # Basic range check
            if not (70 <= spo2 <= 100):
                return False
            
            # Check against history for sudden changes
            if len(self.spo2_history) > 0:
                last_spo2 = self.spo2_history[-1]
                # Allow maximum 10% change between readings
                if abs(spo2 - last_spo2) > 10:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating SpO2: {e}")
            return False
    
    def _reset_measurements(self):
        """
        Reset all measurements when finger not detected
        """
        self.heart_rate = 0.0
        self.spo2 = 0.0
        self.hr_valid = False
        self.spo2_valid = False
        self.hr_history.clear()
        self.spo2_history.clear()
    
    def _update_signal_quality(self):
        """
        Update signal quality metrics based on current buffer data
        """
        try:
            if len(self.ir_buffer) > 10:
                ir_array = np.array(list(self.ir_buffer)[-50:])  # Use last 50 samples
                red_array = np.array(list(self.red_buffer)[-50:])
                
                # Calculate signal quality based on SNR and stability
                ir_snr = self._calculate_snr(ir_array)
                red_snr = self._calculate_snr(red_array)
                
                self.signal_quality_ir = max(0, min(100, ir_snr))
                self.signal_quality_red = max(0, min(100, red_snr))
                    
        except Exception as e:
            self.logger.error(f"Error updating signal quality: {e}")
    
    def _calculate_snr(self, data: np.ndarray) -> float:
        """
        Calculate Signal-to-Noise Ratio
        
        Args:
            data: Signal data
            
        Returns:
            SNR value (0-100)
        """
        try:
            if len(data) < 10:
                return 0.0
            
            # Calculate signal power (variance of AC component)
            signal_power = np.var(data)
            
            # Estimate noise power (high frequency components)
            if len(data) > 20:
                # Simple noise estimation using differences
                noise_power = np.var(np.diff(data))
            else:
                noise_power = signal_power * 0.1  # Assume 10% noise
            
            if noise_power == 0:
                return 100.0
            
            snr_ratio = signal_power / noise_power
            
            # Convert to 0-100 scale
            snr_db = 10 * np.log10(max(1e-10, snr_ratio))
            snr_normalized = max(0, min(100, snr_db * 2))  # Scale factor
            
            return snr_normalized
            
        except Exception as e:
            self.logger.error(f"Error calculating SNR: {e}")
            return 0.0
    
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
        Reset all data buffers and measurements
        """
        self.ir_buffer.clear()
        self.red_buffer.clear()
        self.ir_filtered_buffer.clear()
        self.red_filtered_buffer.clear()
        self.hr_history.clear()
        self.spo2_history.clear()
        self.readings_count = 0
        self._reset_measurements()
        self.logger.info("MAX30102 buffers and measurements reset")
    
    def set_led_amplitude(self, red_amplitude: int, ir_amplitude: int) -> bool:
        """
        Set LED pulse amplitudes sử dụng tích hợp hardware driver
        
        Args:
            red_amplitude: RED LED amplitude (0x00-0xFF)
            ir_amplitude: IR LED amplitude (0x00-0xFF)
            
        Returns:
            bool: True if successful
        """
        try:
            self.pulse_amplitude_red = max(0, min(255, red_amplitude))
            self.pulse_amplitude_ir = max(0, min(255, ir_amplitude))
            
            # Apply settings trực tiếp đến hardware qua tích hợp driver
            if self.max30102_instance:
                self.max30102_instance.set_config(REG_LED1_PA, [self.pulse_amplitude_red])
                self.max30102_instance.set_config(REG_LED2_PA, [self.pulse_amplitude_ir])
            
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
            except Exception as e:
                self.logger.error(f"Error shutting down MAX30102: {e}")
                
        self.reset_buffers()
        return result
    
    def turn_off_red_led(self) -> bool:
        """
        Turn off RED LED after measurement sử dụng tích hợp driver
        
        Returns:
            bool: True if successful
        """
        try:
            if self.max30102_instance:
                # Set RED LED amplitude to 0 để tắt
                self.max30102_instance.set_config(REG_LED1_PA, [0x00])
                self.logger.info("RED LED turned off")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error turning off RED LED: {e}")
            return False
    
    def turn_on_red_led(self) -> bool:
        """
        Turn on RED LED for measurement sử dụng tích hợp driver
        
        Returns:
            bool: True if successful
        """
        try:
            if self.max30102_instance:
                # Restore RED LED amplitude
                self.max30102_instance.set_config(REG_LED1_PA, [self.pulse_amplitude_red])
                self.logger.info("RED LED turned on")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error turning on RED LED: {e}")
            return False
    
    def validate_heart_rate(self, hr: float) -> bool:
        """
        Validate heart rate value (public method)
        
        Args:
            hr: Heart rate value to validate
            
        Returns:
            bool: True if valid
        """
        return self._validate_heart_rate_advanced(hr)
    
    def validate_spo2(self, spo2: float) -> bool:
        """
        Validate SpO2 value (public method)
        
        Args:
            spo2: SpO2 value to validate
            
        Returns:
            bool: True if valid
        """
        return self._validate_spo2_advanced(spo2)
    
    def get_measurement_stability(self) -> Dict[str, float]:
        """
        Get measurement stability metrics
        
        Returns:
            Dictionary with stability metrics
        """
        try:
            hr_stability = 0.0
            spo2_stability = 0.0
            
            if len(self.hr_history) > 1:
                hr_std = np.std(list(self.hr_history))
                hr_mean = np.mean(list(self.hr_history))
                if hr_mean > 0:
                    hr_stability = max(0, min(100, 100 - (hr_std / hr_mean * 100)))
            
            if len(self.spo2_history) > 1:
                spo2_std = np.std(list(self.spo2_history))
                spo2_mean = np.mean(list(self.spo2_history))
                if spo2_mean > 0:
                    spo2_stability = max(0, min(100, 100 - (spo2_std / spo2_mean * 100)))
            
            return {
                'hr_stability': hr_stability,
                'spo2_stability': spo2_stability,
                'hr_history_count': len(self.hr_history),
                'spo2_history_count': len(self.spo2_history)
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating stability: {e}")
            return {'hr_stability': 0.0, 'spo2_stability': 0.0, 
                   'hr_history_count': 0, 'spo2_history_count': 0}


# ========================================
# Integration Summary
# ========================================
"""
MAX30102 Sensor Driver với hoàn toàn tích hợp thư viện:

1. MAX30102Hardware Class:
   - Tích hợp trực tiếp từ max30102.py library
   - Quản lý I2C communication với MAX30102 sensor
   - Register constants và hardware control methods
   - Không phụ thuộc external max30102 library

2. HRCalculator Class:
   - Tích hợp trực tiếp từ hrcalc.py library  
   - Thuật toán peak detection và AC/DC ratio calculation
   - Heart rate và SpO2 calculation algorithms
   - Không phụ thuộc external hrcalc library

3. MAX30102Sensor Class:
   - Sử dụng MAX30102Hardware cho hardware communication
   - Sử dụng HRCalculator cho HR/SpO2 calculations
   - Advanced filtering và validation algorithms
   - Finger detection với realistic thresholds
   - Signal quality assessment
   - Median filtering cho stability

Dependencies chỉ còn lại:
   - smbus: cho I2C communication (system library)
   - numpy: cho signal processing (standard scientific library)
   - collections.deque: cho circular buffers (standard library)
   - typing, logging, time: standard Python libraries
   - base_sensor: project's own base class

Tích hợp hoàn thành - không còn external max30102/hrcalc dependencies!
"""

