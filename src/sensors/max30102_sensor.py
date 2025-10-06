"""MAX30102 sensor driver with measurement window and enhanced HR/SpO₂ workflow."""
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple
from dataclasses import dataclass, field
import logging
import time
from collections import deque
import numpy as np
from .base_sensor import BaseSensor
try:
    import smbus  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - hardware optional
    smbus = None


@dataclass
class MeasurementState:
    """Trạng thái đo hiện tại."""
    heart_rate: float = 0.0
    spo2: float = 0.0
    hr_valid: bool = False
    spo2_valid: bool = False
    signal_quality_ir: float = 0.0
    signal_quality_red: float = 0.0
    window_fill: float = 0.0
    status: str = "idle"
    ready: bool = False
    readings_count: int = 0


@dataclass
class SessionState:
    """Trạng thái phiên đo."""
    active: bool = False
    start_time: float = 0.0
    elapsed: float = 0.0


@dataclass
class FingerDetectionState:
    """Trạng thái phát hiện ngón tay."""
    detected: bool = False
    baseline: float = 0.0
    baseline_ready: bool = False
    present_frames: int = 0
    absent_frames: int = 0
    signal_ratio: float = 0.0
    signal_amplitude: float = 0.0
    signal_quality: float = 0.0
    detection_score: float = 0.0
    
    def reset(self) -> None:
        """Reset về trạng thái ban đầu - KHÔNG reset baseline để giữ ổn định."""
        self.detected = False
        # KHÔNG reset baseline và baseline_ready - giữ nguyên để ổn định phát hiện
        self.present_frames = 0
        self.absent_frames = 0
        self.signal_ratio = 0.0
        self.signal_amplitude = 0.0
        self.signal_quality = 0.0
        self.detection_score = 0.0


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
REG_TEMP_INTR = 0x1F
REG_TEMP_FRAC = 0x20
REG_TEMP_CONFIG = 0x21
REG_PROX_INT_THRESH = 0x30
REG_REV_ID = 0xFE
REG_PART_ID = 0xFF


class MAX30102Hardware:
    """Low-level MAX30102 hardware helper inspired by the reference driver."""

    SAMPLE_RATE_BITS = {
        50: 0x00,
        100: 0x01,
        200: 0x02,
        400: 0x03,
        800: 0x04,
        1000: 0x05,
        1600: 0x06,
        3200: 0x07,
    }

    PULSE_WIDTH_BITS = {
        69: 0x00,
        118: 0x01,
        215: 0x02,
        411: 0x03,
    }

    ADC_RANGE_BITS = {
        2048: 0x00,
        4096: 0x01,
        8192: 0x02,
        16384: 0x03,
    }

    SAMPLE_AVERAGE_BITS = {
        1: 0x00,
        2: 0x01,
        4: 0x02,
        8: 0x03,
        16: 0x04,
        32: 0x05,
    }

    DEFAULT_ALMOST_FULL = 0x0F

    def __init__(self, channel: int = 1, address: int = 0x57, logger: Optional[logging.Logger] = None) -> None:
        if smbus is None:
            raise RuntimeError("smbus không khả dụng - không thể giao tiếp MAX30102")

        self.address = address
        self.channel = channel
        self.logger = logger or logging.getLogger(__name__)

        try:
            self.bus = smbus.SMBus(self.channel)
        except Exception as exc:  # pragma: no cover - hardware only
            raise RuntimeError(f"Không thể mở I2C bus {self.channel}: {exc}") from exc

        self.sample_rate = 100
        self.sample_average = 4
        self.pulse_width = 411
        self.adc_range = 4096
        self.led_mode = 0x03

        self.reset()
        time.sleep(0.05)
        self._clear_interrupts()

    @staticmethod
    def _closest_supported(value: int, mapping: Dict[int, int]) -> int:
        if value in mapping:
            return value
        return min(mapping.keys(), key=lambda key: abs(key - value))

    def _write_reg(self, register: int, value: int) -> None:
        self.bus.write_i2c_block_data(self.address, register, [value & 0xFF])

    def _clear_interrupts(self) -> None:
        try:
            self.bus.read_i2c_block_data(self.address, REG_INTR_STATUS_1, 1)
            self.bus.read_i2c_block_data(self.address, REG_INTR_STATUS_2, 1)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.debug("Không thể đọc thanh ghi interrupt: %s", exc)

    def reset(self) -> None:
        try:
            self._write_reg(REG_MODE_CONFIG, 0x40)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.debug("Không thể reset MAX30102: %s", exc)

    def shutdown(self) -> None:
        try:
            self._write_reg(REG_MODE_CONFIG, 0x80)
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.debug("Không thể shutdown MAX30102: %s", exc)

    def setup(
        self,
        *,
        sample_rate: int = 100,
        led_mode: int = 0x03,
        led1_pa: int = 0x24,
        led2_pa: int = 0x24,
        sample_average: int = 4,
        adc_range: int = 4096,
        pulse_width: int = 411,
        almost_full: int = DEFAULT_ALMOST_FULL,
        roll_over: bool = False,
    ) -> None:
        self.sample_rate = self._closest_supported(sample_rate, self.SAMPLE_RATE_BITS)
        self.sample_average = self._closest_supported(sample_average, self.SAMPLE_AVERAGE_BITS)
        self.pulse_width = self._closest_supported(pulse_width, self.PULSE_WIDTH_BITS)
        self.adc_range = self._closest_supported(adc_range, self.ADC_RANGE_BITS)
        self.led_mode = led_mode & 0x07

        avg_bits = self.SAMPLE_AVERAGE_BITS[self.sample_average]
        fifo_cfg = (avg_bits << 5) | ((1 if roll_over else 0) << 4) | (min(15, max(0, almost_full)) & 0x0F)

        spo2_cfg = (
            (self.PULSE_WIDTH_BITS[self.pulse_width] << 6)
            | (self.SAMPLE_RATE_BITS[self.sample_rate] << 2)
            | self.ADC_RANGE_BITS[self.adc_range]
        )

        self._clear_interrupts()
        self._write_reg(REG_INTR_ENABLE_1, 0xC0)
        self._write_reg(REG_INTR_ENABLE_2, 0x00)
        self._write_reg(REG_FIFO_WR_PTR, 0x00)
        self._write_reg(REG_OVF_COUNTER, 0x00)
        self._write_reg(REG_FIFO_RD_PTR, 0x00)
        self._write_reg(REG_FIFO_CONFIG, fifo_cfg)
        self._write_reg(REG_MODE_CONFIG, self.led_mode)
        self._write_reg(REG_SPO2_CONFIG, spo2_cfg)
        self._write_reg(REG_LED1_PA, max(0, min(0xFF, led1_pa)))
        self._write_reg(REG_LED2_PA, max(0, min(0xFF, led2_pa)))
        self._write_reg(REG_PILOT_PA, 0x7F)

    def set_led_amplitude(self, led: str, amplitude: int) -> None:
        amplitude = max(0, min(0xFF, amplitude))
        if led == "red":
            self._write_reg(REG_LED1_PA, amplitude)
        elif led == "ir":
            self._write_reg(REG_LED2_PA, amplitude)
        elif led == "pilot":
            self._write_reg(REG_PILOT_PA, amplitude)

    def get_data_present(self) -> int:
        try:
            read_ptr = self.bus.read_byte_data(self.address, REG_FIFO_RD_PTR)
            write_ptr = self.bus.read_byte_data(self.address, REG_FIFO_WR_PTR)
        except Exception as exc:
            self.logger.debug("Không thể đọc con trỏ FIFO: %s", exc)
            return 0

        diff = write_ptr - read_ptr
        if diff < 0:
            diff += 32
        return diff

    def read_fifo_sample(self) -> Optional[Tuple[int, int]]:
        try:
            self._clear_interrupts()
            data = self.bus.read_i2c_block_data(self.address, REG_FIFO_DATA, 6)
        except Exception as exc:  # pragma: no cover - hardware only
            self.logger.debug("Không thể đọc FIFO MAX30102: %s", exc)
            return None

        red = (data[0] << 16 | data[1] << 8 | data[2]) & 0x03FFFF
        ir = (data[3] << 16 | data[4] << 8 | data[5]) & 0x03FFFF
        
        # Validate: MAX30102 18-bit ADC, giá trị hợp lệ 0-262143
        # Nếu = 0x03FFFF (262143) → saturated, có thể corrupt
        if red == 0x03FFFF or ir == 0x03FFFF:
            return None  # Skip saturated samples
        
        return red, ir

    def read_samples(self, max_samples: int) -> List[Tuple[int, int]]:
        samples: List[Tuple[int, int]] = []
        if max_samples <= 0:
            return samples

        available = self.get_data_present()
        while available > 0 and len(samples) < max_samples:
            sample = self.read_fifo_sample()
            if sample is None:
                break
            samples.append(sample)
            available -= 1

        return samples

    def close(self) -> None:
        try:
            if hasattr(self.bus, "close"):
                self.bus.close()  # type: ignore[attr-defined]
        except Exception:
            pass


class MeasurementWindow:
    """Manage a rolling buffer of IR/RED samples with progress tracking."""

    def __init__(self, sample_rate: int, window_seconds: float, min_seconds: float) -> None:
        self.sample_rate = max(1, int(sample_rate))
        self.window_seconds = max(1.0, float(window_seconds))
        self.min_seconds = max(1.0, min(self.window_seconds, float(min_seconds)))

        self.max_samples = max(1, int(round(self.sample_rate * self.window_seconds)))
        self.min_samples = max(1, int(round(self.sample_rate * self.min_seconds)))

        self.ir: deque[int] = deque(maxlen=self.max_samples)
        self.red: deque[int] = deque(maxlen=self.max_samples)

    def reset(self) -> None:
        self.ir.clear()
        self.red.clear()

    def add_samples(self, ir_samples: Iterable[int], red_samples: Iterable[int]) -> None:
        for ir_val, red_val in zip(ir_samples, red_samples):
            self.ir.append(int(ir_val))
            self.red.append(int(red_val))

    def fill_ratio(self) -> float:
        if not self.max_samples:
            return 0.0
        return min(1.0, len(self.ir) / float(self.max_samples))

    def has_enough_data(self) -> bool:
        return len(self.ir) >= self.min_samples

    def duration_seconds(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return len(self.ir) / float(self.sample_rate)

    def recent_array(self, seconds: float, channel: str = "ir") -> np.ndarray:
        buffer = self.ir if channel == "ir" else self.red
        sample_count = max(1, int(round(self.sample_rate * max(0.1, seconds))))
        if not buffer:
            return np.empty(0)
        data = list(buffer)[-sample_count:]
        return np.array(data, dtype=np.float64)

    def estimate_quality(self, channel: str = "ir") -> float:
        """Ước lượng chất lượng tín hiệu dựa trên biên độ AC (peak-to-peak)."""
        buffer = self.ir if channel == "ir" else self.red
        if len(buffer) < 10:
            return 0.0
        
        arr = np.array(buffer, dtype=np.float64)
        # Dùng percentile thay vì std để tránh ảnh hưởng của outliers
        p95 = float(np.percentile(arr, 95))
        p5 = float(np.percentile(arr, 5))
        amplitude = max(0.0, p95 - p5)
        
        # Chất lượng dựa trên biên độ tuyệt đối (không phụ thuộc DC)
        if amplitude >= 800:
            quality = 100.0
        elif amplitude >= 500:
            quality = 85.0
        elif amplitude >= 300:
            quality = 65.0
        elif amplitude >= 150:
            quality = 45.0
        elif amplitude >= 80:
            quality = 25.0
        else:
            quality = max(0.0, amplitude / 4.0)  # Scale 0-20% cho tín hiệu yếu
        
        # Penalty nhẹ nếu buffer chưa đầy (chỉ giảm tối đa 30%)
        fill_ratio = len(buffer) / float(self.max_samples)
        if fill_ratio < 0.5:
            quality *= max(0.7, fill_ratio * 2.0)
        
        return quality

    def resample(self, target_rate: int, sample_count: int) -> Tuple[np.ndarray, np.ndarray]:
        if target_rate <= 0 or sample_count <= 0 or not self.ir:
            return np.empty(0), np.empty(0)

        ir_arr = np.array(self.ir, dtype=np.float64)
        red_arr = np.array(self.red, dtype=np.float64)

        if self.sample_rate <= target_rate:
            if ir_arr.size > sample_count:
                ir_arr = ir_arr[-sample_count:]
                red_arr = red_arr[-sample_count:]
            return ir_arr, red_arr

        stride = max(1, int(round(self.sample_rate / float(target_rate))))
        ir_ds = ir_arr[::stride]
        red_ds = red_arr[::stride]

        if ir_ds.size > sample_count:
            ir_ds = ir_ds[-sample_count:]
            red_ds = red_ds[-sample_count:]

        return ir_ds, red_ds


class HRCalculator:
    """Heart rate and SpO₂ estimation routines derived from hrcalc.py."""

    BUFFER_SIZE = 100
    MA_SIZE = 4
    MAX_NUM_PEAKS = 15

    @classmethod
    def calc_hr_and_spo2(
        cls,
        ir_data: np.ndarray,
        red_data: np.ndarray,
        sample_rate: int,
    ) -> Tuple[float, bool, float, bool]:
        if ir_data.size < cls.BUFFER_SIZE or red_data.size < cls.BUFFER_SIZE:
            return -999.0, False, -999.0, False

        # FIX: Clip data vào range hợp lý trước khi xử lý
        # MAX30102 ADC 18-bit: 0-262143, nhưng thường < 200000
        ir = np.array(ir_data[-cls.BUFFER_SIZE:], dtype=np.float64)
        red = np.array(red_data[-cls.BUFFER_SIZE:], dtype=np.float64)
        
        # Filter out saturated/invalid values (> 250000 hoặc < 0)
        ir = np.clip(ir, 0, 250000)
        red = np.clip(red, 0, 250000)
        
        # Convert to int32 AFTER clipping
        ir = ir.astype(np.int32)
        red = red.astype(np.int32)

        ir_mean = int(np.mean(ir))
        x = -1 * (ir - ir_mean)
        x = x.astype(np.int32)

        for i in range(x.shape[0] - cls.MA_SIZE):
            x[i] = int(np.sum(x[i : i + cls.MA_SIZE]) / cls.MA_SIZE)

        n_th = int(np.mean(x))
        n_th = max(30, min(60, n_th))
        min_dist = max(4, int(sample_rate * 0.25))
        ir_valley_locs, n_peaks = cls.find_peaks(x, x.shape[0], n_th, min_dist, cls.MAX_NUM_PEAKS)
        
        # DEBUG: Log để kiểm tra peak detection
        import logging
        logger = logging.getLogger(__name__)
        if n_peaks == 0:
            logger.debug("[HRCalc] Không tìm thấy peaks (n_th=%d, min_dist=%d, x_mean=%.1f)", 
                         n_th, min_dist, np.mean(x))

        hr = -999.0
        hr_valid = False

        if n_peaks >= 2:
            peak_interval_sum = 0
            for i in range(1, n_peaks):
                peak_interval_sum += ir_valley_locs[i] - ir_valley_locs[i - 1]
            peak_interval_sum = int(peak_interval_sum / (n_peaks - 1))
            if peak_interval_sum > 0:
                hr = float(sample_rate * 60 / peak_interval_sum)
                hr_valid = True

        spo2 = -999.0
        spo2_valid = False

        exact_ir_valley_locs_count = n_peaks
        if exact_ir_valley_locs_count == 0:
            return hr, hr_valid, spo2, spo2_valid

        ratio: List[int] = []
        i_ratio_count = 0

        for k in range(exact_ir_valley_locs_count - 1):
            red_dc_max = -1
            ir_dc_max = -1
            red_dc_max_index = -1
            ir_dc_max_index = -1
            if ir_valley_locs[k + 1] - ir_valley_locs[k] > 3:
                for i in range(ir_valley_locs[k], ir_valley_locs[k + 1]):
                    if ir[i] > ir_dc_max:
                        ir_dc_max = ir[i]
                        ir_dc_max_index = i
                    if red[i] > red_dc_max:
                        red_dc_max = red[i]
                        red_dc_max_index = i

                red_ac = int((red[ir_valley_locs[k + 1]] - red[ir_valley_locs[k]]) * (red_dc_max_index - ir_valley_locs[k]))
                red_ac = red[ir_valley_locs[k]] + int(red_ac / (ir_valley_locs[k + 1] - ir_valley_locs[k]))
                red_ac = red[red_dc_max_index] - red_ac

                ir_ac = int((ir[ir_valley_locs[k + 1]] - ir[ir_valley_locs[k]]) * (ir_dc_max_index - ir_valley_locs[k]))
                ir_ac = ir[ir_valley_locs[k]] + int(ir_ac / (ir_valley_locs[k + 1] - ir_valley_locs[k]))
                ir_ac = ir[ir_dc_max_index] - ir_ac

                nume = red_ac * ir_dc_max
                denom = ir_ac * red_dc_max
                if denom > 0 and nume != 0 and i_ratio_count < 5:
                    # FIX: Dùng float để tránh overflow, sau đó clip vào range hợp lý
                    ratio_value = (float(nume) * 100.0) / float(denom)
                    # SpO2 ratio thường trong khoảng 0.4-2.0 (40-200%)
                    # Nếu vượt quá → dữ liệu corrupt, bỏ qua
                    if 10.0 <= ratio_value <= 500.0:
                        ratio.append(int(ratio_value))
                        i_ratio_count += 1
                    # else: Skip invalid ratio

        if not ratio:
            return hr, hr_valid, spo2, spo2_valid

        ratio.sort()
        mid_index = len(ratio) // 2
        if len(ratio) % 2 == 0 and len(ratio) > 1:
            ratio_ave = (ratio[mid_index - 1] + ratio[mid_index]) / 2
        else:
            ratio_ave = ratio[mid_index]

        if 2 < ratio_ave < 184:
            spo2 = -45.060 * (ratio_ave ** 2) / 10000.0 + 30.054 * ratio_ave / 100.0 + 94.845
            spo2_valid = True

        return hr, hr_valid, spo2, spo2_valid

    @staticmethod
    def find_peaks(
        x: np.ndarray,
        size: int,
        min_height: int,
        min_dist: int,
        max_num: int,
    ) -> Tuple[List[int], int]:
        ir_valley_locs, n_peaks = HRCalculator.find_peaks_above_min_height(x, size, min_height, max_num)
        ir_valley_locs, n_peaks = HRCalculator.remove_close_peaks(n_peaks, ir_valley_locs, x, min_dist)
        n_peaks = min(n_peaks, max_num)
        return ir_valley_locs, n_peaks

    @staticmethod
    def find_peaks_above_min_height(
        x: np.ndarray,
        size: int,
        min_height: int,
        max_num: int,
    ) -> Tuple[List[int], int]:
        i = 0
        n_peaks = 0
        ir_valley_locs: List[int] = []
        while i < size - 1:
            if x[i] > min_height and x[i] > x[i - 1]:
                n_width = 1
                while i + n_width < size - 1 and x[i] == x[i + n_width]:
                    n_width += 1
                if x[i] > x[i + n_width] and n_peaks < max_num:
                    ir_valley_locs.append(i)
                    n_peaks += 1
                    i += n_width + 1
                else:
                    i += n_width
            else:
                i += 1
        return ir_valley_locs, n_peaks

    @staticmethod
    def remove_close_peaks(
        n_peaks: int,
        ir_valley_locs: List[int],
        x: np.ndarray,
        min_dist: int,
    ) -> Tuple[List[int], int]:
        sorted_indices = sorted(ir_valley_locs, key=lambda idx: x[idx], reverse=True)
        i = -1
        while i < n_peaks:
            old_n_peaks = n_peaks
            n_peaks = i + 1
            j = i + 1
            while j < old_n_peaks:
                dist = (
                    sorted_indices[j] - sorted_indices[i]
                    if i != -1
                    else (sorted_indices[j] + 1)
                )
                if dist > min_dist or dist < -min_dist:
                    if n_peaks < len(sorted_indices):
                        sorted_indices[n_peaks] = sorted_indices[j]
                    else:
                        sorted_indices.append(sorted_indices[j])
                    n_peaks += 1
                j += 1
            i += 1

        sorted_indices[:n_peaks] = sorted(sorted_indices[:n_peaks])
        return sorted_indices[:n_peaks], n_peaks


class MAX30102Sensor(BaseSensor):
    """High-level MAX30102 sensor wrapper with fixed measurement window."""

    DEFAULT_MEASUREMENT_WINDOW = 8.0  # seconds
    MIN_MEASUREMENT_SECONDS = 2.5  # Giảm từ 4.0 xuống 2.5s để nhanh hơn

    def __init__(self, config: Dict[str, Any]):
        super().__init__("MAX30102", config)

        self.i2c_bus = int(config.get("i2c_bus", 1))
        self.i2c_address = int(config.get("i2c_address", 0x57))
        self.sample_average = int(config.get("sample_average", 4))
        
        # Hardware sample rate (MAX30102 internal) vs polling rate (BaseSensor)
        self.hardware_sample_rate = int(config.get("hardware_sample_rate", 50))
        
        self.pulse_amplitude_red = int(config.get("pulse_amplitude_red", 0x24))
        self.pulse_amplitude_ir = int(config.get("pulse_amplitude_ir", 0x24))
        self.adc_range = int(config.get("adc_range", 4096))
        self.led_mode = int(config.get("led_mode", 0x03))
        self.ir_threshold = int(config.get("ir_threshold", 50000))

        measurement_window = float(config.get("measurement_window_seconds", self.DEFAULT_MEASUREMENT_WINDOW))
        measurement_window = max(self.DEFAULT_MEASUREMENT_WINDOW, measurement_window)
        min_window = float(config.get("min_measurement_seconds", measurement_window * 0.5))
        min_window = max(self.MIN_MEASUREMENT_SECONDS, min_window)
        min_window = min(min_window, measurement_window)

        self.measurement_window_seconds = measurement_window
        self.min_measurement_seconds = min_window

        self.validity_timeout = float(config.get("validity_timeout", 3.0))
        self.hr_algorithm_rate = 25
        default_samples = self.hardware_sample_rate // 4 or 4
        self.max_samples_per_read = max(1, int(config.get("max_samples_per_read", default_samples)))

        self.hardware: Optional[MAX30102Hardware] = None
        self.window = MeasurementWindow(self.hardware_sample_rate, self.measurement_window_seconds, self.min_measurement_seconds)

        # State objects (refactored)
        self.measurement = MeasurementState()
        self.session = SessionState()
        self.finger = FingerDetectionState()
        
        # History buffers for median filtering
        self.hr_history: deque[float] = deque(maxlen=5)
        self.spo2_history: deque[float] = deque(maxlen=5)
        self.last_valid_hr_ts = 0.0
        self.last_valid_spo2_ts = 0.0
        
        # Configuration for finger detection hysteresis
        self._finger_confirm_frames = max(2, int(config.get("finger_confirm_frames", 2)))  # Giảm xuống 2 để nhanh hơn
        self._finger_release_frames = max(3, int(config.get("finger_release_frames", 4)))  # Giảm xuống 4

    def initialize(self) -> bool:
        if self.hardware:
            try:
                self.hardware.setup(
                    sample_rate=self.hardware_sample_rate,
                    led_mode=self.led_mode,
                    led1_pa=self.pulse_amplitude_red,
                    led2_pa=self.pulse_amplitude_ir,
                    sample_average=self.sample_average,
                    adc_range=self.adc_range,
                )
                self.hardware_sample_rate = self.hardware.sample_rate
                self.window = MeasurementWindow(
                    self.hardware_sample_rate,
                    self.measurement_window_seconds,
                    self.min_measurement_seconds,
                )
                self.logger.debug("MAX30102 đã được đánh thức và cấu hình lại sau khi khởi động lại")
                return True
            except Exception as exc:  # pragma: no cover - hardware only
                self.logger.error("Không thể cấu hình lại MAX30102: %s", exc)
                return False

        if smbus is None:
            self.logger.error("Không thể khởi tạo MAX30102 do thiếu smbus")
            return False

        try:
            self.hardware = MAX30102Hardware(channel=self.i2c_bus, address=self.i2c_address, logger=self.logger)
            self.hardware.setup(
                sample_rate=self.hardware_sample_rate,
                led_mode=self.led_mode,
                led1_pa=self.pulse_amplitude_red,
                led2_pa=self.pulse_amplitude_ir,
                sample_average=self.sample_average,
                adc_range=self.adc_range,
            )
            # Tính effective sample rate SAU khi hardware.setup() (có thể bị điều chỉnh)
            self.hardware_sample_rate = self.hardware.sample_rate
            effective_sample_rate = self.hardware_sample_rate / max(1, self.sample_average)
            
            self.window = MeasurementWindow(
                int(effective_sample_rate),  # Dùng effective rate, không phải nominal
                self.measurement_window_seconds,
                self.min_measurement_seconds,
            )
            self.logger.info(
                "MAX30102 khởi tạo (bus=%d, addr=0x%02X, HW_rate=%d SPS, avg=%d, effective=%.1f SPS, poll=%.1f Hz, max_read=%d)",
                self.i2c_bus,
                self.i2c_address,
                self.hardware_sample_rate,
                self.sample_average,
                effective_sample_rate,
                self.sample_rate,
                self.max_samples_per_read,
            )
            return True
        except Exception as exc:  # pragma: no cover - hardware only
            self.logger.error("Không thể khởi tạo MAX30102: %s", exc)
            self.hardware = None
            return False

    def read_raw_data(self) -> Optional[Dict[str, Any]]:
        if not self.hardware:
            return {"read_size": 0}

        try:
            samples = self.hardware.read_samples(self.max_samples_per_read)
            if not samples:
                return {"read_size": 0}

            red_samples = [sample[0] for sample in samples]
            ir_samples = [sample[1] for sample in samples]

            return {
                "read_size": len(samples),
                "red": red_samples,
                "ir": ir_samples,
            }
        except Exception as exc:  # pragma: no cover - hardware only
            self.logger.error("Lỗi đọc dữ liệu MAX30102: %s", exc)
            return None

    def process_data(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if raw_data is None:
            return None

        red_samples = raw_data.get("red", []) or []
        ir_samples = raw_data.get("ir", []) or []
        sample_count = int(raw_data.get("read_size", min(len(red_samples), len(ir_samples))))

        if sample_count <= 0:
            self._update_status_no_samples()
            return self._build_payload(0)

        # Log để kiểm tra data flow
        if sample_count > 0:
            self.logger.debug("[Data Flow] Đọc được %d samples, window fill=%.1f%%", 
                              sample_count, self.window.fill_ratio() * 100)
        
        self.window.add_samples(ir_samples, red_samples)
        self.measurement.readings_count += sample_count
        self.measurement.window_fill = self.window.fill_ratio()
        self.measurement.signal_quality_ir = self.window.estimate_quality("ir")
        self.measurement.signal_quality_red = self.window.estimate_quality("red")
        self.finger.detected = self._detect_finger()
        self.session.elapsed = self._session_elapsed()

        hr_value, hr_valid, spo2_value, spo2_valid = self._compute_biometrics()

        if hr_valid and self.validate_heart_rate(hr_value):
            self.hr_history.append(float(hr_value))
            self.measurement.heart_rate = float(np.median(self.hr_history))
            self.measurement.hr_valid = True
            self.last_valid_hr_ts = time.time()
            self.logger.debug("[HR accepted] %.1f BPM → median=%.1f (history=%d)", 
                              hr_value, self.measurement.heart_rate, len(self.hr_history))
        else:
            self.measurement.hr_valid = False
            if hr_valid:
                self.logger.warning("[HR rejected] %.1f BPM - ngoài khoảng 40-200", hr_value)

        if spo2_valid and self.validate_spo2(spo2_value):
            self.spo2_history.append(float(spo2_value))
            self.measurement.spo2 = float(np.median(self.spo2_history))
            self.measurement.spo2_valid = True
            self.last_valid_spo2_ts = time.time()
            self.logger.debug("[SpO2 accepted] %.1f%% → median=%.1f (history=%d)", 
                              spo2_value, self.measurement.spo2, len(self.spo2_history))
        else:
            self.measurement.spo2_valid = False
            if spo2_valid:
                self.logger.warning("[SpO2 rejected] %.1f%% - ngoài khoảng 70-100", spo2_value)

        self._expire_stale_values()

        self.measurement.status = self._determine_status()
        self.measurement.ready = (
            self.session.active
            and self.measurement.window_fill >= 0.85
            and self.measurement.signal_quality_ir >= 18.0
            and (self.measurement.hr_valid or self.measurement.spo2_valid)
        )

        return self._build_payload(sample_count)

    def begin_measurement_session(self) -> None:
        self.window.reset()
        self.hr_history.clear()
        self.spo2_history.clear()
        
        # Reset measurement state
        self.measurement.hr_valid = False
        self.measurement.spo2_valid = False
        self.measurement.ready = False
        self.measurement.status = "initializing"
        self.measurement.readings_count = 0
        
        # Reset session state
        self.session.active = True
        self.session.start_time = time.time()
        self.session.elapsed = 0.0
        
        # Reset finger detection state
        self.finger.reset()

    def end_measurement_session(self) -> None:
        self.session.active = False
        self.session.start_time = 0.0
        self.session.elapsed = 0.0
        self.measurement.ready = False

    def _compute_biometrics(self) -> Tuple[float, bool, float, bool]:
        """Tính toán HR và SpO₂ từ dữ liệu cửa sổ."""
        if not self.finger.detected:
            self.logger.debug("[Biometrics] Bỏ qua - không phát hiện ngón tay")
            return -999.0, False, -999.0, False
        
        if not self.window.has_enough_data():
            fill = self.window.fill_ratio() * 100
            current_samples = len(self.window.ir)
            self.logger.debug("[Biometrics] Bỏ qua - chưa đủ dữ liệu (fill=%.1f%%, samples=%d/%d)", 
                              fill, current_samples, self.window.min_samples)
            return -999.0, False, -999.0, False

        ir_ds, red_ds = self.window.resample(self.hr_algorithm_rate, HRCalculator.BUFFER_SIZE + 10)
        self.logger.debug("[Biometrics] Resample OK: IR=%d, RED=%d (raw_samples=%d)", 
                          ir_ds.size, red_ds.size, len(self.window.ir))
        
        if ir_ds.size < HRCalculator.BUFFER_SIZE or red_ds.size < HRCalculator.BUFFER_SIZE:
            self.logger.debug("[Biometrics] Resampled không đủ: IR=%d, RED=%d (cần %d)", 
                              ir_ds.size, red_ds.size, HRCalculator.BUFFER_SIZE)
            return -999.0, False, -999.0, False

        hr_value, hr_valid, spo2_value, spo2_valid = HRCalculator.calc_hr_and_spo2(
            ir_ds, red_ds, self.hr_algorithm_rate
        )
        
        self.logger.debug("[Biometrics] HR=%.1f (valid=%s), SpO2=%.1f (valid=%s)", 
                          hr_value, hr_valid, spo2_value, spo2_valid)

        return hr_value, hr_valid, spo2_value, spo2_valid

    def _detect_finger(self) -> bool:
        """Phát hiện ngón tay với scoring đơn giản và hysteresis."""
        recent_ir = self.window.recent_array(seconds=1.2, channel="ir")
        previous_state = bool(self.finger.detected)

        min_samples = max(8, int(self.window.sample_rate * 0.5))
        if recent_ir.size < min_samples:
            # Không đủ dữ liệu - khởi tạo baseline THẤP nếu có ít nhất 3 samples
            if recent_ir.size >= 3 and not self.finger.baseline_ready:
                # Dùng percentile 10% thay vì median để baseline thấp hơn
                self.finger.baseline = float(np.percentile(recent_ir, 10))
                self.finger.baseline_ready = True
                self.logger.debug("[Baseline khởi tạo] %.0f (từ %d samples)", self.finger.baseline, recent_ir.size)
            
            self.finger.present_frames = 0
            self.finger.absent_frames = min(
                self.finger.absent_frames + 1,
                self._finger_release_frames + 1,
            )
            
            if previous_state and self.finger.absent_frames >= self._finger_release_frames:
                self.finger.detected = False
            
            # Reset metrics
            self.finger.signal_ratio = 0.0
            self.finger.signal_amplitude = 0.0
            self.finger.signal_quality = float(self.measurement.signal_quality_ir)
            self.finger.detection_score = 0.0
            return bool(self.finger.detected)

        # Tính metrics cơ bản
        median_ir = float(np.median(recent_ir))
        p95 = float(np.percentile(recent_ir, 95))
        p5 = float(np.percentile(recent_ir, 5))
        amplitude = max(0.0, p95 - p5)
        quality = max(0.0, float(self.measurement.signal_quality_ir))
        
        # Cập nhật baseline CHỈ KHI KHÔNG có ngón tay (CRITICAL FIX)
        if not self.finger.baseline_ready:
            # Lần đầu: khởi tạo baseline ở percentile thấp để dc_increase > 0
            self.finger.baseline = float(np.percentile(recent_ir, 10))
            self.finger.baseline_ready = True
            self.logger.debug("[Baseline khởi tạo chính] %.0f (từ %d samples)", self.finger.baseline, recent_ir.size)
        elif not previous_state:
            # CHỈ cập nhật baseline khi KHÔNG có ngón tay
            # Dùng EMA chậm để tránh nhiễu
            alpha = 0.1
            self.finger.baseline = alpha * median_ir + (1 - alpha) * self.finger.baseline
            self.logger.debug("[Baseline EMA] median=%.0f → baseline=%.0f", median_ir, self.finger.baseline)
        # ELSE: Nếu đã có ngón tay → GIỮ NGUYÊN baseline, KHÔNG cập nhật!
        
        dc_increase = max(0.0, median_ir - self.finger.baseline)
        
        # Scoring đơn giản: 3 thành phần chính
        score = 0.0
        
        # 1. Amplitude score (40% trọng số)
        if amplitude >= 500:
            score += 0.40
        elif amplitude >= 250:
            score += 0.30
        elif amplitude >= 120:
            score += 0.20
        else:
            score += max(0.0, amplitude / 600.0)  # Scale 0-0.20
        
        # 2. Quality score (30% trọng số)
        score += 0.30 * min(1.0, quality / 100.0)
        
        # 3. DC increase score (30% trọng số)
        if dc_increase >= 8000:
            score += 0.30
        elif dc_increase >= 4000:
            score += 0.20
        elif dc_increase >= 2000:
            score += 0.15
        else:
            score += max(0.0, dc_increase / 26667.0)  # Scale 0-0.30
        
        # Threshold đơn giản
        DETECTION_THRESHOLD = 0.45
        finger_metric = score >= DETECTION_THRESHOLD
        
        # Hysteresis: đếm frame liên tục
        if finger_metric:
            self.finger.present_frames = min(
                self.finger.present_frames + 1,
                self._finger_confirm_frames,
            )
            self.finger.absent_frames = 0
            # DEBUG: Log hysteresis progress khi đang chờ confirm
            if not previous_state and self.finger.present_frames < self._finger_confirm_frames:
                self.logger.debug(
                    "[HYSTERESIS] Detecting... %d/%d frames (score=%.2f, amp=%.0f)",
                    self.finger.present_frames,
                    self._finger_confirm_frames,
                    score,
                    amplitude,
                )
        else:
            self.finger.absent_frames = min(
                self.finger.absent_frames + 1,
                self._finger_release_frames + 1,
            )
            self.finger.present_frames = 0
        
        # Quyết định cuối cùng
        finger_now = previous_state
        if not previous_state and self.finger.present_frames >= self._finger_confirm_frames:
            finger_now = True
        elif previous_state and self.finger.absent_frames >= self._finger_release_frames:
            finger_now = False
        
        # Lưu metrics để GUI hiển thị
        self.finger.signal_ratio = amplitude / max(1.0, median_ir)
        self.finger.signal_amplitude = amplitude
        self.finger.signal_quality = quality
        self.finger.detection_score = score
        
        # Log khi thay đổi trạng thái
        if finger_now != previous_state:
            state_label = "detected" if finger_now else "removed"
            self.logger.info(
                "Finger %s (score=%.2f, amplitude=%.0f, quality=%.0f%%, dc_increase=%.0f)",
                state_label,
                score,
                amplitude,
                quality,
                dc_increase,
            )
        
        self.finger.detected = finger_now
        return finger_now

    def _determine_status(self) -> str:
        if not self.finger.detected:
            return "no_finger"
        if not self.window.has_enough_data():
            return "initializing"
        if self.measurement.signal_quality_ir < 15.0:
            return "poor_signal"
        if self.measurement.window_fill < 0.9:
            return "partial"
        return "good"

    def _session_elapsed(self) -> float:
        if not self.session.active:
            return 0.0
        return max(0.0, time.time() - self.session.start_time)

    def _expire_stale_values(self) -> None:
        now = time.time()
        if self.measurement.hr_valid and (now - self.last_valid_hr_ts) > self.validity_timeout:
            self.measurement.hr_valid = False
        if self.measurement.spo2_valid and (now - self.last_valid_spo2_ts) > self.validity_timeout:
            self.measurement.spo2_valid = False

    def _build_payload(self, read_size: int) -> Dict[str, Any]:
        return {
            "read_size": read_size,
            "heart_rate": float(self.measurement.heart_rate),
            "spo2": float(self.measurement.spo2),
            "hr_valid": bool(self.measurement.hr_valid),
            "spo2_valid": bool(self.measurement.spo2_valid),
            "finger_detected": bool(self.finger.detected),
            "signal_quality_ir": float(self.measurement.signal_quality_ir),
            "signal_quality_red": float(self.measurement.signal_quality_red),
            "status": self.measurement.status,
            "window_fill": float(self.measurement.window_fill),
            "measurement_ready": bool(self.measurement.ready),
            "measurement_elapsed": float(self.session.elapsed),
            "session_active": bool(self.session.active),
            "finger_detection_score": float(self.finger.detection_score),
            "finger_signal_amplitude": float(self.finger.signal_amplitude),
            "finger_signal_ratio": float(self.finger.signal_ratio),
            "finger_signal_quality": float(self.finger.signal_quality),
        }

    def _update_status_no_samples(self) -> None:
        if not self.finger.detected:
            self.measurement.status = "no_finger"
        elif not self.window.has_enough_data():
            self.measurement.status = "initializing"

    def get_heart_rate_status(self) -> str:
        if not self.finger.detected:
            return "no_finger"
        if not self.measurement.hr_valid:
            if self.measurement.signal_quality_ir < 15.0:
                return "poor_signal"
            if not self.window.has_enough_data():
                return "initializing"
            return "estimating"
        return "good"

    def get_spo2_status(self) -> str:
        if not self.finger.detected:
            return "no_finger"
        if not self.measurement.spo2_valid:
            if self.measurement.signal_quality_ir < 15.0:
                return "poor_signal"
            if not self.window.has_enough_data():
                return "initializing"
            return "estimating"
        return "good"

    def reset_buffers(self) -> None:
        self.window.reset()
        self.hr_history.clear()
        self.spo2_history.clear()
        
        # Reset measurement state
        self.measurement.heart_rate = 0.0
        self.measurement.spo2 = 0.0
        self.measurement.hr_valid = False
        self.measurement.spo2_valid = False
        self.measurement.status = "idle"
        self.measurement.ready = False
        
        # Reset finger detection state
        self.finger.reset()

    def set_led_amplitude(self, red_amplitude: int, ir_amplitude: int) -> bool:
        if not self.hardware:
            return False
        try:
            self.hardware.set_led_amplitude("red", red_amplitude)
            self.hardware.set_led_amplitude("ir", ir_amplitude)
            return True
        except Exception as exc:  # pragma: no cover - hardware only
            self.logger.error("Không thể đặt biên độ LED: %s", exc)
            return False

    def turn_on_red_led(self) -> bool:
        return self.set_led_amplitude(self.pulse_amplitude_red, self.pulse_amplitude_ir)

    def turn_off_red_led(self) -> bool:
        return self.set_led_amplitude(0, self.pulse_amplitude_ir)

    def validate_heart_rate(self, hr: float) -> bool:
        return 40.0 <= hr <= 200.0

    def validate_spo2(self, spo2: float) -> bool:
        return 70.0 <= spo2 <= 100.0

    def stop(self) -> bool:
        result = super().stop()
        self.end_measurement_session()
        if self.hardware:
            try:
                self.hardware.shutdown()
            except Exception:  # pragma: no cover - defensive
                pass
        return result

