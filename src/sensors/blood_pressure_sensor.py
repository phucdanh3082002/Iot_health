#!/usr/bin/env python3
"""
Blood Pressure Sensor - Oscillometric Method
============================================

Hệ thống đo huyết áp tự động sử dụng phương pháp oscillometric với HX710B ADC.

Architecture:
------------
- HX710BSensor (composition): ADC pressure readings
- GPIO: Pump + deflate valve control
- Signal Processing: Detrend, bandpass filter, envelope extraction
- Safety: Pressure limits, timeout, leak detection
- Algorithm: MAP detection → SYS/DIA calculation (ratio method)

Hardware Requirements:
---------------------
- MPS20N0040D-S pressure sensor (0-40 kPa / 0-300 mmHg)
- HX710B 24-bit ADC (10/40 SPS)
- Air pump (5/12V) via MOSFET + optocoupler
- Deflate valve (NO) via MOSFET + optocoupler
- Relief valve (~300 mmHg) for safety
- Blood pressure cuff

Measurement Workflow:
--------------------
1. INITIALIZE: Zero pressure, validate hardware
2. INFLATE: Pump to 165 mmHg (safety limits: soft 200, hard 250)
3. DEFLATE: Release 3-4 mmHg/s, record pressure continuously
4. ANALYZE: Extract envelope → find MAP → calculate SYS/DIA
5. CLEANUP: Full deflate, return result

Safety Features:
---------------
- Soft limit (200 mmHg): Warning + slow deflate
- Hard limit (250 mmHg): Emergency stop
- Timeout monitoring (inflate 30s, deflate 60s)
- Leak detection (pressure drop > 10 mmHg/s)
- Movement detection (high-freq noise)
- Emergency deflate function

Author: IoT Health Monitor Team
Date: 2025-10-24
Version: 1.0.0
"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple, Callable

import numpy as np
from scipy import signal
from scipy.signal import butter, filtfilt, hilbert, detrend

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from .base_sensor import BaseSensor
from .hx710b_sensor import HX710BSensor


# ==================== DATA MODELS ====================

class BPState(Enum):
    """
    State machine cho quá trình đo huyết áp
    
    Workflow:
    IDLE → INITIALIZING → INFLATING → DEFLATING → ANALYZING → COMPLETED → IDLE
                                   ↓
                           EMERGENCY_DEFLATE → ERROR → IDLE
    """
    IDLE = "idle"                           # Chờ bắt đầu đo
    INITIALIZING = "initializing"           # Chuẩn bị phần cứng
    INFLATING = "inflating"                 # Bơm tăng áp
    DEFLATING = "deflating"                 # Xả khí chậm, thu thập dữ liệu
    ANALYZING = "analyzing"                 # Xử lý tín hiệu
    COMPLETED = "completed"                 # Hoàn thành thành công
    ERROR = "error"                         # Lỗi đo
    EMERGENCY_DEFLATE = "emergency_deflate" # Xả khẩn cấp


@dataclass
class BloodPressureMeasurement:
    """
    Kết quả đo huyết áp
    
    Attributes:
        systolic: Huyết áp tâm thu (mmHg)
        diastolic: Huyết áp tâm trương (mmHg)
        map_value: Mean arterial pressure (mmHg)
        heart_rate: Nhịp tim từ dao động (BPM)
        pulse_pressure: Hiệu SYS-DIA (mmHg)
        timestamp: Thời gian đo
        quality: Chất lượng đo ('excellent', 'good', 'fair', 'poor')
        confidence: Độ tin cậy (0.0-1.0)
        validation_flags: Cờ kiểm tra AAMI
        metadata: Thông tin bổ sung (inflate_time, deflate_time, etc.)
    """
    systolic: float
    diastolic: float
    map_value: float
    heart_rate: float
    pulse_pressure: float
    timestamp: datetime
    quality: str
    confidence: float
    validation_flags: Dict[str, bool]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database/MQTT"""
        return {
            'systolic': round(self.systolic, 1),
            'diastolic': round(self.diastolic, 1),
            'map': round(self.map_value, 1),
            'heart_rate': round(self.heart_rate, 1),
            'pulse_pressure': round(self.pulse_pressure, 1),
            'timestamp': self.timestamp.isoformat(),
            'quality': self.quality,
            'confidence': round(self.confidence, 3),
            'validation': self.validation_flags,
            'metadata': self.metadata
        }


# ==================== SAFETY MONITOR ====================

class BPSafetyMonitor:
    """
    Giám sát an toàn trong quá trình đo huyết áp
    
    Responsibilities:
    - Kiểm tra giới hạn áp suất (soft/hard limits)
    - Phát hiện rò rỉ khí (leak detection)
    - Phát hiện cử động (movement detection)
    - Giám sát timeout
    - Xả khẩn cấp khi cần
    """
    
    # Pressure limits (mmHg)
    SOFT_LIMIT_MMHG = 200    # Warning + chuyển sang deflate chậm
    HARD_LIMIT_MMHG = 250    # Emergency stop (hardware failure)
    
    # Timeout limits (seconds)
    INFLATE_TIMEOUT_S = 30
    DEFLATE_TIMEOUT_S = 60
    ANALYZE_TIMEOUT_S = 10
    
    # Detection thresholds
    LEAK_THRESHOLD_MMHG_S = 20.0    # Pressure drop > 20 mmHg/s (using average rate over 1s window)
    LEAK_GRACE_PERIOD_S = 3.0        # Skip leak detection for first 3s of deflation
    NOISE_THRESHOLD = 0.3            # High-freq noise level
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        
        # State tracking
        self._phase_start_time: Optional[float] = None
        self._last_pressure: Optional[float] = None
        self._last_pressure_time: Optional[float] = None
        
        # Leak detection: Sử dụng buffer để tính average rate (giảm nhiễu)
        self._pressure_history: List[float] = []
        self._time_history: List[float] = []
        self._history_window = 10  # Số samples để tính average (1 giây @ 10 SPS)
        
        # Statistics
        self.warning_count = 0
        self.emergency_count = 0
    
    def start_phase(self, phase: BPState):
        """Bắt đầu phase mới (reset timer + pressure tracking)"""
        self._phase_start_time = time.time()
        # Reset leak detection state để tránh false positive từ phase trước
        self._last_pressure = None
        self._last_pressure_time = None
        self._pressure_history.clear()
        self._time_history.clear()
        self.logger.debug(f"Safety monitor: Started {phase.value} phase (leak detection reset)")
    
    def check_pressure_limit(self, pressure: float) -> Tuple[bool, str]:
        """
        Kiểm tra giới hạn áp suất
        
        Returns:
            (is_safe, message)
        """
        if pressure > self.HARD_LIMIT_MMHG:
            self.emergency_count += 1
            return False, f"CRITICAL: Pressure {pressure:.1f} mmHg exceeded hard limit ({self.HARD_LIMIT_MMHG})"
        
        if pressure > self.SOFT_LIMIT_MMHG:
            self.warning_count += 1
            return False, f"WARNING: Pressure {pressure:.1f} mmHg exceeded soft limit ({self.SOFT_LIMIT_MMHG})"
        
        return True, "OK"
    
    def check_timeout(self, state: BPState) -> Tuple[bool, str]:
        """
        Kiểm tra timeout theo phase
        
        Returns:
            (is_ok, message)
        """
        if self._phase_start_time is None:
            return True, "OK"
        
        elapsed = time.time() - self._phase_start_time
        
        timeout_map = {
            BPState.INFLATING: self.INFLATE_TIMEOUT_S,
            BPState.DEFLATING: self.DEFLATE_TIMEOUT_S,
            BPState.ANALYZING: self.ANALYZE_TIMEOUT_S
        }
        
        timeout = timeout_map.get(state)
        if timeout and elapsed > timeout:
            return False, f"Timeout in {state.value} phase ({elapsed:.1f}s > {timeout}s)"
        
        return True, "OK"
    
    def detect_leak(self, pressure: float, timestamp: float) -> Tuple[bool, str]:
        """
        Phát hiện rò rỉ khí (pressure drop quá nhanh)
        
        Method:
        -------
        - Sử dụng sliding window (10 samples) để tính average deflate rate
        - Giảm false positive do nhiễu hoặc dao động oscillometric ngắn hạn
        - Grace period 3s để van cơ học đóng hoàn toàn
        
        Returns:
            (no_leak, message)
        """
        # Thêm vào history
        self._pressure_history.append(pressure)
        self._time_history.append(timestamp)
        
        # Giữ tối đa N samples trong window
        if len(self._pressure_history) > self._history_window:
            self._pressure_history.pop(0)
            self._time_history.pop(0)
        
        # Cần ít nhất 2 samples để tính rate
        if len(self._pressure_history) < 2:
            return True, "OK (initializing)"
        
        # Grace period: Skip leak detection trong giây đầu
        if self._phase_start_time is not None:
            elapsed_since_phase_start = timestamp - self._phase_start_time
            if elapsed_since_phase_start < self.LEAK_GRACE_PERIOD_S:
                return True, f"OK (grace period: {elapsed_since_phase_start:.1f}s)"
        
        # Tính average deflate rate từ first → last sample trong window
        dt = self._time_history[-1] - self._time_history[0]
        
        if dt < 0.5:  # Window quá ngắn (< 0.5s), chưa đủ tin cậy
            return True, "OK (insufficient data)"
        
        dp = self._pressure_history[0] - self._pressure_history[-1]  # Áp giảm
        avg_rate = dp / dt  # mmHg/s
        
        # Log để debug
        if len(self._pressure_history) == self._history_window:
            self.logger.debug(
                f"Leak check: rate={avg_rate:.1f} mmHg/s over {dt:.1f}s "
                f"({self._pressure_history[0]:.1f} → {self._pressure_history[-1]:.1f} mmHg)"
            )
        
        # Check leak threshold
        if avg_rate > self.LEAK_THRESHOLD_MMHG_S:
            return False, f"Leak detected: pressure drop {avg_rate:.1f} mmHg/s (threshold: {self.LEAK_THRESHOLD_MMHG_S})"
        
        return True, "OK"
    
    def detect_movement(self, oscillations: np.ndarray) -> Tuple[bool, str]:
        """
        Phát hiện cử động (high-freq noise)
        
        Args:
            oscillations: Filtered oscillation signal
        
        Returns:
            (no_movement, message)
        """
        if len(oscillations) < 10:
            return True, "OK"
        
        # Calculate high-freq energy
        noise_level = np.std(np.diff(oscillations))
        
        if noise_level > self.NOISE_THRESHOLD:
            return False, f"Movement detected: noise level {noise_level:.3f}"
        
        return True, "OK"
    
    def get_stats(self) -> Dict[str, int]:
        """Get safety statistics"""
        return {
            'warning_count': self.warning_count,
            'emergency_count': self.emergency_count
        }
    
# ==================== SIGNAL PROCESSOR ====================

class OscillometricProcessor:
    """
    Xử lý tín hiệu oscillometric để tính SYS/DIA/MAP
    
    Algorithm Steps:
    ---------------
    1. Detrend: Loại bỏ DC drift (pressure ramp)
    2. Bandpass filter: 0.5-5 Hz (pulse frequency range)
    3. Envelope extraction: Hilbert transform hoặc peak detection
    4. MAP detection: Find max envelope amplitude
    5. SYS/DIA calculation: Ratio method với calibration
    6. Heart rate: Từ peak-to-peak hoặc FFT
    7. Quality assessment: SNR, peak prominence, regularity
    """
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        
        # Algorithm parameters (from config)
        self.sample_rate = config.get('sample_rate', 10.0)  # Hz (HX710B SPS)
        self.bandpass_low = config.get('bandpass_low', 0.5)  # Hz
        self.bandpass_high = config.get('bandpass_high', 5.0)  # Hz
        self.filter_order = config.get('filter_order', 4)
        
        # Ratio method parameters (calibration required)
        self.sys_ratio = config.get('sys_ratio', 0.55)  # SYS at 55% max amplitude
        self.dia_ratio = config.get('dia_ratio', 0.80)  # DIA at 80% max amplitude
        
        # Validation thresholds (AAMI standards)
        self.min_systolic = 70.0
        self.max_systolic = 200.0
        self.min_diastolic = 40.0
        self.max_diastolic = 140.0
        self.min_pulse_pressure = 20.0
        self.max_pulse_pressure = 80.0
    
    def process_deflate_data(
        self,
        pressures: List[float],
        timestamps: List[float]
    ) -> Optional[BloodPressureMeasurement]: 
        """
        Xử lý dữ liệu pha xả để tính BP
        
        Args:
            pressures: Danh sách áp suất (mmHg)
            timestamps: Danh sách timestamp (seconds)
        
        Returns:
            BloodPressureMeasurement hoặc None nếu thất bại
        """
        try:
            # Validate input
            if len(pressures) < 50:
                self.logger.warning(f"Insufficient data points: {len(pressures)} (need ≥50)")
                return None
            
            pressures_arr = np.array(pressures)
            timestamps_arr = np.array(timestamps)
            
            # Calculate ACTUAL sample rate from data
            if len(timestamps) > 1:
                total_duration = timestamps_arr[-1] - timestamps_arr[0]
                actual_sample_rate = len(timestamps) / total_duration
                self.logger.info(f"Actual sample rate: {actual_sample_rate:.1f} SPS (config: {self.sample_rate} SPS)")
                # Use actual sample rate for filtering
                self.sample_rate = actual_sample_rate
            
            # Step 1: Detrend (remove DC ramp)
            pressure_detrended = detrend(pressures_arr, type='linear')
            
            # Step 2: Bandpass filter (0.5-5 Hz)
            oscillations = self._bandpass_filter(pressure_detrended)
            
            # Step 3: Extract envelope
            envelope = self._extract_envelope(oscillations)
            
            # Log signal quality
            osc_peak_to_peak = np.max(oscillations) - np.min(oscillations)
            env_peak_to_peak = np.max(envelope) - np.min(envelope)
            self.logger.info(
                f"Signal quality: "
                f"Oscillations P-P={osc_peak_to_peak:.3f}, "
                f"Envelope P-P={env_peak_to_peak:.3f}"
            )
            
            # Step 4: Find MAP (max envelope amplitude)
            map_idx = np.argmax(envelope)
            map_pressure = pressures_arr[map_idx]
            map_amplitude = envelope[map_idx]
            
            self.logger.info(
                f"MAP detected: {map_pressure:.1f} mmHg @ idx {map_idx}/{len(pressures)} "
                f"(amplitude: {map_amplitude:.3f})"
            )
            
            # Validate signal quality
            MIN_AMPLITUDE = 0.05  # Minimum envelope amplitude (mmHg)
            if map_amplitude < MIN_AMPLITUDE:
                self.logger.error(
                    f"Oscillometric signal too weak: amplitude {map_amplitude:.3f} < {MIN_AMPLITUDE} mmHg. "
                    f"Possible causes:\n"
                    f"  1. Cuff not placed on arm (no pulse detected)\n"
                    f"  2. Cuff too loose (insufficient arterial compression)\n"
                    f"  3. Wrong cuff position (not over brachial artery)\n"
                    f"  4. Patient movement during measurement"
                )
                return None
            
            # Step 5: Calculate SYS/DIA (ratio method)
            systolic, diastolic = self._calculate_sys_dia(
                pressures_arr, envelope, map_idx, map_amplitude
            )
            
            if systolic is None or diastolic is None:
                self.logger.warning("Failed to calculate SYS/DIA")
                return None
            
            # Step 6: Calculate heart rate
            heart_rate = self._calculate_heart_rate(oscillations, timestamps_arr)
            
            # Step 7: Validate AAMI
            validation_flags = self._validate_aami(systolic, diastolic, map_pressure)
            
            if not all(validation_flags.values()):
                self.logger.warning(f"AAMI validation failed: {validation_flags}")
                # Continue anyway (let user decide)
            
            # Step 8: Assess quality
            quality = self._assess_quality(envelope, map_amplitude)
            confidence = self._calculate_confidence(envelope, validation_flags)
            
            # Create measurement result
            pulse_pressure = systolic - diastolic
            
            measurement = BloodPressureMeasurement(
                systolic=systolic,
                diastolic=diastolic,
                map_value=map_pressure,
                heart_rate=heart_rate,
                pulse_pressure=pulse_pressure,
                timestamp=datetime.now(),
                quality=quality,
                confidence=confidence,
                validation_flags=validation_flags,
                metadata={
                    'data_points': len(pressures),
                    'map_amplitude': float(map_amplitude),
                    'map_index': int(map_idx),
                    'sample_rate': self.sample_rate
                }
            )
            
            self.logger.info(
                f"BP measurement: SYS={systolic:.1f} DIA={diastolic:.1f} MAP={map_pressure:.1f} "
                f"HR={heart_rate:.1f} Quality={quality}"
            )
            
            return measurement
            
        except Exception as e:
            self.logger.error(f"Signal processing error: {e}", exc_info=True)
            return None
    
    def _bandpass_filter(self, signal_data: np.ndarray) -> np.ndarray:
        """
        Apply Butterworth bandpass filter
        
        Args:
            signal_data: Input signal
        
        Returns:
            Filtered signal
        """
        nyquist = self.sample_rate / 2.0
        low = self.bandpass_low / nyquist
        high = self.bandpass_high / nyquist
        
        # Clamp frequencies to valid range (0 < Wn < 1)
        low = max(0.01, min(low, 0.95))
        high = max(low + 0.05, min(high, 0.95))  # high phải > low
        
        self.logger.debug(
            f"Bandpass filter: {self.bandpass_low:.1f}-{self.bandpass_high:.1f} Hz "
            f"(Wn: {low:.3f}-{high:.3f}, Nyquist: {nyquist:.1f} Hz)"
        )
        
        b, a = butter(self.filter_order, [low, high], btype='band')
        filtered = filtfilt(b, a, signal_data)
        
        return filtered
    
    def _extract_envelope(self, oscillations: np.ndarray) -> np.ndarray:
        """
        Extract envelope using Hilbert transform
        
        Args:
            oscillations: Bandpass filtered signal
        
        Returns:
            Envelope (absolute value of analytic signal)
        """
        analytic_signal = hilbert(oscillations)
        envelope = np.abs(analytic_signal)
        
        # Smooth envelope (moving average)
        window_size = max(3, int(self.sample_rate / 5))  # ~0.2s window
        if window_size % 2 == 0:
            window_size += 1
        
        envelope_smooth = signal.savgol_filter(envelope, window_size, 2)
        
        return envelope_smooth
    
    def _calculate_sys_dia(
        self,
        pressures: np.ndarray,
        envelope: np.ndarray,
        map_idx: int,
        map_amplitude: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate SYS/DIA using ratio method (Oscillometric standard)
        
        Algorithm:
        ---------
        1. Tính thresholds: sys_threshold = sys_ratio × max_amplitude
                           dia_threshold = dia_ratio × max_amplitude
        2. SYS: Tìm điểm đầu tiên envelope vượt sys_threshold (trước MAP, khi deflate xuống)
        3. DIA: Tìm điểm đầu tiên envelope giảm xuống dưới dia_threshold (sau MAP)
        
        Ratios (cần calibration):
        - sys_ratio: 0.45-0.60 (default 0.55) - 55% max amplitude
        - dia_ratio: 0.75-0.85 (default 0.80) - 80% max amplitude
        
        Returns:
            (systolic, diastolic) or (None, None) if failed
        """
        sys_threshold = map_amplitude * self.sys_ratio
        dia_threshold = map_amplitude * self.dia_ratio
        
        self.logger.debug(
            f"Thresholds: SYS={sys_threshold:.3f} ({self.sys_ratio*100:.0f}%), "
            f"DIA={dia_threshold:.3f} ({self.dia_ratio*100:.0f}%)"
        )
        
        # ========== FIND SYS (before MAP) ==========
        # Tìm điểm envelope vượt sys_threshold khi áp giảm (envelope tăng)
        sys_idx = self._find_crossing(
            envelope[:map_idx], 
            sys_threshold, 
            direction='up'  # Envelope tăng khi áp giảm trong pha deflate
        )
        
        if sys_idx is None:
            self.logger.warning("Cannot find SYS crossing point")
            # Fallback: estimate từ MAP (rough approximation)
            systolic = pressures[0] if len(pressures) > 0 else None
            if systolic is None:
                return None, None
            self.logger.warning(f"Using fallback SYS estimate: {systolic:.1f} mmHg")
        else:
            systolic = pressures[sys_idx]
            self.logger.debug(f"SYS found at idx={sys_idx}, pressure={systolic:.1f} mmHg")
        
        # ========== FIND DIA (after MAP) ==========
        # Tìm điểm envelope giảm xuống dưới dia_threshold
        dia_idx = self._find_crossing(
            envelope[map_idx:], 
            dia_threshold, 
            direction='down'  # Envelope giảm khi áp tiếp tục giảm
        )
        
        if dia_idx is None:
            self.logger.warning("Cannot find DIA crossing point")
            # Fallback: estimate từ MAP
            diastolic = pressures[-1] if len(pressures) > 0 else None
            if diastolic is None:
                return None, None
            self.logger.warning(f"Using fallback DIA estimate: {diastolic:.1f} mmHg")
        else:
            diastolic = pressures[map_idx + dia_idx]
            self.logger.debug(f"DIA found at idx={map_idx + dia_idx}, pressure={diastolic:.1f} mmHg")
        
        # ========== VALIDATION ==========
        # Check: SYS > MAP > DIA (physiological requirement)
        map_pressure = pressures[map_idx]
        
        if not (diastolic < map_pressure < systolic):
            self.logger.error(
                f"Invalid BP relationship: "
                f"DIA={diastolic:.1f} < MAP={map_pressure:.1f} < SYS={systolic:.1f} "
                f"(should be DIA < MAP < SYS)"
            )
            return None, None
        
        # Check: Pulse pressure reasonable (20-100 mmHg)
        pulse_pressure = systolic - diastolic
        if not (20.0 <= pulse_pressure <= 100.0):
            self.logger.warning(
                f"Unusual pulse pressure: {pulse_pressure:.1f} mmHg (normal: 20-100)"
            )
            # Continue anyway (let AAMI validation decide)
        
        return systolic, diastolic
    
    def _find_crossing(
        self,
        signal_data: np.ndarray,
        threshold: float,
        direction: str = 'down'
    ) -> Optional[int]:
        """
        Find first crossing point
        
        Args:
            signal_data: Input signal
            threshold: Threshold value
            direction: 'up' or 'down'
        
        Returns:
            Index of crossing or None
        """
        if direction == 'down':
            # Signal decreases below threshold
            mask = signal_data > threshold
            diff = np.diff(mask.astype(int))
            crossings = np.where(diff == -1)[0]
        else:
            # Signal increases above threshold
            mask = signal_data < threshold
            diff = np.diff(mask.astype(int))
            crossings = np.where(diff == -1)[0]
        
        if len(crossings) == 0:
            return None
        
        return crossings[0]
    
    def _calculate_heart_rate(
        self,
        oscillations: np.ndarray,
        timestamps: np.ndarray
    ) -> float:
        """
        Calculate heart rate from oscillations
        
        Method: Peak-to-peak interval → BPM
        
        Returns:
            Heart rate (BPM)
        """
        # Find peaks
        peaks, _ = signal.find_peaks(oscillations, distance=int(self.sample_rate * 0.5))
        
        if len(peaks) < 2:
            self.logger.warning("Insufficient peaks for HR calculation")
            return 0.0
        
        # Calculate intervals
        peak_times = timestamps[peaks]
        intervals = np.diff(peak_times)
        
        # Average interval → BPM
        avg_interval = np.median(intervals)
        heart_rate = 60.0 / avg_interval if avg_interval > 0 else 0.0
        
        # Sanity check (40-180 BPM)
        if not (40.0 <= heart_rate <= 180.0):
            self.logger.warning(f"Unrealistic HR: {heart_rate:.1f} BPM")
            return 0.0
        
        return heart_rate
    
    def _validate_aami(
        self,
        systolic: float,
        diastolic: float,
        map_value: float
    ) -> Dict[str, bool]:
        """
        Validate measurement theo chuẩn AAMI
        
        Returns:
            Dict of validation flags
        """
        flags = {}
        
        # Systolic range
        flags['systolic_range'] = self.min_systolic <= systolic <= self.max_systolic
        
        # Diastolic range
        flags['diastolic_range'] = self.min_diastolic <= diastolic <= self.max_diastolic
        
        # Pulse pressure
        pulse_pressure = systolic - diastolic
        flags['pulse_pressure'] = self.min_pulse_pressure <= pulse_pressure <= self.max_pulse_pressure
        
        # MAP relationship (DIA < MAP < SYS)
        flags['map_order'] = diastolic < map_value < systolic
        
        return flags
    
    def _assess_quality(self, envelope: np.ndarray, map_amplitude: float) -> str:
        """
        Đánh giá chất lượng đo
        
        Criteria:
        - SNR (signal-to-noise ratio)
        - Peak prominence
        - Envelope regularity
        
        Returns:
            'excellent', 'good', 'fair', or 'poor'
        """
        # Calculate SNR (simple estimation)
        signal_power = map_amplitude ** 2
        noise_power = np.var(envelope - signal.savgol_filter(envelope, 11, 2))
        snr = 10 * np.log10(signal_power / noise_power) if noise_power > 0 else 0.0
        
        # Quality thresholds
        if snr > 20:
            return 'excellent'
        elif snr > 15:
            return 'good'
        elif snr > 10:
            return 'fair'
        else:
            return 'poor'
    
    def _calculate_confidence(
        self,
        envelope: np.ndarray,
        validation_flags: Dict[str, bool]
    ) -> float:
        """
        Tính độ tin cậy (0.0-1.0)
        
        Based on:
        - Validation flags
        - Envelope quality
        
        Returns:
            Confidence score (0.0-1.0)
        """
        # Base confidence from validation
        passed_checks = sum(validation_flags.values())
        total_checks = len(validation_flags)
        confidence = passed_checks / total_checks
        
        # Adjust by envelope quality (coefficient of variation)
        cv = np.std(envelope) / np.mean(envelope) if np.mean(envelope) > 0 else 1.0
        confidence *= (1.0 - min(cv, 0.5))
        
        return max(0.0, min(1.0, confidence))


# ==================== HARDWARE CONTROLLER ====================

class BPHardwareController:
    """
    Điều khiển phần cứng (bơm + van xả)
    
    GPIO Control:
    - Pump: GPIO output → optocoupler → MOSFET → pump
    - Valve: GPIO output → optocoupler → MOSFET → valve (NO)
    
    Safety:
    - Diode flyback cho inductive load
    - Separate power supply cho pump/valve
    - Common ground
    """
    
    def __init__(self, pump_gpio: int, valve_gpio: int, logger: logging.Logger):
        self.pump_gpio = pump_gpio
        self.valve_gpio = valve_gpio
        self.logger = logger
        
        self._is_initialized = False
    
    def initialize(self) -> bool:
        """Initialize GPIO pins"""
        if not GPIO:
            self.logger.error("RPi.GPIO not available")
            return False
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup outputs (initial: OFF)
            GPIO.setup(self.pump_gpio, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.valve_gpio, GPIO.OUT, initial=GPIO.LOW)
            
            self._is_initialized = True
            self.logger.info(f"Hardware initialized (Pump=GPIO{self.pump_gpio}, Valve=GPIO{self.valve_gpio})")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Hardware init failed: {e}")
            return False
    
    def pump_on(self):
        """Turn pump ON"""
        if self._is_initialized and GPIO:
            GPIO.output(self.pump_gpio, GPIO.HIGH)
            self.logger.debug("Pump ON")
    
    def pump_off(self):
        """Turn pump OFF"""
        if self._is_initialized and GPIO:
            GPIO.output(self.pump_gpio, GPIO.LOW)
            self.logger.debug("Pump OFF")
    
    def valve_open(self):
        """Open deflate valve (NO valve: LOW = OPEN)"""
        if self._is_initialized and GPIO:
            GPIO.output(self.valve_gpio, GPIO.LOW)  # NO valve: LOW = open
            self.logger.debug("Valve OPEN (GPIO LOW)")
    
    def valve_close(self):
        """Close deflate valve (NO valve: HIGH = CLOSED)"""
        if self._is_initialized and GPIO:
            GPIO.output(self.valve_gpio, GPIO.HIGH)  # NO valve: HIGH = closed
            self.logger.debug("Valve CLOSED (GPIO HIGH)")
    
    def emergency_deflate(self):
        """
        Xả khẩn cấp
        
        Actions:
        1. Turn pump OFF immediately
        2. Open valve fully
        3. Log event
        """
        self.logger.warning("⚠️  EMERGENCY DEFLATE TRIGGERED")
        self.pump_off()
        self.valve_open()
    
    def cleanup(self):
        """Cleanup GPIO (safe state)"""
        if self._is_initialized and GPIO:
            try:
                self.pump_off()
                self.valve_close()
                # Don't call GPIO.cleanup() - other sensors may use GPIO
                self._is_initialized = False
                self.logger.info("Hardware cleaned up")
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")


# ==================== MAIN BLOOD PRESSURE SENSOR ====================

class BloodPressureSensor(BaseSensor):
    """
    High-level Blood Pressure Sensor
    
    Tích hợp:
    - HX710BSensor (ADC pressure readings)
    - BPHardwareController (pump/valve control)
    - BPSafetyMonitor (safety checks)
    - OscillometricProcessor (signal processing)
    
    Public API:
    ----------
    - start_measurement(callback): Bắt đầu đo BP (non-blocking)
    - stop_measurement(emergency): Dừng đo (optional emergency deflate)
    - get_last_measurement(): Lấy kết quả gần nhất
    - get_state(): Lấy state hiện tại
    
    Configuration (app_config.yaml):
    -------------------------------
    sensors:
      blood_pressure:
        enabled: true
        inflate_target_mmhg: 165
        deflate_rate_mmhg_s: 3.0
        max_pressure_mmhg: 200
        pump_gpio: 26
        valve_gpio: 16
        hx710b:
          # HX710BSensor config...
        algorithm:
          sample_rate: 10.0
          sys_ratio: 0.55
          dia_ratio: 0.80
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize Blood Pressure Sensor
        
        Args:
            name: Sensor name (e.g., "BloodPressure")
            config: Configuration dictionary
        """
        super().__init__(name, config)
        
        # ========== COMPONENTS (COMPOSITION) ==========
        
        # ADC sensor (HX710B)
        self.adc_sensor = HX710BSensor("BP_ADC", config['hx710b'])
        
        # Hardware controller (pump + valve)
        self.hardware = BPHardwareController(
            pump_gpio=config['pump_gpio'],
            valve_gpio=config['valve_gpio'],
            logger=self.logger
        )
        
        # Safety monitor
        self.safety = BPSafetyMonitor(self.logger)
        
        # Signal processor
        self.processor = OscillometricProcessor(
            config=config.get('algorithm', {}),
            logger=self.logger
        )
        
        # ========== MEASUREMENT PARAMETERS ==========
        
        self.inflate_target = config.get('inflate_target_mmhg', 190.0)
        self.deflate_rate = config.get('deflate_rate_mmhg_s', 3.0)
        self.max_pressure = config.get('max_pressure_mmhg', 250.0)
        
        # ========== STATE MACHINE ==========
        
        self.state = BPState.IDLE
        self.state_lock = threading.Lock()
        
        # ========== DATA BUFFERS ==========
        
        self.pressure_buffer: List[float] = []
        self.timestamp_buffer: List[float] = []
        
        # ========== RESULT ==========
        
        self.last_measurement: Optional[BloodPressureMeasurement] = None
        self.measurement_callback: Optional[Callable] = None
        self.measurement_thread: Optional[threading.Thread] = None
        
        self.logger.info(
            f"BloodPressureSensor initialized: "
            f"Inflate={self.inflate_target}mmHg, Deflate={self.deflate_rate}mmHg/s"
        )
    
    # ==================== PUBLIC API ====================
    
    def start_measurement(self, callback: Optional[Callable[[BloodPressureMeasurement], None]] = None) -> bool:
        """
        Bắt đầu đo huyết áp (non-blocking)
        
        Args:
            callback: Function(measurement: BloodPressureMeasurement) khi hoàn thành
        
        Returns:
            bool: True nếu bắt đầu thành công
        """
        with self.state_lock:
            if self.state != BPState.IDLE:
                self.logger.warning(f"Cannot start: current state is {self.state.value}")
                return False
            
            self.state = BPState.INITIALIZING
        
        self.measurement_callback = callback
        self.measurement_thread = threading.Thread(
            target=self._measurement_loop,
            daemon=True,
            name="BP_Measurement"
        )
        self.measurement_thread.start()
        
        self.logger.info("Started blood pressure measurement")
        return True
    
    def stop_measurement(self, emergency: bool = False):
        """
        Dừng đo huyết áp
        
        Args:
            emergency: Nếu True, xả khẩn cấp ngay lập tức
        """
        self.logger.info(f"Stopping measurement (emergency={emergency})")
        
        if emergency:
            self.hardware.emergency_deflate()
            self._set_state(BPState.EMERGENCY_DEFLATE)
        
        self._cleanup_hardware()
        self._set_state(BPState.IDLE)
    
    def get_last_measurement(self) -> Optional[BloodPressureMeasurement]:
        """Lấy kết quả đo gần nhất"""
        return self.last_measurement
    
    def get_state(self) -> BPState:
        """Lấy state hiện tại"""
        with self.state_lock:
            return self.state
    
    # ==================== MEASUREMENT WORKFLOW ====================
    
    def _measurement_loop(self):
        """
        Main measurement loop (chạy trong thread riêng)
        
        Workflow:
        1. INITIALIZE: Setup hardware, zero pressure
        2. INFLATE: Pump to target
        3. DEFLATE: Release slowly, record data
        4. ANALYZE: Process signal → BP calculation
        5. CLEANUP: Full deflate, return result
        """
        try:
            # Phase 1: Initialize
            if not self._initialize_measurement():
                self._set_state(BPState.ERROR)
                return
            
            # Phase 2: Inflate
            if not self._inflate_phase():
                self._set_state(BPState.ERROR)
                self._cleanup_hardware()
                return
            
            # Phase 3: Deflate (collect data)
            if not self._deflate_phase():
                self._set_state(BPState.ERROR)
                self._cleanup_hardware()
                return
            
            # Phase 4: Analyze
            result = self._analyze_phase()
            
            if result:
                self.last_measurement = result
                self._set_state(BPState.COMPLETED)
                
                # Call callback
                if self.measurement_callback:
                    try:
                        self.measurement_callback(result)
                    except Exception as e:
                        self.logger.error(f"Callback error: {e}")
            else:
                self._set_state(BPState.ERROR)
            
            # Phase 5: Cleanup
            self._cleanup_hardware()
            
            # Reset to IDLE after 2s
            time.sleep(2.0)
            self._set_state(BPState.IDLE)
            
        except Exception as e:
            self.logger.error(f"Measurement loop error: {e}", exc_info=True)
            self._set_state(BPState.ERROR)
            self._cleanup_hardware()
    
    def _initialize_measurement(self) -> bool:
        """
        Phase 1: Initialize hardware
        
        Steps:
        1. Start ADC sensor
        2. Initialize pump/valve GPIO
        3. Open valve → ensure 0 mmHg
        4. Verify pressure stable at 0
        
        Returns:
            bool: Success
        """
        self._set_state(BPState.INITIALIZING)
        self.safety.start_phase(BPState.INITIALIZING)
        
        self.logger.info("Initializing measurement...")
        
        # Start ADC sensor
        if not self.adc_sensor.start():
            self.logger.error("Failed to start ADC sensor")
            return False
        
        # Initialize hardware
        if not self.hardware.initialize():
            self.logger.error("Failed to initialize hardware")
            return False
        
        # Ensure pump OFF, valve OPEN
        self.hardware.pump_off()
        self.hardware.valve_open()
        
        # Wait for deflation (5s)
        self.logger.info("Deflating to zero...")
        time.sleep(5.0)
        
        # Close valve
        self.hardware.valve_close()
        
        # Verify zero pressure
        time.sleep(0.5)
        pressure_data = self.adc_sensor.get_latest_data()
        
        if pressure_data is None:
            self.logger.error("Failed to read initial pressure")
            return False
        
        initial_pressure = pressure_data['pressure_mmhg']
        self.logger.info(f"Initial pressure: {initial_pressure:.1f} mmHg")
        
        if abs(initial_pressure) > 10.0:
            self.logger.warning(f"High initial pressure: {initial_pressure:.1f} mmHg (expected ~0)")
            # Continue anyway
        
        # Clear buffers
        self.pressure_buffer.clear()
        self.timestamp_buffer.clear()
        
        return True
    
    def _inflate_phase(self) -> bool:
        """
        Phase 2: Inflate cuff to target pressure
        
        Steps:
        1. Turn pump ON
        2. Monitor pressure (safety checks)
        3. Stop at target or limits
        
        Returns:
            bool: Success
        """
        self._set_state(BPState.INFLATING)
        self.safety.start_phase(BPState.INFLATING)
        
        self.logger.info(f"Inflating to {self.inflate_target:.1f} mmHg...")
        
        # Close valve, turn pump ON
        self.hardware.valve_close()
        self.hardware.pump_on()
        
        while True:
            # Read pressure
            pressure_data = self.adc_sensor.get_latest_data()
            
            if pressure_data is None:
                self.logger.warning("ADC read failed during inflate")
                time.sleep(0.1)
                continue
            
            pressure = pressure_data['pressure_mmhg']
            
            # Safety check: hard limit
            is_safe, msg = self.safety.check_pressure_limit(pressure)
            if not is_safe and "CRITICAL" in msg:
                self.logger.error(msg)
                self.hardware.emergency_deflate()
                return False
            
            # Safety check: soft limit
            if not is_safe and "WARNING" in msg:
                self.logger.warning(msg)
                break  # Switch to deflate
            
            # Check timeout
            is_ok, msg = self.safety.check_timeout(BPState.INFLATING)
            if not is_ok:
                self.logger.error(msg)
                self.hardware.pump_off()
                return False
            
            # Check target reached
            if pressure >= self.inflate_target:
                self.logger.info(f"Target reached: {pressure:.1f} mmHg")
                break
            
            time.sleep(0.1)
        
        # Turn pump OFF
        self.hardware.pump_off()
        
        return True
    
    def _deflate_phase(self) -> bool:
        """
        Phase 3: Passive deflation (Oscillometric method - giống máy thương mại)
        
        Workflow:
        --------
        1. Pump OFF (dừng bơm)
        2. Van GIỮ ĐÓNG (GPIO HIGH cho van NO) → rò rỉ tự nhiên qua cuff
        3. Thu thập áp + dao động liên tục (~10-40 SPS từ HX710B)
        4. Dừng khi áp < 30 mmHg
        5. Mở van hoàn toàn (GPIO LOW) → xả nhanh còn lại
        
        Tốc độ xả:
        ----------
        - Pha passive (van đóng): 2-3 mmHg/s (rò qua cuff)
        - Pha emergency (van mở): ~50 mmHg/s (xả nhanh)
        
        Safety:
        -------
        - Leak detection: Nếu rò quá nhanh (>10 mmHg/s) → mở van
        - Timeout: Nếu xả quá chậm (>120s) → mở van
        
        Returns:
            bool: Success
        """
        self._set_state(BPState.DEFLATING)
        self.safety.start_phase(BPState.DEFLATING)
        
        self.logger.info("Deflating passively (natural leakage via cuff)...")
        
        # ========== PASSIVE DEFLATION SETUP ==========
        # Pump OFF + Valve CLOSED → rò rỉ tự nhiên qua cuff (~2-3 mmHg/s)
        self.hardware.pump_off()
        self.hardware.valve_close()  # ← QUAN TRỌNG: GIỮ ĐÓNG để passive deflation
        
        # Delay 0.5s: Cho van cơ học thời gian đóng hoàn toàn
        time.sleep(0.5)
        self.logger.debug("Valve closed - waiting for pressure to stabilize...")
        
        # Start recording
        start_time = time.time()
        last_pressure = None
        last_log_time = start_time
        
        # Deflate rate tracking
        deflate_rates = []
        
        # ========== DATA COLLECTION LOOP ==========
        while True:
            # ========== READ PRESSURE ==========
            pressure_data = self.adc_sensor.get_latest_data()
            
            if pressure_data is None:
                self.logger.warning("ADC read failed during deflate")
                time.sleep(0.1)
                continue
            
            pressure = pressure_data['pressure_mmhg']
            timestamp = time.time()
            
            # ========== RECORD DATA ==========
            self.pressure_buffer.append(pressure)
            self.timestamp_buffer.append(timestamp)
            
            # ========== CALCULATE DEFLATE RATE ==========
            if last_pressure is not None and len(self.timestamp_buffer) > 1:
                dt = timestamp - self.timestamp_buffer[-2]
                if dt > 0.01:  # Ignore too-fast samples
                    dp = last_pressure - pressure
                    rate = dp / dt  # mmHg/s
                    deflate_rates.append(rate)
                    
                    # Log deflate rate every 5s
                    if timestamp - last_log_time >= 5.0:
                        avg_rate = np.mean(deflate_rates[-50:]) if len(deflate_rates) > 0 else 0.0
                        self.logger.debug(
                            f"Deflate: {pressure:.1f} mmHg | "
                            f"Rate: {avg_rate:.2f} mmHg/s | "
                            f"Samples: {len(self.pressure_buffer)}"
                        )
                        last_log_time = timestamp
            
            last_pressure = pressure
            
            # ========== SAFETY CHECKS ==========
            
            # Safety 1: Leak detection (too fast)
            is_ok, msg = self.safety.detect_leak(pressure, timestamp)
            if not is_ok:
                self.logger.error(f"Safety abort: {msg}")
                # Emergency: Mở van hoàn toàn để xả nhanh
                self.hardware.valve_open()
                time.sleep(3.0)
                self.hardware.valve_close()
                return False
            
            # Safety 2: Timeout (too slow)
            elapsed = timestamp - start_time
            if elapsed > 120.0:  # 2 minutes max
                avg_rate = np.mean(deflate_rates) if deflate_rates else 0.0
                self.logger.error(
                    f"Deflation timeout ({elapsed:.1f}s). "
                    f"Avg rate: {avg_rate:.2f} mmHg/s (expected ~2-3)"
                )
                # Force: Mở van để tăng tốc xả
                self.logger.warning("Opening valve to speed up deflation...")
                self.hardware.valve_open()
                time.sleep(5.0)
                self.hardware.valve_close()
                return False
            
            # ========== CHECK COMPLETION ==========
            if pressure < 30.0:
                self.logger.info(f"Deflation complete: {pressure:.1f} mmHg")
                break
            
            # Sample at ~20 Hz (limited by HX710B SPS ~10-40)
            time.sleep(0.05)
        
        # ========== POST-DEFLATION ==========
        
        # Ensure full deflate (mở van hoàn toàn)
        self.logger.info("Ensuring complete deflation...")
        self.hardware.valve_open()  # Xả nhanh còn lại
        time.sleep(2.0)
        self.hardware.valve_close()
        
        # ========== STATISTICS ==========
        
        elapsed = time.time() - start_time
        num_samples = len(self.pressure_buffer)
        
        if num_samples > 1 and elapsed > 0:
            actual_sps = num_samples / elapsed
            pressure_drop = self.pressure_buffer[0] - self.pressure_buffer[-1]
            avg_rate = pressure_drop / elapsed
            
            self.logger.info(
                f"Deflate phase complete:\n"
                f"  - Duration: {elapsed:.1f} s\n"
                f"  - Samples: {num_samples} ({actual_sps:.1f} SPS)\n"
                f"  - Pressure drop: {self.pressure_buffer[0]:.1f} → {self.pressure_buffer[-1]:.1f} mmHg\n"
                f"  - Avg deflate rate: {avg_rate:.2f} mmHg/s"
            )
            
            # Validate deflate rate
            if avg_rate < 1.0:
                self.logger.warning(
                    f"⚠️  Slow deflate rate ({avg_rate:.2f} mmHg/s). "
                    f"Check cuff seal or valve seal."
                )
            elif avg_rate > 5.0:
                self.logger.warning(
                    f"⚠️  Fast deflate rate ({avg_rate:.2f} mmHg/s). "
                    f"Possible cuff leak - may affect measurement quality."
                )
            else:
                self.logger.info(f"✅ Deflate rate within target range (2-3 mmHg/s)")
        else:
            self.logger.error("Insufficient deflate data collected")
            return False
        
        return True
    
    def _analyze_phase(self) -> Optional[BloodPressureMeasurement]:
        """
        Phase 4: Analyze data → calculate BP
        
        Returns:
            BloodPressureMeasurement or None
        """
        self._set_state(BPState.ANALYZING)
        self.safety.start_phase(BPState.ANALYZING)
        
        self.logger.info("Analyzing data...")
        
        # Process signal
        result = self.processor.process_deflate_data(
            self.pressure_buffer,
            self.timestamp_buffer
        )
        
        if result:
            self.logger.info(f"Analysis complete: {result.systolic:.1f}/{result.diastolic:.1f} mmHg")
        else:
            self.logger.error("Analysis failed")
        
        return result
    
    def _cleanup_hardware(self):
        """
        Phase 5: Cleanup hardware (safe state)
        
        Actions:
        1. Turn pump OFF
        2. Open valve fully
        3. Wait 5s
        4. Close valve
        """
        self.logger.info("Cleaning up hardware...")
        
        self.hardware.pump_off()
        self.hardware.valve_open()
        
        time.sleep(5.0)
        
        self.hardware.valve_close()
    
    def _set_state(self, new_state: BPState):
        """Update state (thread-safe)"""
        with self.state_lock:
            old_state = self.state
            self.state = new_state
            self.logger.debug(f"State: {old_state.value} → {new_state.value}")
    
    # ==================== BASESENSOR INTERFACE ====================
    
    def initialize(self) -> bool:
        """
        Initialize hardware (BaseSensor interface)
        
        Called by BaseSensor.start()
        """
        # Initialize components
        if not self.hardware.initialize():
            return False
        
        if not self.adc_sensor.start():
            return False
        
        return True
    
    def cleanup(self):
        """
        Cleanup hardware (BaseSensor interface)
        
        Called by BaseSensor.stop()
        """
        self._cleanup_hardware()
        self.hardware.cleanup()
        self.adc_sensor.stop()
    
    def read_raw_data(self) -> Optional[Dict]:
        """
        Read raw data (BaseSensor interface)
        
        Returns current pressure from ADC sensor
        """
        return self.adc_sensor.get_latest_data()
    
    def process_data(self, raw_data: Dict) -> Optional[Dict]:
        """
        Process data (BaseSensor interface)
        
        For BP sensor, this just passes through ADC data.
        Real processing happens in _analyze_phase()
        """
        return raw_data
    
    # ==================== UTILITY METHODS ====================
    
    def get_sensor_info(self) -> Dict[str, Any]:
        """Get sensor info (override BaseSensor)"""
        info = super().get_sensor_info()
        
        info.update({
            'state': self.state.value,
            'inflate_target': self.inflate_target,
            'deflate_rate': self.deflate_rate,
            'max_pressure': self.max_pressure,
            'adc_sensor': self.adc_sensor.get_sensor_info(),
            'safety_stats': self.safety.get_stats(),
            'last_measurement': self.last_measurement.to_dict() if self.last_measurement else None
        })
        
        return info


# ==================== FACTORY FUNCTION ====================

def create_blood_pressure_sensor_from_config(config: Dict[str, Any]) -> Optional[BloodPressureSensor]:
    """
    Factory function to create BloodPressureSensor from app_config.yaml
    
    Args:
        config: Sensor configuration dict (from sensors.blood_pressure in YAML)
    
    Returns:
        BloodPressureSensor instance or None if disabled/invalid
    
    Example YAML:
        sensors:
          blood_pressure:
            enabled: true
            inflate_target_mmhg: 165
            deflate_rate_mmhg_s: 3.0
            max_pressure_mmhg: 200
            pump_gpio: 26
            valve_gpio: 16
            hx710b:
              enabled: true
              gpio_dout: 6
              gpio_sck: 5
              mode: '10sps'
              calibration:
                offset_counts: 12500
                slope_mmhg_per_count: 9.536743e-06
            algorithm:
              sample_rate: 10.0
              bandpass_low: 0.5
              bandpass_high: 5.0
              sys_ratio: 0.55
              dia_ratio: 0.80
    
    Usage:
        >>> from src.sensors.blood_pressure_sensor import create_blood_pressure_sensor_from_config
        >>> import yaml
        >>> 
        >>> with open('config/app_config.yaml') as f:
        >>>     cfg = yaml.safe_load(f)
        >>> 
        >>> sensor = create_blood_pressure_sensor_from_config(cfg['sensors']['blood_pressure'])
        >>> if sensor:
        >>>     sensor.start()
        >>>     sensor.start_measurement(callback=lambda m: print(f"BP: {m.systolic}/{m.diastolic}"))
    """
    logger = logging.getLogger("BloodPressureSensor.Factory")
    
    # Check if enabled
    if not config.get('enabled', True):
        logger.info("Blood pressure sensor disabled in config")
        return None
    
    # Validate required keys
    required_keys = ['pump_gpio', 'valve_gpio', 'hx710b']
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        logger.error(f"Missing required config keys: {missing_keys}")
        return None
    
    # Create sensor
    try:
        sensor = BloodPressureSensor("BloodPressure", config)
        logger.info("BloodPressureSensor created successfully")
        return sensor
        
    except Exception as e:
        logger.error(f"Failed to create BloodPressureSensor: {e}", exc_info=True)
        return None


# ==================== MAIN (FOR TESTING) ====================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # Example config
    test_config = {
        'enabled': True,
        'inflate_target_mmhg': 165.0,
        'deflate_rate_mmhg_s': 3.0,
        'max_pressure_mmhg': 200.0,
        'pump_gpio': 26,
        'valve_gpio': 16,
        'hx710b': {
            'enabled': True,
            'gpio_dout': 6,
            'gpio_sck': 5,
            'mode': '10sps',
            'read_timeout_ms': 1000,
            'calibration': {
                'offset_counts': 0,
                'slope_mmhg_per_count': 9.536743e-06,
                'adc_inverted': False
            }
        },
        'algorithm': {
            'sample_rate': 10.0,
            'bandpass_low': 0.5,
            'bandpass_high': 5.0,
            'sys_ratio': 0.55,
            'dia_ratio': 0.80
        }
    }
    
    # Create sensor
    sensor = create_blood_pressure_sensor_from_config(test_config)
    
    if sensor:
        print("Sensor created successfully!")
        print(f"Info: {sensor.get_sensor_info()}")
        
        # Start sensor (initialize hardware)
        if sensor.start():
            print("Sensor started!")
            
            # Define callback
            def on_measurement_complete(measurement: BloodPressureMeasurement):
                print("\n" + "="*60)
                print("MEASUREMENT COMPLETE")
                print("="*60)
                print(f"Systolic:  {measurement.systolic:.1f} mmHg")
                print(f"Diastolic: {measurement.diastolic:.1f} mmHg")
                print(f"MAP:       {measurement.map_value:.1f} mmHg")
                print(f"HR:        {measurement.heart_rate:.1f} BPM")
                print(f"Quality:   {measurement.quality}")
                print(f"Confidence: {measurement.confidence:.2f}")
                print("="*60)
            
            # Start measurement
            print("\nStarting measurement...")
            sensor.start_measurement(callback=on_measurement_complete)
            
            # Wait for completion (or Ctrl+C)
            try:
                while sensor.get_state() != BPState.IDLE:
                    time.sleep(0.5)
                    state = sensor.get_state()
                    print(f"State: {state.value}", end='\r')
            except KeyboardInterrupt:
                print("\n\nStopping measurement...")
                sensor.stop_measurement(emergency=True)
            
            # Stop sensor
            sensor.stop()
            print("Sensor stopped.")
        else:
            print("Failed to start sensor")
    else:
        print("Failed to create sensor")