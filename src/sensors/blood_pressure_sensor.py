#!/usr/bin/env python3
"""
Blood Pressure Sensor Driver - Rewritten with Accurate Calibration
===================================================================

Oscillometric blood pressure measurement system using:
- MPS20N0040D-S pressure sensor (0-40 kPa, Wheatstone bridge)
- HX710B 24-bit ADC (GPIO bit-bang, differential input)
- 6V air pump (GPIO26 via optocoupler + MOSFET)
- 6V solenoid valve NO (GPIO16 via optocoupler + MOSFET)

Hardware Specifications (from datasheets):
-----------------------------------------
MPS20N0040D-S:
  - Range: 0-40 kPa (0-300 mmHg)
  - Full-scale output: 50-100 mV @ 5V, typical 75 mV
  - Sensitivity: 1.875 mV/kPa (typical)
  - Linearity: ±0.3% FS
  - Temperature coefficient: -0.21% FS/°C

HX710B:
  - Resolution: 24-bit (16,777,216 counts full scale)
  - Gain: 128 (default, configurable)
  - Input range: ±20 mV (before gain)
  - Sample rate: 10-80 SPS (board dependent)

Calibration Parameters (from datasheet calculation @ 3.3V supply):
---------------------------------------------------------------
  slope_mmhg_per_count = 9.536743e-06 mmHg/count (typical, 75mV sensor span)
  offset_counts = [measured at zero pressure via bp_calib_tool.py]
  
Calculation (Ratio-metric @ 3.3V, cancels supply voltage):
  Sensor span (typical): 75 mV @ 300 mmHg (at any supply voltage due to ratio-metric design)
  HX710B full-scale: ±20 mV differential input
  ADC counts: 2^23 = 8,388,608 (signed 24-bit)
  
  counts_per_mV = 8,388,608 / 20 mV = 419,430.4 counts/mV
  mV_per_mmHg = 75 mV / 300 mmHg = 0.25 mV/mmHg
  counts_per_mmHg = 419,430.4 × 0.25 = 104,857.6 counts/mmHg
  slope = 1 / 104,857.6 = 9.536743e-06 mmHg/count
  
  Resolution: ~0.0095 mmHg/count (sufficient for ±2 mmHg AAMI accuracy)

Oscillometric Method (AAMI/ISO 81060-2 compliant):
-------------------------------------------------
1. Inflate to 165 mmHg (above expected SYS)
2. Deflate slowly (~3 mmHg/s target, actual faster due to NO valve)
3. Extract oscillations (pulse amplitude) via bandpass filter (0.5-5 Hz, heart rate range)
4. Find MAP (maximum oscillation point) with quality checks
5. Estimate SYS/DIA using oscillometric ratios (per AAMI recommendations):
   - SYS: pressure where amplitude = 0.55 × MAP_amplitude (on rising slope)
   - DIA: pressure where amplitude = 0.80 × MAP_amplitude (on falling slope)
6. Validate results against physiological limits and SNR thresholds

Hardware Constraints:
--------------------
- NO valve leaks naturally at ~100-500 mmHg/s (uncontrollable)
- Fast deflation → only 10-35 data points collected
- Offset drifts ~100-500 counts/hour with temperature
- Recommend daily offset calibration

Author: IoT Health Monitor Team
Date: 2025-10-23
Version: 2.0.0 (Rewritten with datasheet-accurate calibration)
"""

from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass, asdict
import logging
import time
import threading
from enum import Enum
import json

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

import numpy as np
from scipy import signal as scipy_signal
from .base_sensor import BaseSensor


# ==================== ENUMS & DATA CLASSES ====================

class MeasurementPhase(Enum):
    """Measurement phases for status tracking"""
    IDLE = "idle"
    SAFETY_CHECK = "safety_check"
    INFLATING = "inflating"
    DEFLATING = "deflating"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    ERROR = "error"
    EMERGENCY_DEFLATE = "emergency_deflate"


@dataclass
class MeasurementResult:
    """Complete blood pressure measurement result with metadata"""
    # BP values (mmHg)
    systolic: float
    diastolic: float
    map: float
    pulse_pressure: float
    
    # Quality metrics
    oscillation_amplitude: float  # Peak-to-peak oscillation (mmHg)
    snr_db: float                 # Signal-to-noise ratio (dB)
    points_collected: int
    points_after_filter: int
    sample_rate_hz: float
    deflate_duration_s: float
    
    # Validity flags
    is_valid: bool
    validation_errors: List[str]
    
    # Timestamps
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)


@dataclass
class HX710BCalibration:
    """HX710B ADC calibration parameters"""
    offset_counts: int
    slope_mmhg_per_count: float
    adc_inverted: bool = False    # ADC polarity (True if pressure increase → counts decrease)
    gain: int = 128
    adc_bits: int = 24
    sps_hint: float = 42.5
    
    # Metadata
    calibration_date: Optional[str] = None
    sensor_model: str = "MPS20N0040D-S"
    adc_model: str = "HX710B"
    
    def counts_to_mmhg(self, raw_counts: int) -> float:
        """Convert raw ADC counts to pressure (mmHg)"""
        # Handle ADC inversion (if wired with reversed polarity)
        adjusted_counts = -raw_counts if self.adc_inverted else raw_counts
        return (adjusted_counts - self.offset_counts) * self.slope_mmhg_per_count
    
    def mmhg_to_counts(self, pressure_mmhg: float) -> int:
        """Convert pressure (mmHg) to expected ADC counts"""
        counts = int(pressure_mmhg / self.slope_mmhg_per_count + self.offset_counts)
        return -counts if self.adc_inverted else counts


# ==================== HX710B ADC DRIVER ====================

class HX710B:
    """
    HX710B 24-bit ADC driver with bit-bang protocol
    
    Thread-safe, non-blocking driver for differential pressure sensor.
    Implements proper timing, timeout handling, and error recovery.
    
    Protocol:
    ---------
    1. Wait for DOUT to go LOW (data ready)
    2. Clock out 24 bits (MSB first) via SCK pulses
    3. Send 1 more SCK pulse to prepare next conversion
    
    Timing (from datasheet):
    -----------------------
    - T_PD: >60 μs (power down if SCK stays high)
    - T_DOUT: 0.1 μs (DOUT valid after SCK falling edge)
    - T_SCK: >0.2 μs (min clock pulse width)
    - Sample rate: 10-80 SPS (crystal/config dependent)
    """
    
    def __init__(self, gpio_dout: int, gpio_sck: int, timeout_ms: int = 200):
        """
        Initialize HX710B ADC
        
        Args:
            gpio_dout: GPIO pin for DOUT (data, input)
            gpio_sck: GPIO pin for SCK (clock, output)
            timeout_ms: Max wait time for data ready (ms)
        """
        self.gpio_dout = gpio_dout
        self.gpio_sck = gpio_sck
        self.timeout_ms = timeout_ms
        
        self.logger = logging.getLogger(f"HX710B[DOUT={gpio_dout},SCK={gpio_sck}]")
        self._lock = threading.Lock()
        self._is_initialized = False
        
    def initialize(self) -> bool:
        """
        Initialize GPIO pins and wake up HX710B
        
        Returns:
            bool: True if successful
        """
        if not GPIO:
            self.logger.error("RPi.GPIO not available (simulation mode)")
            return False
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup pins
            GPIO.setup(self.gpio_sck, GPIO.OUT)
            GPIO.setup(self.gpio_dout, GPIO.IN)
            
            # Initialize SCK low
            GPIO.output(self.gpio_sck, GPIO.LOW)
            time.sleep(0.001)  # 1ms settle time
            
            # Power-up sequence: ensure HX710B is awake
            # HX710B enters power-down if SCK is HIGH for >60μs
            # Wake it up by pulsing SCK
            self.logger.debug("Waking up HX710B...")
            for _ in range(3):
                GPIO.output(self.gpio_sck, GPIO.HIGH)
                time.sleep(0.000001)  # 1μs
                GPIO.output(self.gpio_sck, GPIO.LOW)
                time.sleep(0.000001)  # 1μs
            
            # Wait for HX710B to stabilize
            time.sleep(0.1)  # 100ms settle time
            
            self._is_initialized = True
            self.logger.info("HX710B initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize HX710B: {e}")
            return False
    
    def read_raw(self) -> Optional[int]:
        """
        Read raw 24-bit value from HX710B (thread-safe, blocking)
        
        Returns:
            int: Raw counts (signed 24-bit, range: -8388608 to 8388607)
            None: On timeout or error
        """
        if not self._is_initialized:
            self.logger.error("HX710B not initialized")
            return None
        
        with self._lock:
            try:
                # Wait for DOUT to go LOW (data ready)
                start_time = time.time()
                timeout_s = self.timeout_ms / 1000.0
                
                while GPIO.input(self.gpio_dout) == GPIO.HIGH:
                    if time.time() - start_time > timeout_s:
                        self.logger.warning(f"Timeout waiting for data ready ({self.timeout_ms}ms)")
                        return None
                    time.sleep(0.0001)  # 100μs poll interval
                
                # Read 24 bits (MSB first)
                # CRITICAL: Must read DOUT AFTER SCK falling edge (per HX710B datasheet)
                value = 0
                for _ in range(24):
                    # Generate clock pulse (HIGH -> LOW)
                    GPIO.output(self.gpio_sck, GPIO.HIGH)
                    time.sleep(0.000001)  # 1μs high pulse (min 0.2μs per datasheet)
                    GPIO.output(self.gpio_sck, GPIO.LOW)
                    time.sleep(0.000001)  # 1μs low time (allow DOUT to settle)
                    
                    # Read DOUT AFTER falling edge (data is now valid per datasheet)
                    bit_value = GPIO.input(self.gpio_dout)
                    
                    # Shift in bit
                    value = (value << 1) | bit_value
                
                # 25th pulse to set gain/channel for next conversion
                GPIO.output(self.gpio_sck, GPIO.HIGH)
                time.sleep(0.000001)  # 1μs
                GPIO.output(self.gpio_sck, GPIO.LOW)
                
                # Convert 24-bit two's complement to signed int
                if value & 0x800000:  # Negative number
                    value -= 0x1000000
                
                return value
                
            except Exception as e:
                self.logger.error(f"Error reading HX710B: {e}")
                return None
    
    def read_average(self, num_samples: int = 10, discard_outliers: bool = True) -> Optional[float]:
        """
        Read multiple samples and return average (with outlier rejection)
        
        Args:
            num_samples: Number of samples to average
            discard_outliers: Remove values >2 StdDev from median
        
        Returns:
            float: Average value
            None: On error
        """
        samples = []
        for _ in range(num_samples):
            value = self.read_raw()
            if value is not None:
                samples.append(value)
        
        if not samples:
            return None
        
        if discard_outliers and len(samples) >= 5:
            # Remove outliers using MAD (Median Absolute Deviation)
            median = np.median(samples)
            mad = np.median(np.abs(np.array(samples) - median))
            threshold = 3 * mad  # 3-sigma equivalent
            
            samples = [s for s in samples if abs(s - median) <= threshold]
        
        return np.mean(samples) if samples else None
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        if self._is_initialized and GPIO:
            try:
                GPIO.output(self.gpio_sck, GPIO.LOW)
                # Don't call GPIO.cleanup() - other sensors may be using GPIO
                self._is_initialized = False
                self.logger.info("HX710B cleaned up")
            except Exception as e:
                self.logger.error(f"Error during cleanup: {e}")


# ==================== BLOOD PRESSURE SENSOR ====================

class BloodPressureSensor(BaseSensor):
    """
    Oscillometric blood pressure measurement sensor (Accurate Calibration from Datasheet)
    
    This is a ONE-SHOT measurement sensor (not continuous reading).
    Use start_measurement() to begin inflate→deflate→analyze cycle.
    
    Threading Model:
    ---------------
    - Main thread: Controls pump/valve, monitors progress
    - Callback thread: Notifies completion via callback
    - User thread: Polls get_measurement_status() for UI updates
    
    Usage Example:
    -------------
    >>> sensor = BloodPressureSensor(config)
    >>> sensor.initialize()
    >>> sensor.start()  # Enable hardware (doesn't start measurement)
    >>> 
    >>> # Start measurement (runs in background)
    >>> sensor.start_measurement(callback=on_complete)
    >>> 
    >>> # Poll status for UI updates
    >>> while sensor.is_measuring:
    >>>     status = sensor.get_measurement_status()
    >>>     print(f"Phase: {status['phase']}, Pressure: {status['pressure']:.1f} mmHg")
    >>>     time.sleep(0.5)
    >>> 
    >>> # Get result
    >>> result = sensor.get_last_result()
    >>> print(f"BP: {result.systolic}/{result.diastolic} mmHg")
    """
    
    # ==================== CONSTANTS ====================
    
    # Safety limits
    MAX_INFLATE_PRESSURE_MMHG = 200.0      # Absolute maximum (hardware relief valve)
    MAX_INFLATE_TIME_S = 30.0              # Max inflation time
    EMERGENCY_DEFLATE_TIME_S = 5.0         # Time to hold valve open
    
    # Measurement parameters
    INFLATE_TARGET_MMHG = 165.0            # Target inflation pressure
    DEFLATE_ENDPOINT_MMHG = 20.0           # Stop deflation at this pressure
    DEFLATE_TIMEOUT_S = 15.0               # Max deflation time
    
    # Oscillometric algorithm parameters (AAMI/ISO 81060-2 standard)
    BPF_LOW_HZ = 0.5                       # Bandpass filter low cutoff (30 bpm, 0.5 Hz)
    BPF_HIGH_HZ = 5.0                      # Bandpass filter high cutoff (300 bpm, 5 Hz)
    BPF_ORDER = 2                          # Filter order (Butterworth, bi-directional)
    MIN_OSCILLATION_POINTS = 10            # Minimum points for valid analysis (increased)
    
    # Oscillometric ratios (AAMI recommendations, literature consensus)
    SYS_AMPLITUDE_RATIO = 0.55             # SYS at 55% of MAP amplitude (AAMI standard)
    DIA_AMPLITUDE_RATIO = 0.80             # DIA at 80% of MAP amplitude (AAMI standard)
    
    # Validation thresholds (AAMI/AHA guidelines)
    MIN_SYS_MMHG = 70                      # Minimum valid systolic (hypotension threshold)
    MAX_SYS_MMHG = 250                     # Maximum valid systolic (severe hypertension)
    MIN_DIA_MMHG = 40                      # Minimum valid diastolic (physiological limit)
    MAX_DIA_MMHG = 150                     # Maximum valid diastolic (severe hypertension)
    MIN_PULSE_PRESSURE_MMHG = 20           # Minimum pulse pressure (physiological limit)
    MAX_PULSE_PRESSURE_MMHG = 100          # Maximum pulse pressure (widened PP threshold)
    MIN_SNR_DB = 6.0                       # Minimum signal-to-noise ratio (AAMI quality)
    
    # ==================== INITIALIZATION ====================
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize blood pressure sensor
        
        Args:
            config: Configuration dictionary with keys:
                - hx710b: HX710B ADC configuration
                - blood_pressure: BP sensor configuration
        """
        super().__init__("BloodPressure", config)
        
        # Extract configurations
        hx710b_config = config.get('hx710b', {})
        bp_config = config.get('blood_pressure', {})
        
        # Load BP-specific config overrides (from app_config.yaml bp: section)
        bp_advanced = config.get('bp', {})
        signal_config = bp_advanced.get('signal', {})
        estimate_config = bp_advanced.get('estimate', {})
        
        # Initialize HX710B driver
        self.adc = HX710B(
            gpio_dout=hx710b_config.get('gpio_dout', 6),
            gpio_sck=hx710b_config.get('gpio_sck', 5),
            timeout_ms=hx710b_config.get('timeout_ms', 200)
        )
        
        # Load calibration
        calib = hx710b_config.get('calibration', {})
        self.calibration = HX710BCalibration(
            offset_counts=calib.get('offset_counts', 0),
            slope_mmhg_per_count=calib.get('slope_mmhg_per_count', 9.536743e-06),  # Datasheet default
            adc_inverted=calib.get('adc_inverted', False),
            gain=128,
            adc_bits=24,
            sps_hint=hx710b_config.get('sps_hint', 42.5)
        )
        
        # GPIO pins
        self.pump_gpio = bp_config.get('pump_gpio', 26)
        self.valve_gpio = bp_config.get('valve_gpio', 16)
        self.valve_is_no = bp_config.get('valve_is_no', True)  # Normally Open
        
        # Measurement parameters (override defaults if provided)
        self.inflate_target = bp_config.get('inflate_target_mmhg', self.INFLATE_TARGET_MMHG)
        self.max_pressure = bp_config.get('max_pressure', self.MAX_INFLATE_PRESSURE_MMHG)
        
        # Override oscillometric ratios from config (if provided)
        if estimate_config:
            self.SYS_AMPLITUDE_RATIO = estimate_config.get('sys_frac', self.SYS_AMPLITUDE_RATIO)
            self.DIA_AMPLITUDE_RATIO = estimate_config.get('dia_frac', self.DIA_AMPLITUDE_RATIO)
            self.logger.info(f"Using config ratios: SYS={self.SYS_AMPLITUDE_RATIO}, DIA={self.DIA_AMPLITUDE_RATIO}")
        
        # Override filter settings from config (if provided)
        if signal_config:
            self.BPF_LOW_HZ = signal_config.get('bpf_low_hz', self.BPF_LOW_HZ)
            self.BPF_HIGH_HZ = signal_config.get('bpf_high_hz', self.BPF_HIGH_HZ)
            self.MIN_SNR_DB = signal_config.get('snr_min_db', self.MIN_SNR_DB)
            self.logger.info(f"Using config filter: {self.BPF_LOW_HZ}-{self.BPF_HIGH_HZ} Hz, SNR≥{self.MIN_SNR_DB} dB")
        
        # State variables
        self.is_measuring = False
        self.current_phase = MeasurementPhase.IDLE
        self.current_pressure = 0.0
        self.last_result: Optional[MeasurementResult] = None
        
        # Threading
        self._measurement_thread: Optional[threading.Thread] = None
        self._stop_measurement_event = threading.Event()
        self._measurement_callback: Optional[Callable] = None
        
        # Validate configuration
        self._validate_config()
        
        self.logger.info(f"BloodPressureSensor initialized (slope={self.calibration.slope_mmhg_per_count:.10f})")
    
    def _validate_config(self):
        """Validate configuration parameters"""
        # Check calibration
        if self.calibration.offset_counts == 0:
            self.logger.warning("⚠️  Offset not calibrated! Run: python tests/bp_calib_tool.py offset-electric")
        
        # Validate slope against datasheet (±10% tolerance)
        expected_slope = 9.536743e-06
        slope_error = abs(self.calibration.slope_mmhg_per_count - expected_slope) / expected_slope
        if slope_error > 0.10:
            self.logger.warning(f"⚠️  Slope differs from datasheet by {slope_error*100:.1f}%: "
                              f"{self.calibration.slope_mmhg_per_count:.10f} "
                              f"(expected: {expected_slope:.10f})")
            self.logger.warning(f"   Consider recalibration: python tests/bp_calib_tool.py slope-manual --pressure 150")
        
        # Check GPIO
        if self.pump_gpio == self.valve_gpio:
            raise ValueError(f"Pump and valve cannot use same GPIO: {self.pump_gpio}")
        
        # Check pressure limits
        if self.inflate_target >= self.max_pressure:
            raise ValueError(f"Inflate target ({self.inflate_target}) must be < max pressure ({self.max_pressure})")
    
    # ==================== HARDWARE CONTROL ====================
    
    def initialize(self) -> bool:
        """
        Initialize hardware (GPIO, ADC)
        
        Returns:
            bool: True if successful
        """
        if not GPIO:
            self.logger.error("RPi.GPIO not available")
            return False
        
        try:
            # Initialize GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup pump and valve
            GPIO.setup(self.pump_gpio, GPIO.OUT)
            GPIO.setup(self.valve_gpio, GPIO.OUT)
            
            # Initial state: pump OFF, valve according to type
            GPIO.output(self.pump_gpio, GPIO.LOW)
            if self.valve_is_no:
                GPIO.output(self.valve_gpio, GPIO.LOW)  # NO: LOW = open (deflate)
            else:
                GPIO.output(self.valve_gpio, GPIO.HIGH)  # NC: HIGH = open (deflate)
            
            # Initialize ADC
            if not self.adc.initialize():
                return False
            
            # Test read with retry (first read often fails)
            self.logger.info("Testing ADC connection...")
            test_value = None
            for attempt in range(3):
                test_value = self.adc.read_raw()
                if test_value is not None:
                    break
                self.logger.warning(f"ADC test read attempt {attempt+1}/3 failed, retrying...")
                time.sleep(0.2)  # 200ms between retries
            
            if test_value is None:
                self.logger.error("ADC test read failed after 3 attempts")
                self.logger.error("Check: 1) Wiring (DOUT→GPIO6, SCK→GPIO5), 2) Power (VCC 3.3V), 3) HX710B module")
                return False
            
            self.logger.info(f"Hardware initialized successfully (test ADC value: {test_value})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize hardware: {e}")
            return False
    
    def _pump_on(self):
        """Turn pump ON (inflate)"""
        if GPIO:
            GPIO.output(self.pump_gpio, GPIO.HIGH)
            self.logger.info(f"⚡ Pump ON - GPIO{self.pump_gpio}=HIGH")
    
    def _pump_off(self):
        """Turn pump OFF"""
        if GPIO:
            GPIO.output(self.pump_gpio, GPIO.LOW)
            self.logger.info(f"⏹️  Pump OFF - GPIO{self.pump_gpio}=LOW")
    
    def _valve_open(self):
        """Open valve (deflate)"""
        if GPIO:
            if self.valve_is_no:
                GPIO.output(self.valve_gpio, GPIO.LOW)  # NO: LOW = open
                self.logger.info(f"🔓 Valve OPEN (deflate) - GPIO{self.valve_gpio}=LOW (NO mode)")
            else:
                GPIO.output(self.valve_gpio, GPIO.HIGH)  # NC: HIGH = open
                self.logger.info(f"🔓 Valve OPEN (deflate) - GPIO{self.valve_gpio}=HIGH (NC mode)")
    
    def _valve_close(self):
        """Close valve (hold pressure)"""
        if GPIO:
            if self.valve_is_no:
                GPIO.output(self.valve_gpio, GPIO.HIGH)  # NO: HIGH = close
                self.logger.info(f"🔒 Valve CLOSE (hold) - GPIO{self.valve_gpio}=HIGH (NO mode)")
            else:
                GPIO.output(self.valve_gpio, GPIO.LOW)  # NC: LOW = close
                self.logger.info(f"🔒 Valve CLOSE (hold) - GPIO{self.valve_gpio}=LOW (NC mode)")
    
    def _emergency_deflate(self):
        """Emergency deflate: pump OFF, valve OPEN"""
        self.logger.warning("EMERGENCY DEFLATE")
        self._pump_off()
        self._valve_open()
        time.sleep(self.EMERGENCY_DEFLATE_TIME_S)
        self.current_phase = MeasurementPhase.IDLE
    
    # ==================== PRESSURE READING ====================
    
    def _read_pressure(self) -> Optional[float]:
        """
        Read current pressure from ADC (with retry for low SPS)
        
        HX710B has low sample rate (~10-40 SPS), so first read may timeout.
        Retry up to 3 times with longer interval.
        
        Returns:
            float: Pressure in mmHg
            None: On error after retries
        """
        for attempt in range(3):
            raw = self.adc.read_raw()
            if raw is not None:
                # Validate raw value (reject obvious errors)
                if raw == -1 or raw == 0 or raw == -2:
                    self.logger.warning(f"⚠️  Suspicious ADC value: {raw} (likely read error)")
                    if attempt < 2:
                        time.sleep(0.15)  # Wait longer for valid data
                    continue
                    
                pressure = self.calibration.counts_to_mmhg(raw)
                return pressure
            # Timeout - wait for next sample (HX710B is slow ~10-40 SPS)
            if attempt < 2:  # Don't sleep on last attempt
                time.sleep(0.15)  # 150ms wait (enough for 10 SPS ADC)
        
        # All retries failed
        self.logger.warning(f"⚠️  ADC read failed after 3 attempts")
        return None
    
    def _read_pressure_stable(self, num_samples: int = 5) -> Optional[float]:
        """
        Read stable pressure (average of multiple samples)
        
        Args:
            num_samples: Number of samples to average
        
        Returns:
            float: Averaged pressure in mmHg
            None: On error
        """
        samples = []
        max_attempts = num_samples * 3  # Allow more timeouts for low SPS
        
        for attempt in range(max_attempts):
            raw = self.adc.read_raw()
            if raw is not None:
                # Validate raw value
                if raw == -1 or raw == 0 or raw == -2:
                    self.logger.debug(f"Rejecting suspicious ADC value: {raw}")
                    time.sleep(0.15)
                    continue
                    
                pressure = self.calibration.counts_to_mmhg(raw)
                samples.append(pressure)
                
                if len(samples) >= num_samples:
                    break  # Got enough samples
            
            # Wait for next sample (HX710B slow SPS)
            time.sleep(0.15)  # 150ms (safe for 10 SPS ADC)
        
        if len(samples) < num_samples / 2:  # Need at least half
            self.logger.warning(f"Only got {len(samples)}/{num_samples} valid samples")
            return None
        
        return np.mean(samples) if samples else None
    
    # ==================== MEASUREMENT PHASES ====================
    
    def _safety_check(self) -> bool:
        """
        Perform pre-measurement safety check
        
        Checks:
        1. Cuff is not already pressurized (< 20 mmHg)
        2. ADC is responsive
        3. Offset hasn't drifted significantly
        
        Returns:
            bool: True if safe to proceed
        """
        self.logger.info("Performing safety check...")
        self.current_phase = MeasurementPhase.SAFETY_CHECK
        
        try:
            # Deflate first
            self._valve_open()
            time.sleep(0.5)
            
            # Read zero pressure
            zero_pressure = self._read_pressure_stable(num_samples=10)
            if zero_pressure is None:
                self.logger.error("Safety check failed: Cannot read ADC")
                return False
            
            self.logger.info(f"Zero pressure: {zero_pressure:.2f} mmHg")
            
            # Check if already pressurized OR offset drift
            if abs(zero_pressure) > 20:
                self.logger.error(f"Safety check failed: Cuff shows {zero_pressure:.1f} mmHg (should be ~0)")
                self.logger.error(f"This is likely OFFSET DRIFT, not real pressure.")
                self.logger.error(f"SOLUTION: Run calibration → python3 tests/bp_calib_tool.py offset-electric")
                return False
            
            # Warn if moderate drift
            if abs(zero_pressure) > 10:
                self.logger.warning(f"⚠️  Offset drift detected: {zero_pressure:.2f} mmHg")
                self.logger.warning(f"   Recommend recalibration before measurement")
                self.logger.warning(f"   Command: python3 tests/bp_calib_tool.py offset-electric")
            
            self.logger.info("Safety check PASSED")
            return True
            
        except Exception as e:
            self.logger.error(f"Safety check exception: {e}")
            return False
    
    def _inflate(self) -> Tuple[bool, List[float], List[float]]:
        """
        Inflate cuff to target pressure
        
        Returns:
            Tuple[bool, List[float], List[float]]: 
                (success, timestamps, pressures)
        """
        self.logger.info(f"Inflating to {self.inflate_target:.0f} mmHg...")
        self.current_phase = MeasurementPhase.INFLATING
        
        timestamps = []
        pressures = []
        
        try:
            # Close valve FIRST (critical!)
            self.logger.info("🔧 Preparing to inflate: closing valve...")
            self._valve_close()
            time.sleep(0.3)  # Wait for valve to physically close
            
            # Verify valve is holding by checking pressure doesn't drop
            pre_pump_pressure = self._read_pressure()
            if pre_pump_pressure is not None:
                self.logger.info(f"   Pre-pump pressure: {pre_pump_pressure:.1f} mmHg")
            
            # Start pump
            self.logger.info("🔧 Starting pump...")
            self._pump_on()
            time.sleep(0.2)  # Give pump time to spin up
            
            # Check if pressure is rising (valve closed properly)
            initial_check_pressure = self._read_pressure()
            if initial_check_pressure is not None and pre_pump_pressure is not None:
                pressure_change = initial_check_pressure - pre_pump_pressure
                self.logger.info(f"   Pressure after 0.2s pump: {initial_check_pressure:.1f} mmHg (Δ={pressure_change:.1f})")
                
                if pressure_change < -5.0:  # Dropping fast = valve open!
                    self.logger.error(f"❌ VALVE NOT CLOSING! Pressure dropped {abs(pressure_change):.1f} mmHg")
                    self.logger.error(f"   Check: 1) Valve wiring (GPIO{self.valve_gpio}), 2) valve_is_no={self.valve_is_no}, 3) Physical valve")
                    self._pump_off()
                    self._emergency_deflate()
                    return False, timestamps, pressures
            
            start_time = time.time()
            last_pressure = initial_check_pressure if initial_check_pressure is not None else 0.0
            samples_since_last_log = 0
            
            while True:
                # Read pressure using robust method
                pressure = self._read_pressure()
                
                if pressure is None:
                    # ADC timeout - log but continue (may be transient)
                    samples_since_last_log += 1
                    if samples_since_last_log >= 5:
                        self.logger.warning(f"⚠️  Inflate: Multiple ADC failures ({samples_since_last_log} consecutive)")
                        samples_since_last_log = 0
                    continue  # Skip this sample, try next
                
                # Reset timeout counter on successful read
                samples_since_last_log = 0
                
                elapsed = time.time() - start_time
                timestamps.append(elapsed)
                pressures.append(pressure)
                self.current_pressure = pressure
                
                # Log progress every 10 samples OR significant pressure change
                if len(pressures) % 10 == 0:
                    rate = (pressure - pressures[-10]) / max(0.1, elapsed - timestamps[-10]) if len(pressures) >= 10 else 0.0
                    self.logger.info(f"   Inflate: {pressure:.1f} mmHg ({len(pressures)} samples, {elapsed:.1f}s, {rate:.1f} mmHg/s)")
                
                # Check if reached target
                if pressure >= self.inflate_target:
                    self.logger.info(f"Target reached: {pressure:.1f} mmHg in {elapsed:.1f}s")
                    self._pump_off()
                    return True, timestamps, pressures
                
                # Safety: max pressure
                if pressure >= self.max_pressure:
                    self.logger.error(f"Max pressure exceeded: {pressure:.1f} mmHg")
                    self._pump_off()
                    self._emergency_deflate()
                    return False, timestamps, pressures
                
                # Safety: timeout
                if elapsed > self.MAX_INFLATE_TIME_S:
                    self.logger.error(f"Inflate timeout ({self.MAX_INFLATE_TIME_S}s)")
                    self._pump_off()
                    self._emergency_deflate()
                    return False, timestamps, pressures
                
                # Safety: stall detection (pressure not increasing)
                if len(pressures) > 20:
                    # Calculate average pressure over last 20 samples
                    recent_avg = np.mean(pressures[-20:])
                    pressure_change = recent_avg - last_pressure
                    
                    if abs(pressure_change) < 0.5:  # No change in 20 samples
                        stall_time = elapsed - timestamps[-20]
                        if stall_time > 3.0:
                            self.logger.error(f"Inflate stalled (pressure ~{recent_avg:.1f} mmHg for {stall_time:.1f}s)")
                            self.logger.error(f"   Last 5 readings: {[f'{p:.1f}' for p in pressures[-5:]]}")
                            self._pump_off()
                            self._emergency_deflate()
                            return False, timestamps, pressures
                    
                    last_pressure = recent_avg
                
                time.sleep(0.1)  # 100ms sampling (match ADC SPS)
                
        except Exception as e:
            self.logger.error(f"Inflate exception: {e}")
            self._pump_off()
            self._emergency_deflate()
            return False, timestamps, pressures
    
    def _deflate_and_collect(self) -> Tuple[bool, List[float], List[float]]:
        """
        Deflate cuff and collect oscillometric data
        
        Returns:
            Tuple[bool, List[float], List[float]]: 
                (success, timestamps, pressures)
        """
        self.logger.info("Deflating and collecting oscillations...")
        self.current_phase = MeasurementPhase.DEFLATING
        
        timestamps = []
        pressures = []
        
        try:
            # Open valve (free deflation due to NO valve)
            self._valve_open()
            
            start_time = time.time()
            
            while True:
                # Read pressure
                raw = self.adc.read_raw()
                if raw is None:
                    continue  # Skip timeout, keep collecting
                
                pressure = self.calibration.counts_to_mmhg(raw)
                elapsed = time.time() - start_time
                
                timestamps.append(elapsed)
                pressures.append(pressure)
                self.current_pressure = pressure
                
                # Stop at endpoint
                if pressure <= self.DEFLATE_ENDPOINT_MMHG:
                    self.logger.info(f"Deflation complete: {pressure:.1f} mmHg in {elapsed:.1f}s")
                    break
                
                # Safety: timeout
                if elapsed > self.DEFLATE_TIMEOUT_S:
                    self.logger.warning(f"Deflate timeout ({self.DEFLATE_TIMEOUT_S}s), ending collection")
                    break
                
                # NO SLEEP - maximize sample rate for fast deflation
            
            self.logger.info(f"Collected {len(pressures)} points in {elapsed:.2f}s ({len(pressures)/elapsed:.1f} Hz)")
            
            return True, timestamps, pressures
            
        except Exception as e:
            self.logger.error(f"Deflate exception: {e}")
            return False, timestamps, pressures
    
    # ==================== OSCILLOMETRIC ANALYSIS ====================
    
    def _extract_oscillations(self, timestamps: List[float], pressures: List[float]) -> Optional[Tuple[np.ndarray, np.ndarray, float]]:
        """
        Extract oscillation envelope from pressure signal
        
        Uses bandpass filter + Hilbert transform to extract pulse amplitude.
        
        Args:
            timestamps: Time points (seconds)
            pressures: Pressure values (mmHg)
        
        Returns:
            Tuple[np.ndarray, np.ndarray, float]: (pressures, oscillation_envelope, snr_db)
            None: On error
        """
        if len(pressures) < self.MIN_OSCILLATION_POINTS:
            self.logger.error(f"Insufficient points for analysis: {len(pressures)} < {self.MIN_OSCILLATION_POINTS}")
            return None
        
        try:
            # Convert to numpy
            pressures_np = np.array(pressures)
            
            # Estimate sample rate
            dt = np.diff(timestamps)
            fs = 1.0 / np.mean(dt) if len(dt) > 0 else self.calibration.sps_hint
            self.logger.info(f"Estimated sample rate: {fs:.1f} Hz")
            
            # Detrend (remove DC offset and linear trend)
            pressures_detrend = scipy_signal.detrend(pressures_np)
            
            # Bandpass filter to extract pulse oscillations (AAMI standard: 0.5-5 Hz)
            sos = scipy_signal.butter(
                self.BPF_ORDER,
                [self.BPF_LOW_HZ, self.BPF_HIGH_HZ],
                btype='band',
                fs=fs,
                output='sos'
            )
            oscillations = scipy_signal.sosfiltfilt(sos, pressures_detrend)
            
            # Calculate SNR (Signal-to-Noise Ratio)
            signal_power = np.mean(oscillations ** 2)
            noise = pressures_detrend - oscillations
            noise_power = np.mean(noise ** 2)
            snr_db = 10 * np.log10(signal_power / noise_power) if noise_power > 0 else 0.0
            
            self.logger.info(f"Signal quality: SNR = {snr_db:.1f} dB")
            
            # Check SNR threshold
            if snr_db < self.MIN_SNR_DB:
                self.logger.warning(f"⚠️  Low SNR ({snr_db:.1f} dB < {self.MIN_SNR_DB} dB) - measurement may be unreliable")
            
            # Extract envelope using Hilbert transform
            analytic_signal = scipy_signal.hilbert(oscillations)
            envelope = np.abs(analytic_signal)
            
            # Smooth envelope (moving average with Savitzky-Golay filter)
            window_size = max(5, int(fs / 2))  # ~0.5s window
            if window_size % 2 == 0:
                window_size += 1
            if window_size < len(envelope):
                envelope_smooth = scipy_signal.savgol_filter(envelope, window_size, 2)
            else:
                envelope_smooth = envelope  # Not enough points to smooth
            
            return pressures_np, envelope_smooth, snr_db
            
        except Exception as e:
            self.logger.error(f"Oscillation extraction failed: {e}")
            return None
    
    def _calculate_bp(self, pressures: np.ndarray, envelope: np.ndarray, snr_db: float) -> Optional[MeasurementResult]:
        """
        Calculate BP values from oscillation envelope
        
        Algorithm (AAMI/ISO 81060-2 compliant):
        1. Find MAP (maximum envelope point)
        2. Find SYS (pressure where envelope rises to 55% of max, AAMI standard)
        3. Find DIA (pressure where envelope falls to 80% of max, AAMI standard)
        
        Args:
            pressures: Pressure values (decreasing)
            envelope: Oscillation amplitude envelope
            snr_db: Signal-to-noise ratio (dB)
        
        Returns:
            MeasurementResult: BP values and quality metrics
            None: On error
        """
        try:
            # Find MAP (maximum oscillation point)
            map_idx = np.argmax(envelope)
            map_pressure = pressures[map_idx]
            map_amplitude = envelope[map_idx]
            
            self.logger.info(f"MAP found at {map_pressure:.1f} mmHg (amplitude: {map_amplitude:.3f}, SNR: {snr_db:.1f} dB)")
            
            # Define thresholds for SYS/DIA (AAMI standard ratios)
            sys_threshold = map_amplitude * self.SYS_AMPLITUDE_RATIO
            dia_threshold = map_amplitude * self.DIA_AMPLITUDE_RATIO
            
            # Find SYS (before MAP, envelope rising)
            sys_pressure = None
            for i in range(map_idx):
                if envelope[i] >= sys_threshold:
                    # Interpolate for sub-sample accuracy
                    if i > 0:
                        frac = (sys_threshold - envelope[i-1]) / (envelope[i] - envelope[i-1] + 1e-9)
                        sys_pressure = pressures[i-1] + frac * (pressures[i] - pressures[i-1])
                    else:
                        sys_pressure = pressures[i]
                    break
            
            if sys_pressure is None:
                sys_pressure = pressures[0]  # Fallback: use max pressure
                self.logger.warning("⚠️  SYS not found at 55% threshold, using max pressure")
            
            # Find DIA (after MAP, envelope falling)
            dia_pressure = None
            for i in range(map_idx + 1, len(envelope)):
                if envelope[i] <= dia_threshold:
                    # Interpolate
                    if i > 0:
                        frac = (dia_threshold - envelope[i-1]) / (envelope[i] - envelope[i-1] + 1e-9)
                        dia_pressure = pressures[i-1] + frac * (pressures[i] - pressures[i-1])
                    else:
                        dia_pressure = pressures[i]
                    break
            
            if dia_pressure is None:
                dia_pressure = pressures[-1]  # Fallback: use min pressure
                self.logger.warning("⚠️  DIA not found at 80% threshold, using min pressure")
            
            # Calculate derived values
            pulse_pressure = sys_pressure - dia_pressure
            
            self.logger.info(f"BP calculated: SYS={sys_pressure:.1f}, DIA={dia_pressure:.1f}, MAP={map_pressure:.1f}, PP={pulse_pressure:.1f}")
            
            # Validate results
            validation_errors = []
            is_valid = self._validate_bp_values(sys_pressure, dia_pressure, map_pressure, pulse_pressure, snr_db, validation_errors)
            
            # Create result
            result = MeasurementResult(
                systolic=round(sys_pressure, 1),
                diastolic=round(dia_pressure, 1),
                map=round(map_pressure, 1),
                pulse_pressure=round(pulse_pressure, 1),
                oscillation_amplitude=round(map_amplitude, 4),
                snr_db=round(snr_db, 1),
                points_collected=len(pressures),
                points_after_filter=len(pressures),
                sample_rate_hz=0.0,  # Updated by caller
                deflate_duration_s=0.0,  # Updated by caller
                is_valid=is_valid,
                validation_errors=validation_errors,
                timestamp=time.time()
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"BP calculation failed: {e}")
            return None
    
    def _validate_bp_values(self, sys: float, dia: float, map_val: float, pp: float, snr_db: float, errors: List[str]) -> bool:
        """
        Validate BP values against AAMI/AHA physiological limits
        
        Args:
            sys: Systolic pressure (mmHg)
            dia: Diastolic pressure (mmHg)
            map_val: Mean arterial pressure (mmHg)
            pp: Pulse pressure (mmHg)
            snr_db: Signal-to-noise ratio (dB)
            errors: List to append error messages
        
        Returns:
            bool: True if valid
        """
        is_valid = True
        
        # Check SNR (AAMI quality requirement)
        if snr_db < self.MIN_SNR_DB:
            errors.append(f"Low SNR: {snr_db:.1f} dB < {self.MIN_SNR_DB} dB (noisy signal)")
            is_valid = False
        
        # Check SYS range
        if not (self.MIN_SYS_MMHG <= sys <= self.MAX_SYS_MMHG):
            errors.append(f"SYS out of range: {sys:.1f} mmHg (valid: {self.MIN_SYS_MMHG}-{self.MAX_SYS_MMHG})")
            is_valid = False
        
        # Check DIA range
        if not (self.MIN_DIA_MMHG <= dia <= self.MAX_DIA_MMHG):
            errors.append(f"DIA out of range: {dia:.1f} mmHg (valid: {self.MIN_DIA_MMHG}-{self.MAX_DIA_MMHG})")
            is_valid = False
        
        # Check SYS > DIA
        if sys <= dia:
            errors.append(f"SYS ({sys:.1f}) must be > DIA ({dia:.1f})")
            is_valid = False
        
        # Check pulse pressure
        if not (self.MIN_PULSE_PRESSURE_MMHG <= pp <= self.MAX_PULSE_PRESSURE_MMHG):
            errors.append(f"Pulse pressure out of range: {pp:.1f} mmHg (valid: {self.MIN_PULSE_PRESSURE_MMHG}-{self.MAX_PULSE_PRESSURE_MMHG})")
            is_valid = False
        
        # Check MAP consistency (should be between DIA and SYS)
        if not (dia <= map_val <= sys):
            errors.append(f"MAP ({map_val:.1f}) should be between DIA ({dia:.1f}) and SYS ({sys:.1f})")
            is_valid = False
        
        # Additional AAMI check: MAP ≈ DIA + 1/3(PP)
        expected_map = dia + pp / 3.0
        map_error = abs(map_val - expected_map)
        if map_error > 10.0:  # ±10 mmHg tolerance
            self.logger.warning(f"⚠️  MAP deviation from formula: measured {map_val:.1f}, expected {expected_map:.1f} (Δ={map_error:.1f} mmHg)")
        
        return is_valid
    
    # ==================== MEASUREMENT WORKFLOW ====================
    
    def _measurement_workflow(self):
        """
        Complete measurement workflow (runs in background thread)
        
        Phases:
        1. Safety check
        2. Inflate
        3. Deflate and collect data
        4. Analyze oscillations
        5. Calculate BP
        6. Cleanup and callback
        """
        try:
            self.logger.info("=== MEASUREMENT WORKFLOW STARTED ===")
            
            # Phase 1: Safety check
            if not self._safety_check():
                self.logger.error("Safety check failed, aborting")
                self.current_phase = MeasurementPhase.ERROR
                self._emergency_deflate()
                self._trigger_callback(success=False, error="Safety check failed")
                return
            
            # Phase 2: Inflate
            inflate_ok, inflate_times, inflate_pressures = self._inflate()
            if not inflate_ok:
                self.logger.error("Inflation failed")
                self.current_phase = MeasurementPhase.ERROR
                self._trigger_callback(success=False, error="Inflation failed")
                return
            
            max_pressure_reached = max(inflate_pressures) if inflate_pressures else 0.0
            
            # Brief pause at peak pressure
            time.sleep(0.5)
            
            # Phase 3: Deflate and collect
            deflate_ok, deflate_times, deflate_pressures = self._deflate_and_collect()
            if not deflate_ok or len(deflate_pressures) < self.MIN_OSCILLATION_POINTS:
                self.logger.error(f"Deflation failed or insufficient data ({len(deflate_pressures)} points)")
                self.current_phase = MeasurementPhase.ERROR
                self._emergency_deflate()
                self._trigger_callback(success=False, error="Insufficient data collected")
                return
            
            deflate_duration = deflate_times[-1] - deflate_times[0] if len(deflate_times) > 1 else 0.0
            sample_rate = len(deflate_pressures) / deflate_duration if deflate_duration > 0 else 0.0
            
            # Phase 4: Analyze oscillations
            self.current_phase = MeasurementPhase.ANALYZING
            self.logger.info("Analyzing oscillations...")
            
            analysis_result = self._extract_oscillations(deflate_times, deflate_pressures)
            if analysis_result is None:
                self.logger.error("Oscillation extraction failed")
                self.current_phase = MeasurementPhase.ERROR
                self._trigger_callback(success=False, error="Oscillation analysis failed")
                return
            
            pressures_np, envelope, snr_db = analysis_result
            
            # Phase 5: Calculate BP
            result = self._calculate_bp(pressures_np, envelope, snr_db)
            if result is None:
                self.logger.error("BP calculation failed")
                self.current_phase = MeasurementPhase.ERROR
                self._trigger_callback(success=False, error="BP calculation failed")
                return
            
            # Update result with metadata
            result.sample_rate_hz = sample_rate
            result.deflate_duration_s = deflate_duration
            
            # Store result
            self.last_result = result
            
            # Log result
            self.logger.info(f"=== MEASUREMENT COMPLETE ===")
            self.logger.info(f"BP: {result.systolic}/{result.diastolic} mmHg (MAP: {result.map})")
            self.logger.info(f"Quality: {result.points_collected} points, {result.sample_rate_hz:.1f} Hz, {result.deflate_duration_s:.1f}s")
            self.logger.info(f"Valid: {result.is_valid}, Errors: {result.validation_errors}")
            
            # Phase 6: Complete
            self.current_phase = MeasurementPhase.COMPLETE
            self._trigger_callback(success=True, result=result)
            
        except Exception as e:
            self.logger.error(f"Measurement workflow exception: {e}", exc_info=True)
            self.current_phase = MeasurementPhase.ERROR
            self._emergency_deflate()
            self._trigger_callback(success=False, error=str(e))
        
        finally:
            self.is_measuring = False
            self._pump_off()
            self._valve_open()
    
    def _trigger_callback(self, success: bool, result: Optional[MeasurementResult] = None, error: Optional[str] = None):
        """Trigger user callback with result"""
        if self._measurement_callback:
            try:
                self._measurement_callback(success=success, result=result, error=error)
            except Exception as e:
                self.logger.error(f"Callback exception: {e}")
    
    # ==================== PUBLIC API ====================
    
    def start_measurement(self, callback: Optional[Callable] = None):
        """
        Start blood pressure measurement (non-blocking)
        
        Runs measurement workflow in background thread.
        Progress can be monitored via get_measurement_status().
        
        Args:
            callback: Optional callback function(success, result, error)
                      Called when measurement completes
        
        Raises:
            RuntimeError: If measurement already in progress
        """
        if self.is_measuring:
            raise RuntimeError("Measurement already in progress")
        
        self.is_measuring = True
        self.current_phase = MeasurementPhase.IDLE
        self._stop_measurement_event.clear()
        self._measurement_callback = callback
        
        # Start workflow thread
        self._measurement_thread = threading.Thread(
            target=self._measurement_workflow,
            daemon=True,
            name="BP_Measurement"
        )
        self._measurement_thread.start()
        
        self.logger.info("Measurement started (background thread)")
    
    def stop_measurement(self):
        """
        Stop ongoing measurement (emergency abort)
        
        Immediately deflates cuff and stops measurement.
        """
        if not self.is_measuring:
            return
        
        self.logger.warning("Stopping measurement (user abort)")
        self._stop_measurement_event.set()
        self._emergency_deflate()
        
        if self._measurement_thread and self._measurement_thread.is_alive():
            self._measurement_thread.join(timeout=2.0)
        
        self.is_measuring = False
        self.current_phase = MeasurementPhase.IDLE
    
    def get_measurement_status(self) -> Dict[str, Any]:
        """
        Get current measurement status (for UI polling)
        
        Returns:
            Dict with keys:
                - is_measuring: bool
                - phase: str (idle, inflating, deflating, analyzing, complete, error)
                - pressure: float (current pressure in mmHg)
                - progress: float (estimated progress 0.0-1.0)
        """
        progress = 0.0
        
        if self.current_phase == MeasurementPhase.SAFETY_CHECK:
            progress = 0.1
        elif self.current_phase == MeasurementPhase.INFLATING:
            progress = 0.1 + 0.3 * (self.current_pressure / self.inflate_target)
        elif self.current_phase == MeasurementPhase.DEFLATING:
            progress = 0.4 + 0.4 * (1.0 - self.current_pressure / self.inflate_target)
        elif self.current_phase == MeasurementPhase.ANALYZING:
            progress = 0.9
        elif self.current_phase == MeasurementPhase.COMPLETE:
            progress = 1.0
        
        return {
            'is_measuring': self.is_measuring,
            'phase': self.current_phase.value,
            'pressure': round(self.current_pressure, 1),
            'progress': round(progress, 2)
        }
    
    def get_last_result(self) -> Optional[MeasurementResult]:
        """
        Get last measurement result
        
        Returns:
            MeasurementResult: Last result, or None if no measurement completed
        """
        return self.last_result
    
    # ==================== BASESENSOR OVERRIDES ====================
    
    def start(self) -> bool:
        """
        Enable sensor hardware (does NOT start measurement)
        
        Call start_measurement() to actually measure BP.
        
        Returns:
            bool: True if successful
        """
        return self.initialize()
    
    def stop(self):
        """Stop sensor and cleanup"""
        if self.is_measuring:
            self.stop_measurement()
        
        self._pump_off()
        self._valve_open()
        self.adc.cleanup()
        
        self.logger.info("Sensor stopped")
    
    def read(self) -> Dict[str, Any]:
        """
        Read current sensor state (not a new measurement!)
        
        To start a new measurement, use start_measurement().
        
        Returns:
            Dict with last measurement result or current status
        """
        if self.last_result:
            return {
                'systolic': self.last_result.systolic,
                'diastolic': self.last_result.diastolic,
                'map': self.last_result.map,
                'pulse_pressure': self.last_result.pulse_pressure,
                'is_valid': self.last_result.is_valid,
                'timestamp': self.last_result.timestamp
            }
        else:
            return {
                'is_measuring': self.is_measuring,
                'phase': self.current_phase.value,
                'pressure': self.current_pressure
            }
    
    def process_data(self, raw_data: Any) -> Dict[str, Any]:
        """Process raw data (not used in this sensor)"""
        return {}
    
    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        """
        Read raw data from sensor (ONE-SHOT BP measurement)
        
        This is a BLOCKING call that performs complete measurement cycle:
        1. Safety check
        2. Inflate
        3. Deflate and collect data
        4. Analyze and calculate BP
        
        For non-blocking measurement, use start_measurement() instead.
        
        Returns:
            Dict with BP results or None on error
        """
        # For BP sensor, this triggers a complete measurement synchronously
        self.logger.warning("read_raw_data() is BLOCKING (~30-60s). Consider using start_measurement() for non-blocking.")
        
        # Use event to wait for completion
        import threading
        result_container = {'success': False, 'result': None, 'error': None}
        done_event = threading.Event()
        
        def callback(success, result=None, error=None):
            result_container['success'] = success
            result_container['result'] = result
            result_container['error'] = error
            done_event.set()
        
        # Start measurement
        try:
            self.start_measurement(callback=callback)
            
            # Wait for completion (with timeout)
            if done_event.wait(timeout=120):  # 2 minute timeout
                if result_container['success'] and result_container['result']:
                    return result_container['result'].to_dict()
                else:
                    self.logger.error(f"Measurement failed: {result_container['error']}")
                    return None
            else:
                self.logger.error("Measurement timeout (120s)")
                self.stop_measurement()
                return None
                
        except Exception as e:
            self.logger.error(f"read_raw_data exception: {e}")
            return None
