"""Màn hình đo nhịp tim & SpO2 với controller điều phối rõ ràng."""

from __future__ import annotations

from typing import Any, Dict, Optional

import logging
import time
import numpy as np

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDFillRoundFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.progressbar import MDProgressBar

# Import ScenarioID cho TTS
from src.utils.tts_manager import ScenarioID


# ============================================================
# THEME COLORS - Màu sắc giao diện y tế
# ============================================================
MED_BG_COLOR = (0.02, 0.18, 0.27, 1)       # Nền chính (xanh đậm)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)     # Nền card
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)     # Màu nhấn (xanh lục)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)        # Màu chính (xanh dương)
MED_WARNING = (0.96, 0.4, 0.3, 1)          # Cảnh báo (đỏ cam)
TEXT_PRIMARY = (1, 1, 1, 1)                # Chữ chính (trắng)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)         # Chữ phụ (xám nhạt)

# ============================================================
# HEALTH STATUS COLORS - Màu theo ngưỡng sức khỏe (cho người già)
# ============================================================
COLOR_HEALTHY = (0.3, 0.85, 0.4, 1)        # Xanh lá - Tốt
COLOR_CAUTION = (1.0, 0.8, 0.2, 1)         # Vàng - Cần chú ý
COLOR_DANGER = (1.0, 0.3, 0.3, 1)          # Đỏ - Nguy hiểm
COLOR_NORMAL = (0.4, 0.75, 0.95, 1)        # Xanh dương nhạt - Bình thường

# ============================================================
# BUTTON COLORS - Màu nút bấm nổi bật
# ============================================================
BTN_START_COLOR = (0.1, 0.5, 0.7, 1)       # Xanh đậm - Bắt đầu
BTN_STOP_COLOR = (0.9, 0.35, 0.25, 1)      # Đỏ - Dừng
BTN_SAVE_COLOR = (0.2, 0.7, 0.4, 1)        # Xanh lá - Lưu
BTN_DISABLED_COLOR = (0.4, 0.4, 0.4, 1)    # Xám - Vô hiệu


class WaveformWidget(Widget):
    """
    Widget hiển thị biểu đồ sóng PPG hiệu năng cao.
    
    Tối ưu:
    - Dùng Line instruction cố định, không redraw toàn bộ canvas
    - Auto-scale để sóng luôn nằm giữa màn hình
    - Nhận batch data để giảm số lần cập nhật
    - Downsample để sóng rõ ràng, không quá dày đặc
    """
    
    # Buffer lưu raw data (~6 giây @ 100 SPS)
    RAW_BUFFER_SIZE = 600
    # Số điểm thực sự vẽ trên màn hình (sau khi downsample)
    DISPLAY_POINTS = 120
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_points = []  # Raw buffer
        
        # ============================================================
        # 1. VẼ NỀN VÀ LƯỚI (Tĩnh - chỉ vẽ 1 lần)
        # ============================================================
        with self.canvas.before:
            Color(0.05, 0.15, 0.22, 1)  # Nền tối
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            
            Color(0.3, 0.4, 0.5, 0.2)  # Lưới mờ
            self.grid_lines = []
            for _ in range(15):  # Tạo sẵn pool các đường lưới
                self.grid_lines.append(Line(points=[], width=0.5))
        
        # ============================================================
        # 2. VẼ ĐƯỜNG SÓNG (Động - chỉ cập nhật points)
        # ============================================================
        with self.canvas:
            self.line_color_instruction = Color(*COLOR_HEALTHY)
            self.signal_line = Line(points=[], width=2.0)  # Đường dày hơn để dễ nhìn
        
        # Bind resize để cập nhật layout
        self.bind(size=self._update_layout, pos=self._update_layout)
    
    def _update_layout(self, *args):
        """Cập nhật vị trí nền và lưới khi resize (chỉ khi cần)."""
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        
        # Vẽ lại lưới
        rows, cols = 4, 10
        grid_idx = 0
        
        # Đường dọc
        step_x = self.width / cols if cols > 0 else self.width
        for i in range(1, cols):
            if grid_idx < len(self.grid_lines):
                x = self.x + i * step_x
                self.grid_lines[grid_idx].points = [x, self.y, x, self.y + self.height]
                grid_idx += 1
        
        # Đường ngang
        step_y = self.height / rows if rows > 0 else self.height
        for i in range(1, rows):
            if grid_idx < len(self.grid_lines):
                y = self.y + i * step_y
                self.grid_lines[grid_idx].points = [self.x, y, self.x + self.width, y]
                grid_idx += 1
        
        # Cập nhật lại signal line với data hiện tại
        self._update_signal_line()
    
    def set_color(self, color: tuple) -> None:
        """Đặt màu đường sóng (không cần redraw toàn bộ)."""
        self.line_color_instruction.rgba = color
    
    def clear(self) -> None:
        """Xóa tất cả dữ liệu."""
        self.data_points = []
        self.signal_line.points = []
    
    def add_point(self, value: float) -> None:
        """
        Thêm một điểm dữ liệu (backward compatibility).
        Khuyến khích dùng update_data() với batch để hiệu năng tốt hơn.
        """
        self.update_data([value])
    
    def update_data(self, new_values: list) -> None:
        """
        Nhận một MẢNG dữ liệu (batch) và vẽ lại.
        Hiệu năng cao hơn nhiều so với add từng điểm.
        
        Args:
            new_values: List các giá trị raw IR signal từ sensor
        """
        if not new_values:
            return
        
        # Thêm dữ liệu mới vào buffer
        self.data_points.extend(new_values)
        
        # Giới hạn buffer size
        if len(self.data_points) > self.RAW_BUFFER_SIZE:
            self.data_points = self.data_points[-self.RAW_BUFFER_SIZE:]
        
        # Cập nhật đường sóng
        self._update_signal_line()
    
    def _downsample(self, data: list, target_points: int) -> list:
        """
        Giảm số điểm dữ liệu để vẽ rõ ràng hơn.
        Dùng phương pháp lấy trung bình mỗi nhóm.
        
        Args:
            data: Dữ liệu gốc
            target_points: Số điểm muốn có sau khi downsample
            
        Returns:
            List đã được downsample
        """
        n = len(data)
        if n <= target_points:
            return data
        
        # Tính số samples cần gộp thành 1 điểm
        step = n / target_points
        result = []
        
        for i in range(target_points):
            start = int(i * step)
            end = int((i + 1) * step)
            # Lấy trung bình của nhóm (giữ được hình dạng sóng)
            chunk = data[start:end]
            if chunk:
                result.append(sum(chunk) / len(chunk))
        
        return result
    
    def _update_signal_line(self) -> None:
        """
        Cập nhật toạ độ điểm của đường sóng (KHÔNG clear canvas).
        Đây là phần tối ưu quan trọng nhất.
        """
        if len(self.data_points) < 2:
            self.signal_line.points = []
            return
        
        # ============================================================
        # DOWNSAMPLE - Giảm số điểm để sóng rõ ràng hơn
        # ============================================================
        display_data = self._downsample(self.data_points, self.DISPLAY_POINTS)
        
        if len(display_data) < 2:
            self.signal_line.points = []
            return
        
        # ============================================================
        # AUTO SCALE LOGIC - Sóng luôn full màn hình
        # ============================================================
        min_val = min(display_data)
        max_val = max(display_data)
        rng = max_val - min_val
        
        # Tránh phóng đại nhiễu (nếu tín hiệu quá nhỏ < 500, coi như đường thẳng)
        if rng < 500:
            rng = 500
            mid = (min_val + max_val) / 2
            min_val = mid - 250
        
        # ============================================================
        # TÍNH TOẠ ĐỘ MÀN HÌNH
        # ============================================================
        pts = []
        n_points = len(display_data)
        step_x = self.width / (n_points - 1) if n_points > 1 else self.width
        margin_y = self.height * 0.08  # 8% margin trên/dưới
        drawable_height = self.height * 0.84
        
        for i, val in enumerate(display_data):
            x = self.x + i * step_x
            # Normalize 0-1
            norm = (val - min_val) / rng if rng > 0 else 0.5
            # Scale vào chiều cao (với margin)
            y = self.y + margin_y + (norm * drawable_height)
            pts.extend([x, y])
        
        # Cập nhật đường vẽ (chỉ thay đổi points, không tạo mới Line)
        self.signal_line.points = pts


class PulseAnimation(MDBoxLayout):
    """Widget hoạt họa nhịp tim đơn giản."""

    # ------------------------------------------------------------------
    # Initialization & Animation Control
    # ------------------------------------------------------------------

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = (0, dp(4), 0, dp(4))
        self.pulse_active = False
        self.pulse_rate = 60.0
        self.base_font_size = dp(36)  # Giảm nhẹ để nhường chỗ cho waveform

        self.heart_icon = MDIcon(
            icon="heart",
            theme_text_color="Custom",
            text_color=(1, 0.35, 0.46, 1),
            halign="center",
        )
        self.heart_icon.font_size = self.base_font_size
        self.heart_icon.pos_hint = {"center_x": 0.5}
        self.add_widget(self.heart_icon)

    def start_pulse(self, bpm: float) -> None:
        if bpm <= 0:
            self.stop_pulse()
            return

        self.pulse_rate = bpm
        self.pulse_active = True
        Clock.unschedule(self._pulse_beat)
        interval = max(0.3, 60.0 / bpm)
        self._schedule(interval)

    def stop_pulse(self) -> None:
        self.pulse_active = False
        Clock.unschedule(self._pulse_beat)
        self.heart_icon.font_size = self.base_font_size

    def _schedule(self, interval: float) -> None:
        if self.pulse_active:
            Clock.schedule_once(self._pulse_beat, interval)

    def _pulse_beat(self, _dt: float) -> None:
        if not self.pulse_active:
            return

        anim = (
            Animation(font_size=self.base_font_size + dp(6), duration=0.12)
            + Animation(font_size=self.base_font_size, duration=0.12)
        )
        anim.start(self.heart_icon)

        interval = max(0.3, 60.0 / self.pulse_rate) if self.pulse_rate > 0 else 1.0
        self._schedule(interval)


class HeartRateMeasurementController:
    """State machine điều khiển quá trình đo MAX30102."""

    STATE_IDLE = "idle"
    STATE_WAITING = "waiting"
    STATE_MEASURING = "measuring"
    STATE_FINISHED = "finished"

    # Theo tiêu chuẩn y tế quốc tế (FDA, WHO):
    # - Thời gian đo tối thiểu: 10-15s
    # - Thời gian đo tối ưu: 15-30s
    # Dự án chọn 15s để cân bằng tốc độ và độ chính xác
    MEASUREMENT_DURATION = 15.0  # Thời gian đo chuẩn (giây)
    MINIMUM_MEASUREMENT_TIME = 12.0  # Thời gian tối thiểu để chấp nhận kết quả (80% của 15s)
    FINGER_LOSS_GRACE = 3.0  # Grace period khi mất ngón tay trong lúc đo
    TIMEOUT_MARGIN = 20.0  # Thời gian timeout tổng (15s đo + 5s buffer)

    # ------------------------------------------------------------------
    # Initialization & State Management
    # ------------------------------------------------------------------

    def __init__(self, screen: "HeartRateScreen", sensor_name: str = "MAX30102") -> None:
        self.screen = screen
        self.app = screen.app_instance
        self.sensor_name = sensor_name
        self.logger = logging.getLogger(__name__ + ".controller")

        self.state = self.STATE_IDLE
        self.poll_event = None
        self.wait_started = 0.0
        self.measure_started = 0.0
        self.deadline = 0.0
        self.finger_lost_ts: Optional[float] = None
        self.last_snapshot: Dict[str, Any] = {}
        
        # Best results tracking - flag để biết có valid results trong history
        self.best_hr_valid: bool = False
        self.best_spo2_valid: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.state in (self.STATE_WAITING, self.STATE_MEASURING):
            self.logger.debug("Phiên đo đang chạy - bỏ qua yêu cầu start")
            return

        if not self._ensure_sensor_started():
            self.screen.show_error_status("Không thể khởi động cảm biến. Kiểm tra kết nối.")
            return

        sensor = self._get_sensor()
        if sensor and hasattr(sensor, "begin_measurement_session"):
            try:
                sensor.begin_measurement_session()
            except Exception as exc:  # pragma: no cover - safety log
                self.logger.error("Không thể begin_measurement_session: %s", exc)

        now = time.time()
        self.state = self.STATE_WAITING
        self.wait_started = now
        self.measure_started = 0.0
        self.deadline = now + self.MEASUREMENT_DURATION + self.TIMEOUT_MARGIN
        self.finger_lost_ts = None
        self.last_snapshot = {}
        
        # Reset best results tracking
        self.best_hr = 0.0
        self.best_hr_valid = False
        self.best_spo2 = 0.0
        self.best_spo2_valid = False
        self.best_quality = 0.0

        self.screen.on_measurement_preparing()
        self._schedule_poll()
        self.logger.info("Chờ ngón tay đặt lên cảm biến (không giới hạn thời gian)")

    def stop(self, user_cancelled: bool = True) -> None:
        if self.state not in (self.STATE_WAITING, self.STATE_MEASURING):
            self.reset()
            self.screen.reset_to_idle()
            return

        snapshot = self.app.get_sensor_data() or {}
        self._finalize(success=False, reason="user_cancel" if user_cancelled else "stopped", snapshot=snapshot)

    def reset(self) -> None:
        self._cancel_poll()
        self.state = self.STATE_IDLE
        self.wait_started = 0.0
        self.measure_started = 0.0
        self.deadline = 0.0
        self.finger_lost_ts = None
        self.last_snapshot = {}
        # Reset best results flags
        self.best_hr_valid = False
        self.best_spo2_valid = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_sensor_started(self) -> bool:
        try:
            return bool(self.app.ensure_sensor_started(self.sensor_name))
        except Exception as exc:  # pragma: no cover - safety log
            self.logger.error("Không thể khởi động %s: %s", self.sensor_name, exc)
            return False

    def _get_sensor(self):
        sensors = getattr(self.app, "sensors", {})
        if isinstance(sensors, dict):
            return sensors.get(self.sensor_name)
        return None

    def _schedule_poll(self) -> None:
        if self.poll_event is None:
            # Tăng tốc độ cập nhật lên 0.05s (20Hz) để sóng mượt
            self.poll_event = Clock.schedule_interval(self._poll_sensor, 0.05)

    def _cancel_poll(self) -> None:
        if self.poll_event is not None:
            try:
                self.poll_event.cancel()
            except Exception:
                Clock.unschedule(self._poll_sensor)
        self.poll_event = None

    def _poll_sensor(self, _dt: float) -> bool:
        sensor_data = self.app.get_sensor_data() or {}
        status = self._extract_status(sensor_data)
        self.last_snapshot = {"sensor_status": {self.sensor_name: status}, **sensor_data}
        
        # ============================================================
        # LẤY RAW SAMPLES TỪ SENSOR BUFFER CHO WAVEFORM
        # ============================================================
        sensor = self._get_sensor()
        if sensor and hasattr(sensor, "pop_visual_samples"):
            raw_samples = sensor.pop_visual_samples()
            if raw_samples:
                # Đẩy cả mảng vào waveform (widget tự auto-scale)
                self.screen.update_waveform(raw_samples)

        now = time.time()
        finger_present = bool(status.get("finger_detected", sensor_data.get("finger_detected", False)))
        window_fill = float(status.get("window_fill", sensor_data.get("window_fill", 0.0)) or 0.0)
        signal_quality = float(status.get("signal_quality_ir", sensor_data.get("signal_quality_ir", 0.0)) or 0.0)
        signal_quality_index = float(status.get("signal_quality_index", sensor_data.get("signal_quality_index", 0.0)) or 0.0)  # NEW: SQI
        detection_score = float(status.get("finger_detection_score", sensor_data.get("finger_detection_score", 0.0)) or 0.0)
        detection_amp = float(status.get("finger_signal_amplitude", sensor_data.get("finger_signal_amplitude", 0.0)) or 0.0)
        detection_ratio = float(status.get("finger_signal_ratio", sensor_data.get("finger_signal_ratio", 0.0)) or 0.0)
        spo2_cv = float(status.get("spo2_cv", sensor_data.get("spo2_cv", 0.0)) or 0.0)  # NEW: CV
        peak_count = int(status.get("peak_count", sensor_data.get("peak_count", 0)) or 0)  # NEW: Peak count
        measurement_ready = bool(status.get("measurement_ready", sensor_data.get("measurement_ready", False)))
        measurement_status = status.get("status", "idle") or "idle"

        # Hiển thị thông tin tín hiệu (không phụ thuộc state) - Bao gồm SQI và metadata
        self.screen.show_signal_info(signal_quality, signal_quality_index, detection_score, detection_amp, detection_ratio, spo2_cv, peak_count)

        hr_valid = bool(sensor_data.get("hr_valid"))
        spo2_valid = bool(sensor_data.get("spo2_valid"))
        heart_rate = float(sensor_data.get("heart_rate", 0.0) or 0.0)
        spo2 = float(sensor_data.get("spo2", 0.0) or 0.0)
        self.screen.update_live_metrics(heart_rate, hr_valid, spo2, spo2_valid, self.state)
        
        # ============================================================
        # TRACK BEST RESULTS - Lưu kết quả tốt nhất trong phiên đo
        # STRATEGY: Dùng MEDIAN của history thay vì first valid value
        # để tránh bias từ noise đầu phiên đo
        # ============================================================
        if hr_valid and heart_rate > 0:
            # Always track valid HR to update best at finalization
            self.best_hr_valid = True
        
        if spo2_valid and spo2 > 0:
            # Always track valid SpO2 to update best at finalization
            self.best_spo2_valid = True

        # ============================================================
        # STATE: WAITING - Chờ ngón tay (KHÔNG ĐẾM NGƯỢC)
        # ============================================================
        if self.state == self.STATE_WAITING:
            # Hiển thị hướng dẫn chờ ngón tay (KHÔNG có countdown)
            self.screen.show_waiting_instructions()
            # Progress = 0% khi đang chờ
            self.screen.update_progress(0.0, "waiting", 0.0)
            
            if finger_present:
                # Phát hiện ngón tay → bắt đầu đo NGAY LẬP TỨC
                self.state = self.STATE_MEASURING
                self.measure_started = now
                self.deadline = now + self.MEASUREMENT_DURATION + self.TIMEOUT_MARGIN
                self.finger_lost_ts = None
                self.screen.on_measurement_started(self.MEASUREMENT_DURATION)
                self.logger.info("Phát hiện ngón tay → Bắt đầu đo (%ds)", self.MEASUREMENT_DURATION)
            
            # Chờ vô hạn - chỉ user cancel mới dừng
            return True

        if self.state != self.STATE_MEASURING:
            return True

        # ============================================================
        # STATE: MEASURING - Tính measurement_elapsed chính xác
        # ============================================================
        # CRITICAL: Tính elapsed CHỈ dựa trên thời gian CÓ ngón tay
        if not finger_present:
            # Mất ngón tay → DỪNG ĐẾM NGƯỢC
            if self.finger_lost_ts is None:
                # Lần đầu mất ngón tay → ghi nhận thời điểm
                self.finger_lost_ts = now
                self.logger.warning("Ngón tay rời khỏi cảm biến - DỪNG đếm ngược")
            
            # Tính elapsed = thời gian từ measure_started đến finger_lost_ts
            time_with_finger = self.finger_lost_ts - self.measure_started
            measurement_elapsed = time_with_finger
            
            # Grace period check
            pause_duration = now - self.finger_lost_ts
            if pause_duration > self.FINGER_LOSS_GRACE:
                self.logger.error("Mất ngón tay quá %.1fs - Hủy phiên đo", self.FINGER_LOSS_GRACE)
                self._finalize(success=False, reason="finger_removed", snapshot=sensor_data)
                return False
            
            # Hiển thị trạng thái PAUSE
            remaining_time = max(0.0, self.MEASUREMENT_DURATION - measurement_elapsed)
            progress_percent = (measurement_elapsed / self.MEASUREMENT_DURATION * 100.0) if self.MEASUREMENT_DURATION else 0.0
            self.screen.update_progress(progress_percent, "paused", remaining_time)
            self.screen.show_finger_instruction(missing=True)
            
        else:
            # Có ngón tay → TIẾP TỤC ĐẾM NGƯỢC
            if self.finger_lost_ts is not None:
                # Ngón tay vừa quay lại → điều chỉnh measure_started
                pause_duration = now - self.finger_lost_ts
                self.measure_started += pause_duration  # Dịch thời điểm bắt đầu về sau
                self.deadline += pause_duration  # Kéo dài deadline tương ứng
                self.logger.info("Ngón tay quay lại - TIẾP TỤC đếm (đã tạm dừng %.1fs)", pause_duration)
                self.finger_lost_ts = None
            
            # Tính elapsed bình thường khi có ngón tay
            measurement_elapsed = now - self.measure_started
            remaining_time = max(0.0, self.MEASUREMENT_DURATION - measurement_elapsed)
            progress_percent = (measurement_elapsed / self.MEASUREMENT_DURATION * 100.0) if self.MEASUREMENT_DURATION else 0.0
            
            # Cập nhật UI - progress dựa trên thời gian đo (trong giai đoạn measuring)
            # Window fill chỉ dùng để tham khảo hoặc trong giai đoạn chờ
            progress_display = progress_percent
            self.screen.update_progress(progress_display, measurement_status, remaining_time)
            
            # Hiển thị hướng dẫn phù hợp
            if measurement_status == "poor_signal":
                self.screen.show_signal_warning()
            else:
                self.screen.show_measurement_guidance(remaining_time)

        # ============================================================
        # KIỂM TRA ĐIỀU KIỆN KẾT THÚC ĐO
        # ============================================================
        has_valid_metrics = (hr_valid and heart_rate > 0) or (spo2_valid and spo2 > 0)
        has_both_metrics = (hr_valid and heart_rate > 0) and (spo2_valid and spo2 > 0)
        
        # Kết thúc khi:
        # 1. Đủ thời gian tối thiểu (12s) VÀ có cả HR & SpO2
        # 2. HOẶC đủ thời gian đầy đủ (15s) VÀ có ít nhất 1 giá trị
        if measurement_elapsed >= self.MINIMUM_MEASUREMENT_TIME:
            if has_both_metrics:
                self.logger.info("Đo hoàn tất sau %.1fs - Có đủ HR và SpO2", measurement_elapsed)
                self._finalize(success=True, reason="measurement_complete", snapshot=sensor_data)
                return False
            elif measurement_elapsed >= self.MEASUREMENT_DURATION and has_valid_metrics:
                self.logger.warning("Đo hoàn tất sau %.1fs - Chỉ có 1 giá trị", measurement_elapsed)
                self._finalize(success=True, reason="partial_complete", snapshot=sensor_data)
                return False

        # Timeout tuyệt đối
        if now >= self.deadline:
            self.logger.error(
                "Timeout đo nhịp tim sau %.1fs (chất lượng=%.1f%%)",
                measurement_elapsed,
                signal_quality,
            )
            self._finalize(success=False, reason="timeout", snapshot=sensor_data)
            return False

        return True

    def _finalize(self, success: bool, reason: str, snapshot: Dict[str, Any]) -> None:
        previous_state = self.state
        self.state = self.STATE_FINISHED if success else self.STATE_IDLE
        self._cancel_poll()

        sensor = self._get_sensor()
        if sensor and hasattr(sensor, "end_measurement_session"):
            try:
                sensor.end_measurement_session()
            except Exception as exc:  # pragma: no cover - safety log
                self.logger.debug("Không thể end_measurement_session: %s", exc)

        try:
            self.app.stop_sensor(self.sensor_name)
        except Exception as exc:  # pragma: no cover - safety log
            self.logger.debug("Không thể dừng sensor %s: %s", self.sensor_name, exc)

        # ============================================================
        # USE BEST RESULTS - Ưu tiên kết quả tốt nhất trong phiên đo
        # Snapshot cuối có thể bị noise, best_* giữ giá trị ổn định nhất
        # ============================================================
        snapshot_hr_valid = bool(snapshot.get("hr_valid"))
        snapshot_spo2_valid = bool(snapshot.get("spo2_valid"))
        snapshot_hr = float(snapshot.get("heart_rate", 0.0) or 0.0)
        snapshot_spo2 = float(snapshot.get("spo2", 0.0) or 0.0)
        
        # ============================================================
        # IMPROVED: Dùng MEDIAN của history thay vì first valid value
        # Lý do: Median robust hơn với noise và outliers
        # History nằm ở SENSOR, không phải controller
        # ============================================================
        sensor = self._get_sensor()
        
        if self.best_hr_valid and sensor and hasattr(sensor, 'hr_history') and len(sensor.hr_history) > 0:
            # Dùng median history của sensor (đã được filter)
            heart_rate = float(np.median(list(sensor.hr_history)))
            hr_valid = True
            self.logger.info("[Finalize] Dùng HR median=%.1f từ %d samples (snapshot=%.1f)", 
                            heart_rate, len(sensor.hr_history), snapshot_hr)
        else:
            heart_rate = snapshot_hr if snapshot_hr_valid and snapshot_hr > 0 else 0.0
            hr_valid = snapshot_hr_valid and snapshot_hr > 0
            if not self.best_hr_valid:
                self.logger.warning("[Finalize] Không có HR valid trong phiên đo")
        
        if self.best_spo2_valid and sensor and hasattr(sensor, 'spo2_history') and len(sensor.spo2_history) > 0:
            # Dùng median history của sensor (đã được filter)
            # CRITICAL FIX: Lọc ra SpO2 > 90% (healthy range) nếu có
            spo2_values = list(sensor.spo2_history)
            healthy_spo2 = [s for s in spo2_values if 90 <= s <= 100]
            
            if healthy_spo2:
                # Ưu tiên median từ healthy range
                spo2 = float(np.median(healthy_spo2))
                self.logger.info("[Finalize] Dùng SpO2 healthy median=%.1f từ %d/%d samples (snapshot=%.1f)", 
                                spo2, len(healthy_spo2), len(spo2_values), snapshot_spo2)
            else:
                # Fallback: dùng median toàn bộ
                spo2 = float(np.median(spo2_values))
                self.logger.info("[Finalize] Dùng SpO2 median=%.1f từ %d samples (snapshot=%.1f)", 
                                spo2, len(spo2_values), snapshot_spo2)
            spo2_valid = True
        else:
            spo2 = snapshot_spo2 if snapshot_spo2_valid and snapshot_spo2 > 0 else 0.0
            spo2_valid = snapshot_spo2_valid and snapshot_spo2 > 0
            if not self.best_spo2_valid:
                self.logger.warning("[Finalize] Không có SpO2 valid trong phiên đo")
        
        quality = float(snapshot.get("signal_quality_ir", 0.0) or 0.0)
        status = self._extract_status(snapshot)
        quality = float(status.get("signal_quality_ir", quality))
        
        # Nếu có best results, coi như success=True
        has_best_results = (self.best_hr_valid and self.best_hr > 0) or (self.best_spo2_valid and self.best_spo2 > 0)
        if has_best_results and not success:
            success = True
            reason = "best_results_available"
            self.logger.info("[Finalize] Có best results → đánh dấu success=True")

        self.screen.on_measurement_complete(
            success=success,
            reason=reason,
            heart_rate=heart_rate,
            spo2=spo2,
            hr_valid=hr_valid,
            spo2_valid=spo2_valid,
            signal_quality=quality,
            previous_state=previous_state,
        )

    def _extract_status(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        status_map = sensor_data.get("sensor_status") if isinstance(sensor_data, dict) else None
        if isinstance(status_map, dict):
            status = status_map.get(self.sensor_name)
            if isinstance(status, dict):
                return status
        return {
            "finger_detected": bool(sensor_data.get("finger_detected", False)),
            "signal_quality_ir": float(sensor_data.get("signal_quality_ir", 0.0) or 0.0),
            "window_fill": float(sensor_data.get("window_fill", 0.0) or 0.0),
            "measurement_ready": bool(sensor_data.get("measurement_ready", False)),
        }


class HeartRateScreen(Screen):
    """Màn hình đo nhịp tim & SpO2 với controller tách riêng."""

    # ------------------------------------------------------------------
    # Initialization & Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)

        # Thời gian đo theo chuẩn y tế được quản lý bởi Controller
        # Không cần lưu ở Screen nữa
        self.current_hr = 0.0
        self.current_spo2 = 0.0
        
        # ============================================================
        # GRACE PERIOD - Giữ giá trị cũ khi mất tín hiệu tạm thời
        # ============================================================
        self._last_valid_hr = 0.0
        self._last_valid_spo2 = 0.0
        self._hr_invalid_since = 0.0  # Timestamp khi HR bắt đầu invalid
        self._spo2_invalid_since = 0.0  # Timestamp khi SpO2 bắt đầu invalid
        self._grace_period = 2.5  # Giữ giá trị cũ trong 2.5 giây
        self._dimmed_alpha = 0.5  # Độ mờ khi hiển thị giá trị cũ

        self._build_layout()
        self.controller = HeartRateMeasurementController(self)

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        main_layout = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=(dp(8), dp(6), dp(8), dp(8)),
        )

        from kivy.graphics import Color, Rectangle  # tránh import vòng ở module load

        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)

        self._create_header(main_layout)
        self._create_measurement_panel(main_layout)
        self._create_status_display(main_layout)
        self._create_controls(main_layout)

        self.add_widget(main_layout)

    def _update_bg(self, instance, _value) -> None:
        self.bg_rect.size = instance.size
        self.bg_rect.pos = instance.pos

    def _create_header(self, parent) -> None:
        header_card = MDCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            padding=(dp(6), 0, dp(12), 0),
            radius=[dp(18)],
            md_bg_color=MED_PRIMARY,
        )

        back_btn = MDIconButton(
            icon="arrow-left",
            theme_icon_color="Custom",
            icon_color=TEXT_PRIMARY,
            size_hint=(None, None),
            pos_hint={"center_y": 0.5},
        )
        back_btn.bind(on_release=self._on_back_pressed)
        header_card.add_widget(back_btn)

        title_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(2),
            size_hint_x=1,
        )

        title_label = MDLabel(
            text="NHỊP TIM & SpO2",
            font_style="Subtitle1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(title_label)

        subtitle_label = MDLabel(
            text="Giữ ngón tay cố định khi đo",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
        )
        subtitle_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(subtitle_label)

        header_card.add_widget(title_box)
        parent.add_widget(header_card)

    def _create_measurement_panel(self, parent) -> None:
        # Tối ưu cho màn hình 480×320 (3.5 inch)
        # Bố cục: [Metrics bên trái] | [Pulse bên phải]
        
        panel_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(130),
            padding=(dp(6), dp(6), dp(6), dp(6)),
        )

        # ============================================================
        # LEFT: HR & SpO2 Metrics (cột trái)
        # ============================================================
        metrics_card = MDCard(
            orientation="vertical",
            size_hint_x=0.65,
            padding=(dp(8), dp(8), dp(8), dp(8)),
            spacing=dp(4),
            radius=[dp(14)],
            md_bg_color=MED_CARD_BG,
        )

        # HR Row
        hr_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(42),
        )
        hr_icon = MDIcon(
            icon="heart-pulse",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(32), dp(32)),
        )
        hr_icon.icon_size = dp(28)
        hr_row.add_widget(hr_icon)

        hr_value_box = MDBoxLayout(orientation="vertical", spacing=dp(0), size_hint_x=1)
        hr_label = MDLabel(
            text="Nhịp tim",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        hr_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        hr_value_box.add_widget(hr_label)

        self.hr_value_label = MDLabel(
            text="-- BPM",
            font_style="H5",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
            bold=True,
        )
        self.hr_value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        hr_value_box.add_widget(self.hr_value_label)
        hr_row.add_widget(hr_value_box)
        metrics_card.add_widget(hr_row)

        # SpO2 Row
        spo2_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(42),
        )
        spo2_icon = MDIcon(
            icon="blood-bag",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(32), dp(32)),
        )
        spo2_icon.icon_size = dp(28)
        spo2_row.add_widget(spo2_icon)

        spo2_value_box = MDBoxLayout(orientation="vertical", spacing=dp(0), size_hint_x=1)
        spo2_label = MDLabel(
            text="SpO2",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        spo2_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        spo2_value_box.add_widget(spo2_label)

        self.spo2_value_label = MDLabel(
            text="-- %",
            font_style="H5",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
            bold=True,
        )
        self.spo2_value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        spo2_value_box.add_widget(self.spo2_value_label)
        spo2_row.add_widget(spo2_value_box)
        metrics_card.add_widget(spo2_row)

        # Instruction at bottom
        self.instruction_label = MDLabel(
            text="Đặt ngón tay lên cảm biến",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.6),
            halign="left",
            size_hint_y=None,
            height=dp(20),
        )
        self.instruction_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        metrics_card.add_widget(self.instruction_label)

        panel_layout.add_widget(metrics_card)

        # ============================================================
        # RIGHT: Waveform Graph + Pulse Icon (cột phải - mở rộng)
        # ============================================================
        right_column = MDBoxLayout(
            orientation="vertical",
            size_hint_x=0.40,  # Tăng từ 0.35 lên 0.40 để có chỗ cho waveform
            spacing=dp(2),
            padding=(dp(4), dp(4), dp(4), dp(4)),
        )

        # Waveform graph (phần lớn diện tích - giống monitor y tế)
        waveform_card = MDCard(
            orientation="vertical",
            size_hint_y=0.70,
            radius=[dp(8)],
            md_bg_color=(0.05, 0.15, 0.22, 1),
            padding=(dp(2), dp(2), dp(2), dp(2)),
        )
        self.waveform_widget = WaveformWidget()
        self.waveform_widget.size_hint = (1, 1)
        waveform_card.add_widget(self.waveform_widget)
        right_column.add_widget(waveform_card)
        
        # Bottom row: Heart icon + Signal quality
        bottom_info = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=0.30,
            spacing=dp(4),
        )
        
        # Pulse animation (nhỏ hơn, bên trái)
        pulse_wrapper = AnchorLayout(
            anchor_x="center",
            anchor_y="center",
            size_hint_x=0.35,
        )
        self.pulse_widget = PulseAnimation()
        self.pulse_widget.size_hint = (None, None)
        self.pulse_widget.width = dp(40)
        self.pulse_widget.height = dp(40)
        pulse_wrapper.add_widget(self.pulse_widget)
        bottom_info.add_widget(pulse_wrapper)

        # Signal quality info (bên phải)
        self.signal_label = MDLabel(
            text="SQI: --",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
            size_hint_x=0.65,
        )
        self.signal_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        bottom_info.add_widget(self.signal_label)
        
        right_column.add_widget(bottom_info)

        panel_layout.add_widget(right_column)
        parent.add_widget(panel_layout)

    def _create_status_display(self, parent) -> None:
        # Compact status bar cho màn hình nhỏ
        status_card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(48),
            padding=(dp(8), dp(6), dp(8), dp(6)),
            spacing=dp(2),
            radius=[dp(12)],
            md_bg_color=MED_CARD_BG,
        )

        self.status_label = MDLabel(
            text="Sẵn sàng đo",
            font_style="Body2",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
        )
        self.status_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        status_card.add_widget(self.status_label)

        self.progress_bar = MDProgressBar(
            max=100,
            value=0,
            color=MED_CARD_ACCENT,
            size_hint_y=None,
            height=dp(3),
        )
        status_card.add_widget(self.progress_bar)

        parent.add_widget(status_card)

    def _create_controls(self, parent) -> None:
        # ============================================================
        # CONTROLS - Nút bấm lớn, màu sắc rõ ràng cho người già
        # Dùng MDFillRoundFlatIconButton (nút đặc) thay vì viền
        # ============================================================
        control_layout = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),  # Tăng chiều cao để nút dễ bấm hơn
            spacing=dp(10),
            padding=(dp(6), dp(4), dp(6), dp(4)),
        )

        # Nút Bắt đầu/Dừng - Màu xanh đậm nổi bật
        self.start_stop_btn = MDFillRoundFlatIconButton(
            text="BẮT ĐẦU",
            icon="play-circle",
            md_bg_color=BTN_START_COLOR,
            text_color=TEXT_PRIMARY,
            icon_color=TEXT_PRIMARY,
            size_hint_x=0.55,
            font_size="16sp",
            icon_size="24sp",
        )
        self.start_stop_btn.bind(on_press=self._on_start_stop_pressed)
        control_layout.add_widget(self.start_stop_btn)

        # Nút Lưu - Ban đầu xám (vô hiệu), chuyển xanh lá khi có kết quả
        self.save_btn = MDFillRoundFlatIconButton(
            text="LƯU",
            icon="content-save",
            disabled=True,
            md_bg_color=BTN_DISABLED_COLOR,
            text_color=(1, 1, 1, 0.5),
            icon_color=(1, 1, 1, 0.5),
            size_hint_x=0.45,
            font_size="16sp",
            icon_size="24sp",
        )
        self.save_btn.bind(on_press=self._on_save_pressed)
        control_layout.add_widget(self.save_btn)

        parent.add_widget(control_layout)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _style_start_button(self, active: bool) -> None:
        """Style nút Bắt đầu/Dừng với màu sắc nổi bật."""
        if active:
            self.start_stop_btn.text = "DỪNG"
            self.start_stop_btn.icon = "stop-circle"
            self.start_stop_btn.md_bg_color = BTN_STOP_COLOR  # Đỏ
            self.start_stop_btn.text_color = TEXT_PRIMARY
            self.start_stop_btn.icon_color = TEXT_PRIMARY
        else:
            self.start_stop_btn.text = "BẮT ĐẦU"
            self.start_stop_btn.icon = "play-circle"
            self.start_stop_btn.md_bg_color = BTN_START_COLOR  # Xanh đậm
            self.start_stop_btn.text_color = TEXT_PRIMARY
            self.start_stop_btn.icon_color = TEXT_PRIMARY

    def _style_save_button(self, enabled: bool) -> None:
        """Style nút Lưu - Xanh lá khi enabled, xám khi disabled."""
        self.save_btn.disabled = not enabled
        if enabled:
            self.save_btn.md_bg_color = BTN_SAVE_COLOR  # Xanh lá
            self.save_btn.text_color = TEXT_PRIMARY
            self.save_btn.icon_color = TEXT_PRIMARY
        else:
            self.save_btn.md_bg_color = BTN_DISABLED_COLOR  # Xám
            self.save_btn.text_color = (1, 1, 1, 0.5)
            self.save_btn.icon_color = (1, 1, 1, 0.5)
    
    # ============================================================
    # DYNAMIC COLORS - Màu sắc thay đổi theo ngưỡng sức khỏe
    # ============================================================
    def _get_hr_color(self, hr: float) -> tuple:
        """
        Lấy màu cho nhịp tim theo ngưỡng sức khỏe.
        
        Ngưỡng (theo WHO/AHA):
        - 60-100 BPM: Bình thường → Xanh lá
        - 50-60 hoặc 100-120: Cần chú ý → Vàng
        - <50 hoặc >120: Nguy hiểm → Đỏ
        """
        if 60 <= hr <= 100:
            return COLOR_HEALTHY  # Xanh lá - Tốt
        elif 50 <= hr < 60 or 100 < hr <= 120:
            return COLOR_CAUTION  # Vàng - Cần chú ý
        else:
            return COLOR_DANGER  # Đỏ - Nguy hiểm
    
    def _get_spo2_color(self, spo2: float) -> tuple:
        """
        Lấy màu cho SpO2 theo ngưỡng sức khỏe.
        
        Ngưỡng (theo FDA/WHO):
        - 96-100%: Bình thường → Xanh lá
        - 90-95%: Cần chú ý → Vàng
        - <90%: Nguy hiểm → Đỏ
        """
        if spo2 >= 96:
            return COLOR_HEALTHY  # Xanh lá - Tốt
        elif spo2 >= 90:
            return COLOR_CAUTION  # Vàng - Cần chú ý
        else:
            return COLOR_DANGER  # Đỏ - Nguy hiểm

    def on_measurement_preparing(self) -> None:
        """Chuẩn bị đo - chờ ngón tay (KHÔNG có countdown)."""
        self._style_start_button(True)
        self._style_save_button(False)
        self.progress_bar.value = 0
        self.hr_value_label.text = "-- BPM"
        self.spo2_value_label.text = "-- %"
        self.status_label.text = "Đang khởi động cảm biến..."
        self.signal_label.text = "Chất lượng tín hiệu: --"
        self.instruction_label.text = f"Đặt ngón tay lên cảm biến. Đo tối thiểu {self.controller.MINIMUM_MEASUREMENT_TIME:.0f}s."
        self.pulse_widget.start_pulse(60.0)

    def show_waiting_instructions(self) -> None:
        """Hiển thị hướng dẫn chờ ngón tay - KHÔNG có countdown."""
        self.status_label.text = "⏳ Chờ ngón tay"

    def on_measurement_started(self, duration: float) -> None:
        """Bắt đầu đo với countdown."""
        self.status_label.text = f"Đang đo {duration:.0f}s"

    def show_finger_instruction(self, missing: bool) -> None:
        if missing:
            self.status_label.text = "Mất ngón tay"
            self.instruction_label.text = "Đặt lại"
        else:
            self.instruction_label.text = "Giữ"

    def show_measurement_guidance(self, remaining_time: float) -> None:
        """Intentionally empty - status_label đã được cập nhật trong update_progress()."""
        # NOTE: Method này tồn tại để Controller có thể gọi mà không cần kiểm tra.
        # Việc cập nhật instruction_label được xử lý trong update_progress() để tập trung
        # tất cả UI updates vào một nơi, tránh flicker do nhiều updates liên tiếp.
        pass

    def show_signal_warning(self) -> None:
        self.instruction_label.text = "Tín hiệu yếu"

    def update_progress(self, percent: float, measurement_status: str, remaining_time: float) -> None:
        """Cập nhật thanh tiến trình (compact cho màn hình nhỏ)."""
        self.progress_bar.value = max(0.0, min(100.0, percent))
        
        # Calculate total measurement duration for display
        total_duration = self.controller.MEASUREMENT_DURATION
        
        if measurement_status == "waiting":
            self.status_label.text = "Chờ ngón tay..."
            self.instruction_label.text = f"Đặt ngón tay lên cảm biến. Đo tối thiểu {self.controller.MINIMUM_MEASUREMENT_TIME:.0f}s."
            self.status_label.text_color = TEXT_PRIMARY
        elif measurement_status == "paused":
            self.status_label.text = f"Mất ngón tay! Đặt lại ({remaining_time:.0f}s)"
            self.instruction_label.text = "Giữ yên tĩnh, tín hiệu sẽ ổn định."
            self.status_label.text_color = MED_WARNING
        elif measurement_status == "poor_signal":
            self.status_label.text = "Tín hiệu yếu"
            self.instruction_label.text = "Cố định ngón tay, tránh rung lắc."
            self.status_label.text_color = MED_WARNING
        elif remaining_time > 0:
            # Display elapsed time / total duration
            self.status_label.text = f"Đang đo {total_duration - remaining_time:.0f}/{total_duration:.0f}s"
            self.instruction_label.text = "Giữ ngón tay cố định trong suốt quá trình đo."
            self.status_label.text_color = TEXT_PRIMARY
        else:
            self.status_label.text = "Đang xử lý kết quả..."
            self.instruction_label.text = "Vui lòng chờ."
            self.status_label.text_color = TEXT_PRIMARY

    def show_signal_info(
        self, 
        quality: float, 
        sqi: float,  # Signal Quality Index
        detection_score: float, 
        amplitude: float, 
        ratio: float,
        cv: float = 0.0,  # Coefficient of variation
        peak_count: int = 0  # Number of peaks
    ) -> None:
        """
        Hiển thị chất lượng tín hiệu ngắn gọn.
        
        NOTE: Waveform giờ được cập nhật từ raw IR samples trong controller,
        không dùng amplitude nữa để có tín hiệu real-time chính xác hơn.
        """
        # Sử dụng SQI (0-100) để đánh giá chất lượng tổng thể
        if sqi >= 80:
            quality_text = "Tốt"
            color = COLOR_HEALTHY
        elif sqi >= 50:
            quality_text = "TB"
            color = COLOR_CAUTION
        else:
            quality_text = "Yếu"
            color = COLOR_DANGER
        
        # Hiển thị SQI compact hơn
        self.signal_label.text = f"SQI:{sqi:.0f}% {quality_text}"
        self.signal_label.text_color = color
        
        # Cập nhật màu waveform theo chất lượng tín hiệu
        if hasattr(self, 'waveform_widget'):
            self.waveform_widget.set_color(color)

    def update_live_metrics(
        self,
        heart_rate: float,
        hr_valid: bool,
        spo2: float,
        spo2_valid: bool,
        controller_state: str,
    ) -> None:
        """
        Cập nhật chỉ số realtime với Grace Period.
        
        Grace Period: Khi mất tín hiệu tạm thời, giữ giá trị cũ trong 2.5s
        và làm mờ (dim) để người dùng biết đó là giá trị lịch sử.
        """
        import time
        now = time.time()
        
        if controller_state in (HeartRateMeasurementController.STATE_MEASURING, HeartRateMeasurementController.STATE_WAITING):
            # ============================================================
            # CẬP NHẬT HR VỚI GRACE PERIOD
            # ============================================================
            if hr_valid and heart_rate > 0:
                # Tín hiệu tốt - cập nhật giá trị và reset invalid timer
                self._last_valid_hr = heart_rate
                self._hr_invalid_since = 0.0
                
                self.hr_value_label.text = f"{heart_rate:.0f} BPM"
                self.hr_value_label.text_color = self._get_hr_color(heart_rate)
                self.pulse_widget.start_pulse(max(40.0, heart_rate))
                self.waveform_widget.set_color(self._get_hr_color(heart_rate))
            else:
                # Tín hiệu mất - kiểm tra Grace Period
                if self._hr_invalid_since == 0.0:
                    self._hr_invalid_since = now  # Bắt đầu đếm thời gian invalid
                
                time_invalid = now - self._hr_invalid_since
                
                if time_invalid < self._grace_period and self._last_valid_hr > 0:
                    # Trong Grace Period - hiển thị giá trị cũ nhưng Mờ ĐI
                    hr_color = self._get_hr_color(self._last_valid_hr)
                    dimmed_color = (hr_color[0], hr_color[1], hr_color[2], self._dimmed_alpha)
                    self.hr_value_label.text = f"{self._last_valid_hr:.0f} BPM"
                    self.hr_value_label.text_color = dimmed_color
                    # Giữ pulse animation với nhịp cũ
                    self.pulse_widget.start_pulse(max(40.0, self._last_valid_hr))
                else:
                    # Hết Grace Period - hiển thị "--"
                    self.hr_value_label.text = "-- BPM"
                    self.hr_value_label.text_color = TEXT_PRIMARY
                    self.pulse_widget.stop_pulse()

            # ============================================================
            # CẬP NHẬT SPO2 VỚI GRACE PERIOD
            # ============================================================
            if spo2_valid and spo2 > 0:
                # Tín hiệu tốt
                self._last_valid_spo2 = spo2
                self._spo2_invalid_since = 0.0
                
                self.spo2_value_label.text = f"{spo2:.1f} %"
                self.spo2_value_label.text_color = self._get_spo2_color(spo2)
            else:
                # Tín hiệu mất - kiểm tra Grace Period
                if self._spo2_invalid_since == 0.0:
                    self._spo2_invalid_since = now
                
                time_invalid = now - self._spo2_invalid_since
                
                if time_invalid < self._grace_period and self._last_valid_spo2 > 0:
                    # Trong Grace Period - hiển thị giá trị cũ nhưng Mờ ĐI
                    spo2_color = self._get_spo2_color(self._last_valid_spo2)
                    dimmed_color = (spo2_color[0], spo2_color[1], spo2_color[2], self._dimmed_alpha)
                    self.spo2_value_label.text = f"{self._last_valid_spo2:.1f} %"
                    self.spo2_value_label.text_color = dimmed_color
                else:
                    # Hết Grace Period - hiển thị "--"
                    self.spo2_value_label.text = "-- %"
                    self.spo2_value_label.text_color = TEXT_PRIMARY
    
    def update_waveform(self, samples: list) -> None:
        """
        Cập nhật biểu đồ sóng với batch dữ liệu từ sensor.
        Được gọi từ controller mỗi khi có dữ liệu mới.
        
        Args:
            samples: List các giá trị raw IR signal từ MAX30102
        """
        if hasattr(self, 'waveform_widget'):
            self.waveform_widget.update_data(samples)

    def on_measurement_complete(
        self,
        success: bool,
        reason: str,
        heart_rate: float,
        spo2: float,
        hr_valid: bool,
        spo2_valid: bool,
        signal_quality: float,
        previous_state: str,
    ) -> None:
        self.pulse_widget.stop_pulse()
        self._style_start_button(False)

        # ============================================================
        # CRITICAL: Reset HR announcement state to prevent TTS loop
        # Đánh dấu session đã kết thúc - không cho TTS đọc thêm
        # ============================================================
        self.app_instance._hr_last_announced = None
        # KHÔNG reset _hr_result_announced_this_session ở đây
        # vì chúng ta muốn ngăn TTS đọc lại sau khi đo xong
        # Flag này sẽ chỉ reset khi vào màn hình mới hoặc bắt đầu session mới

        if success and ((hr_valid and heart_rate > 0) or (spo2_valid and spo2 > 0)):
            self.current_hr = heart_rate if hr_valid and heart_rate > 0 else 0.0
            self.current_spo2 = spo2 if spo2_valid and spo2 > 0 else 0.0

            self.hr_value_label.text = f"{self.current_hr:.0f} BPM" if self.current_hr > 0 else "-- BPM"
            self.spo2_value_label.text = f"{self.current_spo2:.1f} %" if self.current_spo2 > 0 else "-- %"
            self.status_label.text = "Hoàn tất - Nhấn 'Lưu' để lưu"
            self.progress_bar.value = 100.0
            self.instruction_label.text = "Kết quả OK"
            self._style_save_button(True)
            
            # ============================================================
            # STEP 1: TTS - Đọc kết quả cuối cùng (CHỈ ở đây, sau khi đo hoàn tất)
            # ============================================================
            if self.current_hr > 0 and self.current_spo2 > 0:
                hr_int = int(round(self.current_hr))
                spo2_int = int(round(self.current_spo2))
                self.app_instance._speak_scenario(
                    ScenarioID.HR_RESULT, 
                    bpm=hr_int, 
                    spo2=spo2_int
                )
                self.logger.info("TTS đọc kết quả: HR=%d, SpO2=%d", hr_int, spo2_int)
            
            # ============================================================
            # STEP 2: Kiểm tra ngưỡng & TTS đọc cảnh báo nếu cần
            # Gọi ngay sau khi đo hoàn tất, TRƯỚC khi user nhấn "Lưu"
            # Để TTS có thể đọc cảnh báo ngay lập tức
            # ============================================================
            try:
                # Chuẩn bị health_data cho alert checking
                health_data_for_alert = {
                    'heart_rate': self.current_hr,
                    'spo2': self.current_spo2,
                    'timestamp': time.time()
                }
                
                # Gọi hàm kiểm tra alert (sẽ tạo alert nếu cần và TTS đọc cảnh báo)
                self.app_instance._check_and_create_alert_immediate(health_data_for_alert)
                
            except Exception as e:
                self.logger.error("Error checking alerts: %s", e)
            
            self.logger.info(
                "Đo nhịp tim thành công (HR=%.1f valid=%s, SpO2=%.1f valid=%s)",
                self.current_hr,
                hr_valid,
                self.current_spo2,
                spo2_valid,
            )
        else:
            self.current_hr = 0.0
            self.current_spo2 = 0.0
            self.hr_value_label.text = "-- BPM"
            self.spo2_value_label.text = "-- %"
            self.progress_bar.value = 0
            self._style_save_button(False)

            failure_reason = {
                "timeout": "Tín hiệu yếu",
                "no_finger": "Không phát hiện",
                "finger_removed": "Mất ngón tay",
                "user_cancel": "Hủy",
                "stopped": "Dừng",
            }.get(reason, "Lỗi")
            self.status_label.text = failure_reason
            self.instruction_label.text = "Thử lại"
            if reason != "user_cancel" and previous_state == HeartRateMeasurementController.STATE_MEASURING:
                self.logger.warning(
                    "Measurement failed - hr_valid=%s spo2_valid=%s quality=%.1f reason=%s",
                    hr_valid,
                    spo2_valid,
                    signal_quality,
                    reason,
                )

    def reset_to_idle(self) -> None:
        """Reset giao diện về trạng thái ban đầu."""
        self._style_start_button(False)
        self._style_save_button(False)
        self.progress_bar.value = 0
        
        # Reset HR/SpO2 labels với màu mặc định
        self.hr_value_label.text = "-- BPM"
        self.hr_value_label.text_color = TEXT_PRIMARY
        self.spo2_value_label.text = "-- %"
        self.spo2_value_label.text_color = TEXT_PRIMARY
        
        # Reset status
        self.status_label.text = "Sẵn sàng"
        self.status_label.text_color = TEXT_PRIMARY
        self.signal_label.text = "SQI: --"
        self.signal_label.text_color = TEXT_MUTED
        self.instruction_label.text = "Đặt ngón tay lên cảm biến."
        
        # Reset animations và waveform
        self.pulse_widget.stop_pulse()
        if hasattr(self, 'waveform_widget'):
            self.waveform_widget.clear()
            self.waveform_widget.set_color(COLOR_HEALTHY)
        
        # Reset Grace Period state
        self._last_valid_hr = 0.0
        self._last_valid_spo2 = 0.0
        self._hr_invalid_since = 0.0
        self._spo2_invalid_since = 0.0

    def show_error_status(self, message: str) -> None:
        self.status_label.text = message
        self.logger.error(message)

    # ------------------------------------------------------------------
    # Button callbacks
    # ------------------------------------------------------------------
    def _on_back_pressed(self, _instance) -> None:
        self.controller.stop(user_cancelled=True)
        self.app_instance.navigate_to_screen("dashboard")

    def _on_start_stop_pressed(self, _instance) -> None:
        if self.controller.state in (HeartRateMeasurementController.STATE_WAITING, HeartRateMeasurementController.STATE_MEASURING):
            self.controller.stop(user_cancelled=True)
        else:
            self.controller.start()

    def _on_save_pressed(self, _instance) -> None:
        if self.current_hr <= 0 and self.current_spo2 <= 0:
            return

        measurement_data = {
            "timestamp": time.time(),
            "heart_rate": self.current_hr,
            "spo2": self.current_spo2,
            "measurement_type": "heart_rate_spo2",
        }
        
        # Add metadata from last snapshot for MQTT publishing
        last_snapshot = getattr(self.controller, 'last_snapshot', {})
        sensor_data = last_snapshot.get('sensor_status', {}).get('MAX30102', {})
        
        if sensor_data:
            measurement_data.update({
                'signal_quality_index': sensor_data.get('signal_quality_index', 0.0),
                'peak_count': sensor_data.get('peak_count', 0),
                'measurement_duration': self.controller.MEASUREMENT_DURATION,
                'cv': sensor_data.get('spo2_cv', 0.0),
                'confidence': sensor_data.get('signal_quality_ir', 0.0) / 100.0 if sensor_data.get('signal_quality_ir') else 0.9,
                'spo2_confidence': 0.9,  # Default confidence
                'sampling_rate': 100.0  # MAX30102 default sampling rate
            })
        
        try:
            # ============================================================
            # CRITICAL: Stop sensor & reset state to avoid TTS loop
            # ============================================================
            # Stop sensor immediately to stop callbacks
            try:
                self.app_instance.stop_sensor("MAX30102")
            except Exception as e:
                self.logger.debug("Could not stop MAX30102: %s", e)
            
            # Reset the last announced HR/SpO2 to prevent repeated TTS
            self.app_instance._hr_last_announced = None
            
            self.app_instance.save_measurement_to_database(measurement_data)
            self.logger.info(
                "Đã lưu kết quả HR/SpO2: HR=%.1f BPM, SpO2=%.1f%%",
                self.current_hr,
                self.current_spo2,
            )
            
            # TTS: Announce measurement complete
            self._speak_scenario(ScenarioID.MEASUREMENT_COMPLETE)
            
            self._style_save_button(False)
        except Exception as exc:  # pragma: no cover - safety log
            self.logger.error("Không thể lưu kết quả HR/SpO2: %s", exc)

    # ------------------------------------------------------------------
    # Screen lifecycle
    # ------------------------------------------------------------------
    def on_enter(self) -> None:
        self.logger.info("Heart rate measurement screen entered")
        self.controller.reset()
        self.reset_to_idle()
        
        # Reset TTS announcement flag cho session mới
        self.app_instance._hr_result_announced_this_session = False
        self.app_instance._hr_last_announced = None

    def on_leave(self) -> None:
        self.logger.info("Heart rate measurement screen left")
        self.controller.stop(user_cancelled=True)
        self.controller.reset()
        try:
            self.app_instance.stop_sensor("MAX30102")
        except Exception:
            pass
        self.pulse_widget.stop_pulse()
        
        # Reset TTS state khi rời màn hình
        self.app_instance._hr_result_announced_this_session = False
        self.app_instance._hr_last_announced = None
