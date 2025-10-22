"""
Blood Pressure Sensor Driver
Driver cho cảm biến huyết áp sử dụng phương pháp dao động (oscillometric) với ADC HX710B
"""
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass
import logging
import time
import threading
from .base_sensor import BaseSensor

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

import numpy as np
import statistics
from scipy import signal as scipy_signal

# ==================== QA METRICS DATACLASS ====================

@dataclass
class MeasurementQuality:
    """Measurement quality metrics for diagnostic purposes"""
    adc_timeouts: int = 0           # Count of ADC timeout events
    points_collected: int = 0       # Total data points collected
    points_after_filter: int = 0    # Points after filtering/validation
    signal_noise_ratio: float = 0.0 # SNR estimate (amplitude/noise)
    map_amplitude: float = 0.0      # Peak oscillation amplitude (mmHg)
    deflate_duration_s: float = 0.0 # Actual deflation time (seconds)
    sample_rate_hz: float = 0.0     # Estimated sample rate (Hz)
    max_pressure_reached: float = 0.0  # Peak pressure during inflation (mmHg)
    is_valid: bool = False          # Whether measurement passed QA checks

class BloodPressureSensor(BaseSensor):
    """
    Driver cho cảm biến huyết áp sử dụng oscillometric method với HX710B
    
    **IMPORTANT**: This sensor does NOT use BaseSensor's automatic reading loop.
    Blood pressure measurement is a ONE-SHOT procedure triggered manually via:
      1. start_measurement() - begins inflate→deflate cycle
      2. read_raw_data() - executes full cycle (blocks ~30-60s)
      3. process_data() - calculates BP values
      4. stop_measurement() - aborts and emergency deflates
    
    For GUI integration, run read_raw_data() in a background thread and poll
    get_measurement_status() for progress updates.
    
    Attributes:
        pressure_sensor_type (str): Loại cảm biến áp suất (ví dụ "HX710B")
        pump_gpio (int): GPIO pin điều khiển bơm (GPIO26)
        valve_gpio (int): GPIO pin điều khiển van xả (GPIO16)
        current_pressure (float): Áp suất hiện tại (mmHg)
        oscillation_buffer (List): Buffer cho tín hiệu dao động (không dùng trực tiếp ở đây)
        systolic_bp (float): Huyết áp tâm thu đo được (mmHg)
        diastolic_bp (float): Huyết áp tâm trương đo được (mmHg)
        mean_arterial_pressure (float): Huyết áp động mạch trung bình (mmHg)
        is_measuring (bool): Trạng thái đang đo hay không
    """
    
    # ==================== CONSTANTS ====================
    PUMP_TIMEOUT_S = 30.0              # Max time for inflation (seconds)
    DEFLATE_TIMEOUT_S = 60.0           # Max time for deflation (seconds)
    DEFLATE_ENDPOINT_MMHG = 40.0       # Pressure to end deflation (mmHg)
    STALL_TIMEOUT_S = 5.0              # Max time with no pressure change (seconds)
    STALL_THRESHOLD_MMHG = 0.5         # Min pressure change to consider not stalled (mmHg)
    ADC_READ_INTERVAL_S = 0.1          # Time between ADC reads during pump/deflate (seconds)
    EMERGENCY_DEFLATE_TIME_S = 5.0     # Time to hold valve open for emergency (seconds)
    SAFETY_CHECK_DEFLATE_S = 0.5       # Time to deflate before safety check (seconds)
    ZERO_CALIBRATION_SAMPLES = 20      # Number of samples for zero offset calibration
    
    # ==================== INITIALIZATION & SETUP ====================
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize blood pressure sensor
        Args:
            config: Configuration dictionary for blood pressure sensor
        """
        super().__init__("BloodPressure", config)
        
        # GPIO configuration
        self.pump_gpio = config.get('pump_gpio', 26)   # GPIO26 for pump control
        self.valve_gpio = config.get('valve_gpio', 16)  # GPIO16 for valve control
        
        # Measurement parameters
        self.inflate_target_mmhg = config.get('inflate_target_mmhg', 165)
        self.max_pressure = config.get('max_pressure', 180)
        self.safety_pressure = config.get('safety_pressure', 200)
        self.deflate_rate_mmhg_s = config.get('deflate_rate_mmhg_s', 3.0)
        
        # P1-3: Add parameter validation (was missing)
        self._validate_measurement_params()
        
        # State variables
        self.is_measuring = False
        self.current_pressure = 0.0
        self.systolic_bp = 0.0
        self.diastolic_bp = 0.0
        self.mean_arterial_pressure = 0.0
        self._state = 'idle'
        
        # Valve type configuration (NO = Normally Open, NC = Normally Closed)
        self.valve_is_no = config.get('valve_is_no', True)  # Default: NO (open when GPIO LOW)
        
        # HX710B ADC configuration - UPDATED: Always use config (supports both merged and separate configs)
        self.pressure_sensor_type = config.get('pressure_sensor', "HX710B")
        # Try separate hx710b config first, then fallback to merged config
        hx_conf = config.get('hx710b', config)
        self._dout_pin = hx_conf.get('gpio_dout')
        self._sck_pin = hx_conf.get('gpio_sck')
        # P0-2: Reduce timeout from 1000ms to 200ms for better responsiveness
        self._hx_timeout = hx_conf.get('timeout_ms', 200) / 1000.0
        calib = hx_conf.get('calibration', {})
        self._offset_counts = int(calib.get('offset_counts', 0))
        self._slope = float(calib.get('slope_mmhg_per_count', 0.001))
        # ADC polarity: some modules produce inverted counts/sign; allow override from config
        # If not provided, default to False (not inverted)
        self._adc_inverted = bool(hx_conf.get('adc_inverted', False))
        
        # GPIO setup flag
        self._gpio_initialized = False
        # Last deflation duration (to estimate sample rate)
        self._last_deflate_duration = 0.0
        
        # P1-4: QA metrics tracking (was missing)
        self.measurement_quality = MeasurementQuality()
        
        # P1-5: Separate inflate/deflate phase data (was missing)
        self._inflate_data = []  # Points collected during inflation
        self._deflate_data = []  # Points collected during deflation
        
        # Completion callback for GUI (called when measurement completes)
        self._measurement_callback: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None
    
    def _validate_measurement_params(self) -> None:
        """
        P1-3: Validate measurement parameters for consistency (was missing)
        Raises warnings if config values are out of typical ranges
        """
        if self.inflate_target_mmhg < 100 or self.inflate_target_mmhg > 220:
            self.logger.warning(f"Inflate target {self.inflate_target_mmhg} mmHg out of typical range [100-220]")
        if self.deflate_rate_mmhg_s < 1.0 or self.deflate_rate_mmhg_s > 10.0:
            self.logger.warning(f"Deflate rate {self.deflate_rate_mmhg_s} mmHg/s out of typical range [1-10]")
        if self.safety_pressure < self.inflate_target_mmhg:
            self.logger.warning(f"Safety pressure {self.safety_pressure} < inflate target {self.inflate_target_mmhg}")
    
    def initialize(self) -> bool:
        """
        Initialize blood pressure measurement hardware (GPIO and ADC)
        Returns:
            bool: True if initialization successful
        """
        if GPIO is None:
            self.logger.error("RPi.GPIO not available")
            return False
        try:
            # Use BCM numbering for GPIO
            GPIO.setmode(GPIO.BCM)
            # Setup pump GPIO (output, default LOW)
            GPIO.setup(self.pump_gpio, GPIO.OUT, initial=GPIO.LOW)
            # Setup valve GPIO (output, default LOW)
            GPIO.setup(self.valve_gpio, GPIO.OUT, initial=GPIO.LOW)
            # Setup HX710B ADC pins
            if self._dout_pin is None or self._sck_pin is None:
                self.logger.error("HX710B pins not configured")
                return False
            GPIO.setup(self._dout_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(self._sck_pin, GPIO.OUT, initial=GPIO.LOW)
            
            self._gpio_initialized = True
            self.logger.info(f"Blood pressure GPIO initialized: pump={self.pump_gpio}, valve={self.valve_gpio}, dout={self._dout_pin}, sck={self._sck_pin}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize blood pressure GPIO: {e}")
            return False
    
    # ==================== BASESENSOR OVERRIDE (DISABLE AUTO-LOOP) ====================
    
    def start(self) -> bool:
        """
        Override BaseSensor.start() to DISABLE automatic reading loop.
        Blood pressure measurement is manual-trigger only via start_measurement().
        
        This method only initializes hardware without starting the continuous loop.
        
        Returns:
            bool: True if hardware initialization successful
        """
        if self.is_running:
            self.logger.warning(f"{self.name} sensor is already initialized")
            return True
        
        if not self.initialize():
            self.logger.error(f"Failed to initialize {self.name} sensor hardware")
            return False
        
        # Mark as "running" for compatibility, but DO NOT start reading thread
        self.is_running = True
        self.error_count = 0
        # NOTE: reading_thread is NOT started - BP is manual trigger only
        
        self.logger.info(f"Initialized {self.name} sensor (manual-trigger mode)")
        return True
    
    def stop(self) -> bool:
        """
        Override BaseSensor.stop() to handle manual-trigger mode.
        Stops any ongoing measurement and cleans up hardware.
        
        Returns:
            bool: True if stop successful
        """
        if not self.is_running:
            return True
        
        # Abort any ongoing measurement
        if self.is_measuring:
            self.stop_measurement()
        
        self.is_running = False
        # No reading thread to join in manual mode
        
        self.logger.info(f"Stopped {self.name} sensor")
        return True
    
    def set_measurement_callback(self, callback: Callable[[Optional[Dict[str, Any]]], None]):
        """
        Set callback function to be called when measurement completes.
        Useful for GUI to get notified without polling.
        
        Args:
            callback: Function(result_dict or None) called on completion
        """
        self._measurement_callback = callback
    
    # ==================== HARDWARE CONTROL (GPIO/HX710B) ====================
    
    def start_measurement(self) -> bool:
        """
        Bắt đầu chu trình đo huyết áp
        Returns:
            bool: True if measurement started successfully
        """
        if not self._gpio_initialized:
            self.logger.error("GPIO not initialized")
            return False
        if self.is_measuring:
            self.logger.warning("Measurement already in progress")
            return False
        try:
            # Thực hiện kiểm tra an toàn (hiệu chỉnh offset 0)
            if not self._safety_check():
                self.logger.error("Safety check failed, cannot start measurement")
                return False
            # Reset QA metrics trước mỗi lần đo mới
            self.measurement_quality = MeasurementQuality()
            # Reset phase data
            self._inflate_data = []
            self._deflate_data = []
            # Bắt đầu đo
            self.is_measuring = True
            self._state = 'INFLATE'
            self.current_pressure = 0.0
            self.logger.info("Blood pressure measurement started")
            return True
        except Exception as e:
            self.logger.error(f"Failed to start measurement: {e}")
            return False
    
    def stop_measurement(self) -> bool:
        """
        Dừng chu trình đo huyết áp
        Returns:
            bool: True if measurement stopped successfully
        """
        if not self.is_measuring:
            return True
        try:
            # Emergency deflate toàn bộ ngay lập tức
            self.emergency_deflate()
            self.is_measuring = False
            self._state = 'idle'
            self.logger.info("Blood pressure measurement stopped")
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop measurement: {e}")
            return False
    
    def _pump_on(self) -> None:
        """Turn pump ON (GPIO HIGH)"""
        if self._gpio_initialized:
            GPIO.output(self.pump_gpio, GPIO.HIGH)
            self.logger.debug("Pump ON")
    
    def _pump_off(self) -> None:
        """Turn pump OFF (GPIO LOW)"""
        if self._gpio_initialized:
            GPIO.output(self.pump_gpio, GPIO.LOW)
            self.logger.debug("Pump OFF")
    
    def _valve_open(self) -> None:
        """Open valve (allow airflow)"""
        if self._gpio_initialized:
            gpio_level = GPIO.LOW if self.valve_is_no else GPIO.HIGH
            GPIO.output(self.valve_gpio, gpio_level)
            self.logger.debug(f"Valve OPEN (GPIO {gpio_level})")

    def _valve_close(self) -> None:
        """Close valve (block airflow)"""
        if self._gpio_initialized:
            gpio_level = GPIO.HIGH if self.valve_is_no else GPIO.LOW
            GPIO.output(self.valve_gpio, gpio_level)
            self.logger.debug(f"Valve CLOSED (GPIO {gpio_level})")
    
    def _read_adc_value(self, timeout: float = None) -> Optional[int]:
        """
        Đọc giá trị ADC 24-bit từ HX710B (non-blocking)
        Returns:
            int: raw ADC counts (24-bit signed) or None if timeout
        """
        if GPIO is None or self._dout_pin is None or self._sck_pin is None:
            return None
        if timeout is None:
            timeout = self._hx_timeout
        value = 0
        # Sử dụng khóa để tránh xung đột đọc ADC giữa các thread
        with self.data_lock:
            t0 = time.time()
            # Chờ tín hiệu data-ready (DOUT xuống LOW)
            while GPIO.input(self._dout_pin) == 1:
                if time.time() - t0 > timeout:
                    # P1-4: Track ADC timeouts for QA metrics
                    self.measurement_quality.adc_timeouts += 1
                    return None
            # Đọc 24 bit dữ liệu
            for _ in range(24):
                GPIO.output(self._sck_pin, True)
                bit = GPIO.input(self._dout_pin)
                GPIO.output(self._sck_pin, False)
                value = (value << 1) | bit
            # Gửi xung cho ADC (3 xung để ở chế độ 40SPS)
            for _ in range(3):
                GPIO.output(self._sck_pin, True)
                GPIO.output(self._sck_pin, False)
        # Chuyển dạng two's complement sang giá trị có dấu
        if value & 0x800000:
            value -= 1 << 24
        return value

    
    def _pump_to_pressure(self, target_pressure: float) -> bool:
        """
        Bơm đến áp suất mục tiêu (mmHg)
        Args:
            target_pressure: Target pressure in mmHg
        Returns:
            bool: True if pumping successful, False if aborted or error
        """
        if not self.is_measuring:
            return False
        try:
            self.logger.info(f"Pumping to {target_pressure:.0f} mmHg...")
            self._pump_on()
            self._valve_close()  # Đóng van khi bơm
            start_time = time.time()
            # P1-5: Track inflation phase data separately
            self._inflate_data = []
            # Giữ bơm cho đến khi đạt áp suất mục tiêu hoặc có sự cố
            while self.current_pressure < target_pressure:
                # Kiểm tra hủy đo từ người dùng
                if not self.is_measuring:
                    self.logger.info("Pumping aborted by user")
                    self._pump_off()
                    return False
                # Giới hạn thời gian bơm
                if time.time() - start_time > self.PUMP_TIMEOUT_S:
                    self.logger.error(f"Pump timeout - reached {self.PUMP_TIMEOUT_S}s limit")
                    self._pump_off()
                    return False
                # Kiểm tra áp suất an toàn
                if self.current_pressure >= self.safety_pressure:
                    self.logger.error(f"Safety pressure {self.safety_pressure} mmHg exceeded during inflate")
                    self._pump_off()
                    return False
                # Cập nhật áp suất hiện tại từ cảm biến
                raw = self._read_adc_value(timeout=0.1)
                if raw is not None:
                    # FIXED: Apply polarity correction
                    corrected_counts = raw - self._offset_counts
                    if self._adc_inverted:
                        self.current_pressure = -corrected_counts * self._slope
                    else:
                        self.current_pressure = corrected_counts * self._slope
                    self.current_pressure = max(0.0, self.current_pressure)  # Ensure non-negative
                    # P1-5: Record inflation data for QA
                    self._inflate_data.append(self.current_pressure)
                    # P1-4: Track max pressure reached
                    if self.current_pressure > self.measurement_quality.max_pressure_reached:
                        self.measurement_quality.max_pressure_reached = self.current_pressure
                else:
                    self.logger.warning("ADC timeout during pumping")
                time.sleep(self.ADC_READ_INTERVAL_S)  # Interval between ADC reads
            # Ngừng bơm khi đạt mục tiêu
            self._pump_off()
            self.logger.info(f"Target pressure {target_pressure:.0f} mmHg reached")
            return True
        except Exception as e:
            self.logger.error(f"Pumping failed: {e}")
            self._pump_off()
            return False

    
    def _controlled_deflation(self, deflation_rate: float) -> List[Dict[str, float]]:
        """
        Thực hiện quá trình xả khí có kiểm soát và thu thập dữ liệu áp suất
        Args:
            deflation_rate: Tốc độ xả dự kiến (mmHg/s)
        Returns:
            List of data points (each a dict with 'raw' and 'pressure') thu thập được
        """
        data_points: List[Dict[str, float]] = []
        if not self.is_measuring:
            return data_points
        # Bắt đầu xả khí
        self._state = 'DEFLATE'
        self._valve_open()
        # P1-5: Reset deflate data for this phase
        self._deflate_data = []
        start_time = time.time()
        aborted = False
        last_pressure = self.current_pressure
        stall_start_time = None
        
        try:
            while True:
                # Kiểm tra hủy đo từ người dùng
                if not self.is_measuring:
                    self.logger.info("Deflation aborted by user")
                    aborted = True
                    break
                # Đọc áp suất hiện tại
                raw = self._read_adc_value()
                if raw is None:
                    self.logger.error("ADC timeout during deflation")
                    aborted = True
                    break
                # FIXED: Apply polarity correction
                corrected_counts = raw - self._offset_counts
                if self._adc_inverted:
                    pressure = -corrected_counts * self._slope
                else:
                    pressure = corrected_counts * self._slope
                pressure = max(0.0, pressure)  # Ensure non-negative
                # Bỏ qua giá trị bất thường
                if pressure < -5.0 or pressure > self.safety_pressure + 10.0:
                    continue
                
                data_points.append({'raw': raw, 'pressure': pressure})
                
                # Check for stalled deflation (valve stuck closed or cuff leak)
                if abs(pressure - last_pressure) < self.STALL_THRESHOLD_MMHG:  # Less than threshold mmHg change
                    if stall_start_time is None:
                        stall_start_time = time.time()
                    elif time.time() - stall_start_time > self.STALL_TIMEOUT_S:  # Stalled for N seconds
                        self.logger.error(f"Deflation stalled - pressure not decreasing (threshold={self.STALL_THRESHOLD_MMHG} mmHg)")
                        aborted = True
                        break
                else:
                    stall_start_time = None  # Reset stall timer
                    last_pressure = pressure
                
                # P1-5: Track deflation data for phase analysis
                self._deflate_data.append(pressure)
                # Kiểm tra điều kiện kết thúc đo
                if pressure <= self.DEFLATE_ENDPOINT_MMHG:
                    # Xả xuống endpoint là đủ để xác định DIA
                    break
                if time.time() - start_time > self.DEFLATE_TIMEOUT_S:
                    # Quá thời gian đo (timeout)
                    self.logger.error(f"Measurement timeout during deflation ({self.DEFLATE_TIMEOUT_S}s)")
                    aborted = True
                    break
        finally:
            end_time = time.time()
            # Đảm bảo xả hết áp suất còn lại
            self._valve_open()
            time.sleep(1.0)
            self._valve_close()
            # Lưu thời gian xả thực tế
            self._last_deflate_duration = end_time - start_time
            # P1-4: Calculate and store sample rate (safe division)
            if self._last_deflate_duration > 0.1 and len(data_points) > 0:
                self.measurement_quality.sample_rate_hz = len(data_points) / self._last_deflate_duration
                self.measurement_quality.deflate_duration_s = self._last_deflate_duration
        if aborted:
            # Nếu chưa ngừng bởi user, thực hiện xả khẩn cấp
            if self.is_measuring:
                self.emergency_deflate()
            return []  # return empty list if aborted (user or error)
        return data_points

    
    # ==================== DATA PROCESSING & CALCULATION ====================
    
    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        """
        Read raw pressure and oscillation data from sensor
        Returns:
            Dict with 'pressure' and 'raw' lists (and read_size) or None if error
        """
        # Nếu không ở trạng thái đo, trả về không dữ liệu
        if not self.is_measuring:
            return {'read_size': 0}
        # Thực hiện chu trình đo huyết áp
        # Bơm đến áp suất mục tiêu
        pump_ok = self._pump_to_pressure(self.inflate_target_mmhg)
        if not pump_ok:
            # Dừng đo nếu bơm thất bại hoặc bị hủy
            if not self.is_measuring:
                # Người dùng hủy trong khi bơm
                return {'read_size': 0}
            # Sự cố khi bơm (quá áp hoặc quá thời gian)
            self.emergency_deflate()
            self.is_measuring = False
            self._state = 'idle'
            self.logger.error("Measurement aborted during inflation phase")
            return None
        # Pha xả khí và thu thập dữ liệu
        data_points = self._controlled_deflation(self.deflate_rate_mmhg_s)
        if len(data_points) == 0:
            # Không thu được dữ liệu (có thể bị hủy giữa chừng)
            if not self.is_measuring:
                # Người dùng đã hủy trong khi xả
                return {'read_size': 0}
            # Lỗi trong quá trình xả
            self.is_measuring = False
            self._state = 'idle'
            self.logger.error("No oscillation data collected (measurement failed)")
            return None
        # Đo thành công, kết thúc đo
        self.is_measuring = False
        self._state = 'idle'
        # Tách danh sách áp suất và raw
        pressure_values = [dp['pressure'] for dp in data_points]
        raw_values = [dp['raw'] for dp in data_points]
        raw_data = {
            'pressure': pressure_values,
            'raw': raw_values,
            'read_size': len(pressure_values)
        }
        # Gắn thêm thời gian xả (nếu có) để dùng cho xử lý tín hiệu
        if hasattr(self, '_last_deflate_duration'):
            raw_data['duration'] = self._last_deflate_duration
        return raw_data
    
    def process_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process oscillometric data to calculate blood pressure values
        Args:
            raw_data: Raw pressure data (with 'pressure' list)
        Returns:
            Dict with 'systolic', 'diastolic', 'map', etc. or None if calculation failed
        """
        try:
            pressure_data = raw_data.get('pressure')
            if not pressure_data or len(pressure_data) == 0:
                return None
            # P0-3: Minimum data points validation — make dynamic based on deflation duration
            # Strict minimum absolute floor, but prefer ~50 points when possible
            min_points_default = 50
            duration = raw_data.get('duration', getattr(self, '_last_deflate_duration', 0.0))
            if duration and duration > 0:
                # estimate sample rate from collected points if QA doesn't have it
                est_sps = self.measurement_quality.sample_rate_hz or (len(pressure_data) / max(0.001, duration))
                expected_points = int(round(est_sps * duration)) if est_sps > 0 else len(pressure_data)
                # require at least 60% of expected points, but clamp to reasonable bounds
                min_points = max(12, min(min_points_default, int(max(12, expected_points * 0.6))))
            else:
                min_points = min_points_default

            if len(pressure_data) < min_points:
                # If we still have a modest amount of data (>=12) allow processing with a warning
                if len(pressure_data) >= 12:
                    self.logger.warning(f"Few data points collected ({len(pressure_data)}). Expected {min_points}. Proceeding with reduced dataset.")
                else:
                    self.logger.error(f"Insufficient data points: {len(pressure_data)} < {min_points} required")
                    self.measurement_quality.is_valid = False
                    return None
            # P1-4: Track points collected
            self.measurement_quality.points_collected = len(pressure_data)
            
            # Lọc và loại bỏ xu hướng áp suất (detrend)
            filtered_signal = self._filter_pressure_signal(pressure_data)
            # P1-4: Track filtered points
            self.measurement_quality.points_after_filter = len([x for x in filtered_signal if abs(x) > 0.1])
            
            # Tính biên độ dao động (envelope)
            oscillation_amplitude = self._detect_oscillations(filtered_signal)
            # Ghép cặp áp suất và biên độ thành danh sách dict
            oscillation_data = [
                {'pressure': p, 'amplitude': a} 
                for p, a in zip(pressure_data, oscillation_amplitude)
            ]
            # Tính toán giá trị huyết áp SYS, DIA, MAP
            bp_values = self._calculate_bp_values(oscillation_data)
            if bp_values is None:
                self.logger.warning("Failed to compute blood pressure from oscillation data")
                self.measurement_quality.is_valid = False
                return None
            systolic_val, diastolic_val, map_val = bp_values
            # Làm tròn các kết quả về số nguyên mmHg
            systolic_val = int(round(systolic_val))
            diastolic_val = int(round(diastolic_val))
            map_val = int(round(map_val))
            
            # Validate BP results (physiological sanity checks)
            if not self._validate_bp_results(systolic_val, diastolic_val, map_val):
                self.logger.error(f"BP validation failed: SYS={systolic_val}, DIA={diastolic_val}, MAP={map_val}")
                self.measurement_quality.is_valid = False
                return None
            
            # Cập nhật thuộc tính kết quả
            self.systolic_bp = systolic_val
            self.diastolic_bp = diastolic_val
            self.mean_arterial_pressure = map_val
            # P1-4: Mark measurement as valid after successful calculation
            self.measurement_quality.is_valid = True
            
            # Tạo dict kết quả trả về
            result = {
                'systolic': systolic_val,
                'diastolic': diastolic_val,
                'map': map_val,
                'sys': systolic_val,
                'dia': diastolic_val,
                'status': 'complete',
                'measurement_complete': True,
                'quality': self.measurement_quality.__dict__  # Include QA metrics
            }
            return result
        except Exception as e:
            self.logger.error(f"Error processing oscillometric data: {e}")
            self.measurement_quality.is_valid = False
            return None
    
    def _validate_bp_results(self, systolic: float, diastolic: float, map_val: float) -> bool:
        """
        Validate blood pressure results for physiological sanity
        Args:
            systolic: Systolic BP (mmHg)
            diastolic: Diastolic BP (mmHg)
            map_val: Mean arterial pressure (mmHg)
        Returns:
            bool: True if results are physiologically valid
        """
        # Check 1: SYS must be greater than DIA
        if systolic <= diastolic:
            self.logger.warning(f"SYS ({systolic}) must be > DIA ({diastolic})")
            return False
        
        # Check 2: Values must be in reasonable physiological range
        if systolic < 50 or systolic > 250:
            self.logger.warning(f"SYS ({systolic}) out of range [50-250] mmHg")
            return False
        if diastolic < 30 or diastolic > 150:
            self.logger.warning(f"DIA ({diastolic}) out of range [30-150] mmHg")
            return False
        
        # Check 3: Pulse pressure (SYS - DIA) should be reasonable
        pulse_pressure = systolic - diastolic
        if pulse_pressure < 20 or pulse_pressure > 100:
            self.logger.warning(f"Pulse pressure ({pulse_pressure}) out of range [20-100] mmHg")
            return False
        
        # Check 4: MAP should be between DIA and SYS
        if not (diastolic <= map_val <= systolic):
            self.logger.warning(f"MAP ({map_val}) should be between DIA ({diastolic}) and SYS ({systolic})")
            return False
        
        return True
    
    def _detect_oscillations(self, pressure_data: List[float]) -> List[float]:
        """
        Detect oscillation amplitude envelope in the pressure signal
        Args:
            pressure_data: Filtered (detrended) pressure signal
        Returns:
            List of oscillation amplitude (envelope) values
        """
        N = len(pressure_data)
        if N == 0:
            return []
        
        # Edge case: very few points - return abs values directly
        if N < 10:
            self.logger.warning(f"Very few points ({N}) for envelope detection")
            return [abs(x) for x in pressure_data]
        
        # P1-1: Add Band-Pass Filter to remove baseline drift and high-freq noise
        # Create scipy butterworth BPF (0.5-5 Hz) if scipy available
        try:
            # Estimate sample rate with safe division
            if getattr(self, '_last_deflate_duration', 0) > 0:
                sps = N / max(0.1, self._last_deflate_duration)  # Prevent division by very small number
            else:
                sps = 40.0  # default assume ~40 Hz
            
            # Clamp sample rate to reasonable range
            sps = max(10.0, min(200.0, sps))
            
            # Design bandpass filter: 0.5 Hz (high-pass) to 5 Hz (low-pass)
            nyquist = sps / 2.0
            low_cutoff = 0.5 / nyquist  # normalized frequency
            high_cutoff = 5.0 / nyquist  # normalized frequency
            
            # Ensure cutoff frequencies are in valid range
            low_cutoff = max(0.001, min(0.999, low_cutoff))
            high_cutoff = max(low_cutoff + 0.01, min(0.999, high_cutoff))
            
            # Only apply filter if we have enough points (need at least 3x filter order)
            if N >= 12:  # 2nd order filter needs ~6 points, use 2x safety margin
                # Design Butterworth bandpass filter (2nd order)
                b, a = scipy_signal.butter(2, [low_cutoff, high_cutoff], btype='band')
                # Apply filter forward-backward for zero phase shift
                filtered = scipy_signal.filtfilt(b, a, pressure_data)
            else:
                # Too few points for filtfilt - just detrend
                filtered = pressure_data
        except Exception as e:
            # Fallback if scipy filter fails: just use the pressure data as-is
            self.logger.warning(f"BPF filtering failed: {e}, using raw signal for envelope")
            filtered = pressure_data
        
        # Tín hiệu tuyệt đối (biên độ dao động tức thời)
        abs_signal = np.abs(filtered) if isinstance(filtered, (list, np.ndarray)) else [abs(x) for x in filtered]
        
        # Ước tính tần số lấy mẫu (Hz) để chọn cửa sổ lọc envelope ~0.5s
        if getattr(self, '_last_deflate_duration', 0) > 0:
            sps = N / max(0.1, self._last_deflate_duration)
        else:
            sps = 40.0  # default assume ~40 Hz
        
        sps = max(10.0, min(200.0, sps))  # Clamp to reasonable range
        window_samples = int(max(3, min(N // 2, round(sps * 0.5))))  # Ensure window <= half of signal
        
        # Bộ lọc trung bình để tính envelope (moving average)
        kernel = np.ones(window_samples) / window_samples
        # P1-2: Fix convolution edge effects - use 'full' mode and then trim
        envelope_full = np.convolve(abs_signal, kernel, mode='full')
        # Trim to original size, keeping center portion to avoid edge artifacts
        start_idx = window_samples // 2
        end_idx = start_idx + N
        envelope = envelope_full[start_idx:end_idx]
        # Ensure output length matches input
        if len(envelope) < N:
            envelope = np.pad(envelope, (0, N - len(envelope)), mode='edge')
        elif len(envelope) > N:
            envelope = envelope[:N]
        
        return envelope.tolist() if isinstance(envelope, np.ndarray) else list(envelope)

    
    def _calculate_bp_values(self, oscillation_data: List[Dict[str, float]]) -> Optional[Tuple[float, float, float]]:
        """
        Calculate systolic, diastolic, and MAP from oscillation data
        Args:
            oscillation_data: List of dict with 'pressure' and 'amplitude'
        Returns:
            Tuple of (systolic, diastolic, MAP) or None if calculation failed
        """
        if not oscillation_data:
            return None
        # Tìm điểm MAP (biên độ dao động lớn nhất)
        map_point = self._find_maximum_oscillation(oscillation_data)
        if map_point is None:
            return None
        # Áp dụng tỉ lệ dao động để tìm SYS và DIA
        systolic_val, diastolic_val = self._apply_oscillometric_ratios(map_point, oscillation_data)
        if systolic_val is None or diastolic_val is None:
            return None
        return (systolic_val, diastolic_val, map_point['pressure'])
    
    def _find_maximum_oscillation(self, oscillation_data: List[Dict[str, float]]) -> Optional[Dict[str, float]]:
        """
        Find point of maximum oscillation amplitude (MAP)
        Improved: Find peak in smoothed envelope to avoid noise spikes
        Args:
            oscillation_data: List of {'pressure': ..., 'amplitude': ...}
        Returns:
            Dict with pressure and amplitude at maximum point, or None if not found
        """
        if not oscillation_data:
            return None
        
        # Tìm dict có amplitude lớn nhất
        max_point = max(oscillation_data, key=lambda x: x['amplitude'])
        max_idx = oscillation_data.index(max_point)
        
        # Verify this is a true peak (not a noise spike) by checking neighbors
        # A true MAP should have amplitude decreasing on both sides
        N = len(oscillation_data)
        if N >= 5:  # Need enough points to check neighbors
            # Check if neighbors have lower amplitude
            left_check = max_idx == 0 or oscillation_data[max_idx-1]['amplitude'] < max_point['amplitude']
            right_check = max_idx == N-1 or oscillation_data[max_idx+1]['amplitude'] < max_point['amplitude']
            
            if not (left_check and right_check):
                # Not a clean peak - find best peak in neighborhood
                self.logger.debug(f"MAP at index {max_idx} not a clean peak, searching neighborhood")
                # Search in ±5 indices window
                search_start = max(0, max_idx - 5)
                search_end = min(N, max_idx + 6)
                neighborhood = oscillation_data[search_start:search_end]
                # Find peak with best neighbors
                best_point = max(neighborhood, key=lambda x: x['amplitude'])
                max_point = best_point
        
        self.logger.debug(f"MAP found: pressure={max_point['pressure']:.1f} mmHg, amplitude={max_point['amplitude']:.4f}")
        return max_point
    
    def _apply_oscillometric_ratios(self, map_point: Dict[str, float], 
                                    oscillation_data: List[Dict[str, float]]) -> Tuple[Optional[float], Optional[float]]:
        """
        Apply oscillometric ratios to determine systolic and diastolic pressures
        P0-1 FIX: Corrected detection logic to find SYS/DIA on proper branches
        
        Args:
            map_point: Điểm có dao động cực đại (MAP)
            oscillation_data: Toàn bộ dữ liệu dao động (danh sách dict pressure/amplitude)
        Returns:
            Tuple of (systolic_pressure, diastolic_pressure) in mmHg (hoặc None nếu không xác định được)
        
        OSCILLOMETRIC METHOD:
        - During inflation: pressure increases, oscillations grow → SYS detected when amplitude crosses threshold going UP
        - During deflation: pressure decreases, oscillations shrink → MAP at max amplitude, DIA when amplitude falls below threshold
        - P0-1 FIX: SYS should be on RISING branch (before MAP), DIA on FALLING branch (after MAP)
        """
        # Lấy hệ số tỷ lệ từ config (không hardcode)
        ratio_conf = self.config.get('ratio', {}) if hasattr(self, 'config') else {}
        sys_frac = ratio_conf.get('sys_frac', 0.5)   # Default 50% for SYS
        dia_frac = ratio_conf.get('dia_frac', 0.8)   # Default 80% for DIA
        
        # P1-3: Validate ratio parameters
        if not (0.0 < sys_frac < 1.0):
            self.logger.warning(f"Invalid sys_frac {sys_frac}, using 0.5")
            sys_frac = 0.5
        if not (0.0 < dia_frac < 1.0):
            self.logger.warning(f"Invalid dia_frac {dia_frac}, using 0.8")
            dia_frac = 0.8
        
        # Danh sách áp suất và biên độ
        pressures = [pt['pressure'] for pt in oscillation_data]
        amplitudes = [pt['amplitude'] for pt in oscillation_data]
        
        # Chỉ số của điểm MAP
        try:
            map_index = oscillation_data.index(map_point)
        except ValueError:
            return (None, None)
        
        # Ngưỡng biên độ cho SYS và DIA
        sys_threshold = sys_frac * map_point['amplitude']
        dia_threshold = dia_frac * map_point['amplitude']
        
        systolic_pressure = None
        diastolic_pressure = None
        
        # P0-1 FIX: SYSTOLIC on RISING branch (before MAP, going UP)
        # Find FIRST point where amplitude crosses sys_threshold while increasing
        for i in range(0, map_index):
            # Check if amplitude is crossing threshold going upward
            if amplitudes[i] >= sys_threshold:
                # Confirm it's part of rising portion by checking slope
                # Use 3-point average slope for robustness
                if i == 0:
                    is_rising = True  # First point, assume rising
                elif i == 1:
                    is_rising = amplitudes[i] > amplitudes[i-1]
                else:
                    # Check average slope over last 3 points
                    slope_1 = amplitudes[i] - amplitudes[i-1]
                    slope_2 = amplitudes[i-1] - amplitudes[i-2]
                    avg_slope = (slope_1 + slope_2) / 2.0
                    is_rising = avg_slope > 0
                
                if is_rising:
                    systolic_pressure = pressures[i]
                    self.logger.debug(f"SYS detected at index {i}: pressure={systolic_pressure:.1f}, amplitude={amplitudes[i]:.4f}")
                    break
        
        # P0-1 FIX: DIASTOLIC on FALLING branch (after MAP, going DOWN)
        # Find FIRST point where amplitude falls below dia_threshold after MAP
        for j in range(map_index, len(amplitudes)):
            # Check if amplitude is on falling portion and below threshold
            if amplitudes[j] <= dia_threshold:
                # Confirm it's part of falling portion by checking slope
                if j == map_index:
                    is_falling = True  # At MAP, assume falling after
                elif j == len(amplitudes) - 1:
                    is_falling = amplitudes[j] < amplitudes[j-1]
                else:
                    # Check average slope over 3 points
                    slope_1 = amplitudes[j] - amplitudes[j-1] if j > map_index else 0
                    slope_2 = amplitudes[j+1] - amplitudes[j] if j < len(amplitudes)-1 else 0
                    avg_slope = (slope_1 + slope_2) / 2.0
                    is_falling = avg_slope < 0
                
                if is_falling:
                    diastolic_pressure = pressures[j]
                    self.logger.debug(f"DIA detected at index {j}: pressure={diastolic_pressure:.1f}, amplitude={amplitudes[j]:.4f}")
                    break
        
        # Nếu không tìm thấy một trong hai ngưỡng, trả về None
        if systolic_pressure is None or diastolic_pressure is None:
            self.logger.warning(f"Failed to detect SYS or DIA: sys={systolic_pressure}, dia={diastolic_pressure}")
            return (None, None)
        
        # P1-4: Calculate SNR for QA metrics
        if map_point['amplitude'] > 0:
            noise_estimate = statistics.median([abs(a) for a in amplitudes[:max(1, len(amplitudes)//10)]])
            self.measurement_quality.signal_noise_ratio = map_point['amplitude'] / (noise_estimate + 0.001)
            self.measurement_quality.map_amplitude = map_point['amplitude']
        
        return (systolic_pressure, diastolic_pressure)

    
    def _filter_pressure_signal(self, signal: List[float]) -> List[float]:
        """
        Apply filtering to pressure signal (remove baseline drift)
        P1-1: Includes detrending logic (further HPF done in _detect_oscillations BPF)
        Args:
            signal: Raw pressure signal (with baseline trend)
        Returns:
            Filtered pressure signal (oscillations around zero)
        """
        N = len(signal)
        if N == 0:
            return []
        # Loại bỏ xu hướng áp suất (detrend tuyến tính) - removes linear drift
        p_start = signal[0]
        p_end = signal[-1]
        baseline = [(p_start + (p_end - p_start) * i / (N - 1)) for i in range(N)] if N > 1 else [p_start] * N
        filtered = [signal[i] - baseline[i] for i in range(N)]
        # Note: Additional high-pass filtering (0.5 Hz cutoff) is applied in _detect_oscillations BPF
        return filtered
    
    # ==================== SAFETY & EMERGENCY ====================
    
    def _safety_check(self) -> bool:
        """
        Kiểm tra an toàn trước khi đo (xả áp suất dư, verify calibration)
        FIXED: Chỉ verify, KHÔNG ghi đè offset. Yêu cầu calibrate_with_arm.py cho cuff đeo tay
        Returns:
            bool: True nếu an toàn để tiếp tục
        """
        if not self._gpio_initialized:
            return False
        try:
            # Xả hết áp suất còn trong cuff (tăng thời gian cho cuff đeo tay)
            self.logger.info("Safety check: deflating cuff completely...")
            self._valve_open()
            time.sleep(3.0)  # 3 giây để đảm bảo xả hết với cuff đeo tay
            
            samples: List[int] = []
            # Đọc nhiều samples để verify zero-pressure
            for _ in range(self.ZERO_CALIBRATION_SAMPLES):
                val = self._read_adc_value(timeout=0.1)
                if val is not None:
                    samples.append(val)
                    time.sleep(0.05)  # Tăng delay giữa các lần đọc
                else:
                    break
            self._valve_close()
            
            if len(samples) == 0:
                self.logger.error("No ADC data for zero verification")
                return False
            
            # Tính median và std của zero-pressure readings
            zero_adc = int(statistics.median(samples))
            adc_std = statistics.stdev(samples) if len(samples) > 1 else 0
            # FIXED: Apply polarity correction
            corrected_counts = zero_adc - self._offset_counts
            if self._adc_inverted:
                zero_pressure = -corrected_counts * self._slope
            else:
                zero_pressure = corrected_counts * self._slope
            
            # Log kết quả verify
            self.logger.info(f"Zero-pressure verification:")
            self.logger.info(f"  ADC median: {zero_adc:,} (±{adc_std:.0f} std)")
            self.logger.info(f"  Config offset: {self._offset_counts:,}")
            self.logger.info(f"  Calculated pressure: {zero_pressure:.1f} mmHg")
            
            # Warning nếu sai số lớn (nhưng KHÔNG ghi đè offset!)
            if abs(zero_pressure) > 15.0:
                self.logger.warning(f"⚠ CALIBRATION ERROR DETECTED!")
                self.logger.warning(f"  Zero-pressure should be ~0 mmHg, but got {zero_pressure:.1f} mmHg")
                self.logger.warning(f"  This will cause INCORRECT blood pressure readings!")
                self.logger.warning(f"")
                self.logger.warning(f"  REQUIRED ACTION:")
                self.logger.warning(f"    1. Run: python tests/calibrate_with_arm.py")
                self.logger.warning(f"    2. Follow on-screen instructions")
                self.logger.warning(f"    3. Re-test measurement")
                self.logger.warning(f"")
                # Vẫn return False để NGĂN ĐO với calibration sai
                return False
            else:
                self.logger.info(f"✓ Calibration verified (error: {zero_pressure:.1f} mmHg)")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Safety check error: {e}")
            return False
    
    def emergency_deflate(self) -> bool:
        """
        Xả khẩn cấp toàn bộ khí trong cuff
        Returns:
            bool: True nếu xả thành công
        """
        try:
            self._pump_off()   # đảm bảo tắt bơm
            self._valve_open()  # mở van xả
            time.sleep(self.EMERGENCY_DEFLATE_TIME_S)  # xả khí
            self._valve_close() # đóng van lại
            self.logger.info("Emergency deflation completed")
            return True
        except Exception as e:
            self.logger.error(f"Emergency deflation failed: {e}")
            return False
    
    def cleanup(self) -> None:
        """
        Cleanup GPIO resources
        """
        try:
            if self._gpio_initialized:
                self._pump_off()
                self._valve_close()
                GPIO.cleanup([self.pump_gpio, self.valve_gpio, self._dout_pin, self._sck_pin])
                self._gpio_initialized = False
                self.logger.info("Blood pressure GPIO cleaned up")
        except Exception as e:
            self.logger.error(f"GPIO cleanup failed: {e}")
    
    # ==================== CALIBRATION & STATUS ====================
    
    def calibrate_pressure_sensor(self, reference_pressures: List[float], 
                                  measured_values: List[float]) -> bool:
        """
        Calibrate pressure sensor với các giá trị tham chiếu
        Args:
            reference_pressures: List các áp suất tham chiếu (mmHg)
            measured_values: List các giá trị ADC đo được tương ứng
        Returns:
            bool: True nếu hiệu chuẩn thành công
        """
        if not reference_pressures or not measured_values or len(reference_pressures) != len(measured_values) or len(reference_pressures) < 2:
            self.logger.error("Invalid calibration data provided")
            return False
        try:
            coeff = np.polyfit(measured_values, reference_pressures, 1)
            slope = coeff[0]
            intercept = coeff[1]
            if slope == 0:
                self.logger.error("Calibration slope is zero")
                return False
            # Tính offset_counts dựa trên đường hiệu chuẩn (reference = slope*raw + intercept)
            offset_counts = - intercept / slope
            self._offset_counts = int(round(offset_counts))
            self._slope = float(slope)
            self.logger.info(f"Calibration updated: offset_counts={self._offset_counts}, slope={self._slope:.6f} mmHg/count")
            return True
        except Exception as e:
            self.logger.error(f"Calibration failed: {e}")
            return False
    
    def get_measurement_status(self) -> Dict[str, Any]:
        """
        Get current measurement status and progress
        Returns:
            Dict with measurement status information (state, current pressure, progress, etc.)
        """
        status: Dict[str, Any] = {}
        status['state'] = self._state
        status['current_pressure'] = self.current_pressure
        status['is_measuring'] = self.is_measuring
        if not self.is_measuring:
            # Đo không hoạt động - trả về kết quả lần đo cuối (nếu có)
            status['systolic'] = self.systolic_bp if self.systolic_bp else None
            status['diastolic'] = self.diastolic_bp if self.diastolic_bp else None
            status['map'] = self.mean_arterial_pressure if self.mean_arterial_pressure else None
            status['progress'] = 0.0
        else:
            # Đang trong quá trình đo - tính toán tiến độ gần đúng
            if self._state == 'INFLATE':
                progress = 0.0
                if self.inflate_target_mmhg > 0:
                    progress = min(1.0, self.current_pressure / float(self.inflate_target_mmhg))
                status['progress'] = progress
            elif self._state == 'DEFLATE':
                # Tính phần trăm xả dựa trên áp suất đã giảm từ khi bơm xong đến 40 mmHg
                range_pressure = max(1.0, float(self.inflate_target_mmhg - 40.0))
                progress = (float(self.inflate_target_mmhg) - self.current_pressure) / range_pressure
                progress = max(0.0, min(1.0, progress))
                status['progress'] = progress
            else:
                status['progress'] = 0.0
        return status
    
    def get_measurement_quality(self) -> Dict[str, Any]:
        """
        P1-4: Get measurement quality metrics for diagnostic purposes
        Returns:
            Dict with QA metrics (timeouts, points, SNR, sample rate, etc.)
        """
        return self.measurement_quality.__dict__

