"""Màn hình đo nhịp tim & SpO2 với controller điều phối rõ ràng."""

from __future__ import annotations

from typing import Any, Dict, Optional

import logging
import time

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.screenmanager import Screen

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDRectangleFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.progressbar import MDProgressBar

# Import ScenarioID cho TTS
from src.utils.tts_manager import ScenarioID


MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


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
        self.base_font_size = dp(44)

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
            Animation(font_size=self.base_font_size + dp(8), duration=0.12)
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
        
        # Best results tracking - lưu kết quả tốt nhất trong phiên đo
        self.best_hr: float = 0.0
        self.best_hr_valid: bool = False
        self.best_spo2: float = 0.0
        self.best_spo2_valid: bool = False
        self.best_quality: float = 0.0

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
        # Reset best results
        self.best_hr = 0.0
        self.best_hr_valid = False
        self.best_spo2 = 0.0
        self.best_spo2_valid = False
        self.best_quality = 0.0

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
            self.poll_event = Clock.schedule_interval(self._poll_sensor, 0.2)

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
        # Lý do: Đôi khi poll cuối cùng có noise, ta cần giữ best result
        # ============================================================
        if hr_valid and heart_rate > 0:
            # Ưu tiên HR với quality cao hơn, hoặc HR mới nếu quality tương đương
            if not self.best_hr_valid or signal_quality_index >= self.best_quality:
                self.best_hr = heart_rate
                self.best_hr_valid = True
                self.best_quality = max(self.best_quality, signal_quality_index)
        
        if spo2_valid and spo2 > 0:
            # Ưu tiên SpO2 trong range sinh lý (90-100%) với quality cao
            if not self.best_spo2_valid:
                self.best_spo2 = spo2
                self.best_spo2_valid = True
            elif 90 <= spo2 <= 100 and (self.best_spo2 < 90 or signal_quality_index >= self.best_quality):
                # Prefer healthy SpO2 values khi có quality tốt hơn
                self.best_spo2 = spo2
                self.best_quality = max(self.best_quality, signal_quality_index)

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
        
        # Ưu tiên best results nếu có, fallback về snapshot
        if self.best_hr_valid and self.best_hr > 0:
            heart_rate = self.best_hr
            hr_valid = True
            self.logger.info("[Finalize] Dùng best HR=%.1f (snapshot HR=%.1f valid=%s)", 
                            self.best_hr, snapshot_hr, snapshot_hr_valid)
        else:
            heart_rate = snapshot_hr if snapshot_hr_valid and snapshot_hr > 0 else 0.0
            hr_valid = snapshot_hr_valid and snapshot_hr > 0
        
        if self.best_spo2_valid and self.best_spo2 > 0:
            spo2 = self.best_spo2
            spo2_valid = True
            self.logger.info("[Finalize] Dùng best SpO2=%.1f (snapshot SpO2=%.1f valid=%s)", 
                            self.best_spo2, snapshot_spo2, snapshot_spo2_valid)
        else:
            spo2 = snapshot_spo2 if snapshot_spo2_valid and snapshot_spo2 > 0 else 0.0
            spo2_valid = snapshot_spo2_valid and snapshot_spo2 > 0
        
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
        # RIGHT: Pulse Animation + Signal Quality (cột phải)
        # ============================================================
        right_column = MDBoxLayout(
            orientation="vertical",
            size_hint_x=0.35,
            spacing=dp(4),
        )

        # Pulse animation (to hơn, ở bên phải)
        pulse_wrapper = AnchorLayout(
            anchor_x="center",
            anchor_y="center",
            size_hint_x=1,
            size_hint_y=0.65,
        )
        self.pulse_widget = PulseAnimation()
        self.pulse_widget.size_hint = (None, None)
        self.pulse_widget.width = dp(70)
        self.pulse_widget.height = dp(70)
        pulse_wrapper.add_widget(self.pulse_widget)
        right_column.add_widget(pulse_wrapper)

        # Signal quality info
        self.signal_label = MDLabel(
            text="Chất lượng: --",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=0.35,
        )
        self.signal_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        right_column.add_widget(self.signal_label)

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
        # Compact controls cho màn hình 480×320
        control_layout = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
            padding=(dp(4), dp(2), dp(4), dp(2)),
        )

        self.start_stop_btn = MDRectangleFlatIconButton(
            text="Bắt đầu",
            icon="play-circle",
            text_color=MED_CARD_ACCENT,
            line_color=MED_CARD_ACCENT,
            size_hint_x=0.6,
            font_size="14sp",
            icon_size="20sp",
        )
        self.start_stop_btn.bind(on_press=self._on_start_stop_pressed)
        control_layout.add_widget(self.start_stop_btn)

        self.save_btn = MDRectangleFlatIconButton(
            text="Lưu",
            icon="content-save",
            disabled=True,
            text_color=(1, 1, 1, 0.3),
            line_color=(1, 1, 1, 0.3),
            size_hint_x=0.4,
            font_size="14sp",
            icon_size="20sp",
        )
        self.save_btn.bind(on_press=self._on_save_pressed)
        control_layout.add_widget(self.save_btn)

        parent.add_widget(control_layout)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _style_start_button(self, active: bool) -> None:
        if active:
            self.start_stop_btn.text = "Dừng"
            self.start_stop_btn.icon = "stop-circle"
            self.start_stop_btn.text_color = MED_WARNING
            self.start_stop_btn.line_color = MED_WARNING
        else:
            self.start_stop_btn.text = "Bắt đầu"
            self.start_stop_btn.icon = "play-circle"
            self.start_stop_btn.text_color = MED_CARD_ACCENT
            self.start_stop_btn.line_color = MED_CARD_ACCENT

    def _style_save_button(self, enabled: bool) -> None:
        self.save_btn.disabled = not enabled
        if enabled:
            self.save_btn.text_color = MED_CARD_ACCENT
            self.save_btn.line_color = MED_CARD_ACCENT
        else:
            self.save_btn.text_color = (1, 1, 1, 0.3)
            self.save_btn.line_color = (1, 1, 1, 0.3)

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
        sqi: float,  # NEW: Signal Quality Index
        detection_score: float, 
        amplitude: float, 
        ratio: float,
        cv: float = 0.0,  # NEW: Coefficient of variation
        peak_count: int = 0  # NEW: Number of peaks
    ) -> None:
        """Hiển thị chất lượng tín hiệu ngắn gọn cho màn hình nhỏ."""
        # Sử dụng SQI (0-100) để đánh giá chất lượng tổng thể
        if sqi >= 80:
            quality_text = "Tốt"
            color = MED_CARD_ACCENT # Greenish
        elif sqi >= 50:
            quality_text = "Trung bình"
            color = MED_WARNING # Orangeish
        else:
            quality_text = "Kém"
            color = MED_WARNING # Reddish
        
        self.signal_label.text = f"Chất lượng: {quality_text} (SQI: {sqi:.0f}%)"
        self.signal_label.text_color = color

    def update_live_metrics(
        self,
        heart_rate: float,
        hr_valid: bool,
        spo2: float,
        spo2_valid: bool,
        controller_state: str,
    ) -> None:
        if controller_state in (HeartRateMeasurementController.STATE_MEASURING, HeartRateMeasurementController.STATE_WAITING):
            if hr_valid and heart_rate > 0:
                self.hr_value_label.text = f"{heart_rate:.0f} BPM"
                self.pulse_widget.start_pulse(max(40.0, heart_rate))
            else:
                self.hr_value_label.text = "-- BPM"

            if spo2_valid and spo2 > 0:
                self.spo2_value_label.text = f"{spo2:.1f} %"
            else:
                self.spo2_value_label.text = "-- %"

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
        self._style_start_button(False)
        self._style_save_button(False)
        self.progress_bar.value = 0
        self.hr_value_label.text = "-- BPM"
        self.spo2_value_label.text = "-- %"
        self.status_label.text = "Sẵn sàng"
        self.status_label.text_color = TEXT_PRIMARY # Reset màu về mặc định
        self.signal_label.text = "Chất lượng: --"
        self.signal_label.text_color = TEXT_MUTED # Reset màu về mặc định
        self.instruction_label.text = "Đặt ngón tay lên cảm biến."
        self.pulse_widget.stop_pulse()

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
