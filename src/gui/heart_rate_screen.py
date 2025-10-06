"""Màn hình đo nhịp tim & SpO₂ với controller điều phối rõ ràng."""

from __future__ import annotations

from typing import Any, Dict, Optional

import logging
import time

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.screenmanager import Screen

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDRectangleFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.progressbar import MDProgressBar


MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class PulseAnimation(MDBoxLayout):
    """Widget hoạt họa nhịp tim đơn giản."""

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

    WAIT_TIMEOUT = 10.0  # Chờ ngón tay (chỉ để hiển thị UI, không timeout thực sự)
    FINGER_LOSS_GRACE = 3.0  # Grace period khi mất ngón tay
    TIMEOUT_MARGIN = 15.0  # Tăng lên 15s để đủ thời gian thu đủ samples

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
        self.deadline = now + self.screen.measurement_duration + self.TIMEOUT_MARGIN
        self.finger_lost_ts = None
        self.last_snapshot = {}

        self.screen.on_measurement_preparing(self.WAIT_TIMEOUT)
        self._schedule_poll()
        self.logger.info("Bắt đầu chờ ngón tay cho phiên đo nhịp tim")

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
        detection_score = float(status.get("finger_detection_score", sensor_data.get("finger_detection_score", 0.0)) or 0.0)
        detection_amp = float(status.get("finger_signal_amplitude", sensor_data.get("finger_signal_amplitude", 0.0)) or 0.0)
        detection_ratio = float(status.get("finger_signal_ratio", sensor_data.get("finger_signal_ratio", 0.0)) or 0.0)
        measurement_ready = bool(status.get("measurement_ready", sensor_data.get("measurement_ready", False)))
        measurement_status = status.get("status", "idle") or "idle"
        
        # DEBUG: Log finger detection state
        if self.state == self.STATE_WAITING and detection_score > 0:
            self.logger.debug(
                "[POLL] state=%s, finger_present=%s, score=%.2f, amp=%.0f, quality=%.0f",
                self.state,
                finger_present,
                detection_score,
                detection_amp,
                signal_quality,
            )

        elapsed_report = float(status.get("measurement_elapsed", sensor_data.get("measurement_elapsed", 0.0)) or 0.0)
        measurement_elapsed = elapsed_report if elapsed_report > 0 else (now - self.measure_started if self.measure_started else 0.0)
        remaining_time = max(0.0, self.screen.measurement_duration - measurement_elapsed)
        progress = max(window_fill, measurement_elapsed / self.screen.measurement_duration if self.screen.measurement_duration else 0.0)
        self.screen.update_progress(progress * 100.0, measurement_status, remaining_time)
        self.screen.show_signal_info(signal_quality, detection_score, detection_amp, detection_ratio)

        hr_valid = bool(sensor_data.get("hr_valid"))
        spo2_valid = bool(sensor_data.get("spo2_valid"))
        heart_rate = float(sensor_data.get("heart_rate", 0.0) or 0.0)
        spo2 = float(sensor_data.get("spo2", 0.0) or 0.0)
        self.screen.update_live_metrics(heart_rate, hr_valid, spo2, spo2_valid, self.state)

        if self.state == self.STATE_WAITING:
            # Tính elapsed_wait nhưng chỉ hiển thị countdown, KHÔNG timeout khi không có ngón tay
            elapsed_wait = now - self.wait_started
            remaining_wait = max(0.0, self.WAIT_TIMEOUT - elapsed_wait)
            self.screen.show_waiting_instructions(remaining_wait)
            
            if finger_present:
                self.state = self.STATE_MEASURING
                self.measure_started = now
                self.finger_lost_ts = None
                self.screen.on_measurement_started(self.screen.measurement_duration)
                self.logger.info("Đã phát hiện ngón tay, chuyển sang trạng thái đo")
            # KHÔNG timeout trong WAITING - chờ vô hạn cho đến khi có ngón tay hoặc user cancel
            return True

        if self.state != self.STATE_MEASURING:
            return True

        # TRONG TRẠNG THÁI MEASURING: Tạm dừng đếm ngược nếu mất ngón tay
        if not finger_present:
            if self.finger_lost_ts is None:
                self.finger_lost_ts = now
                self.logger.debug("Ngón tay rời khỏi cảm biến - TẠM DỪNG đếm ngược")
            # DỪNG ĐẾM: measurement_elapsed không tăng khi mất ngón tay
            # Tính lại elapsed dựa trên thời gian CÓ ngón tay
            time_with_finger = (self.finger_lost_ts - self.measure_started) if self.measure_started else 0.0
            measurement_elapsed = time_with_finger
            remaining_time = max(0.0, self.screen.measurement_duration - measurement_elapsed)
            
            # Grace period: nếu mất ngón tay quá lâu → fail
            if now - self.finger_lost_ts > self.FINGER_LOSS_GRACE:
                self.logger.warning("Ngón tay rời khỏi cảm biến quá lâu")
                self._finalize(success=False, reason="finger_removed", snapshot=sensor_data)
                return False
            self.screen.show_finger_instruction(missing=True)
        else:
            # Có ngón tay: tiếp tục đếm bình thường
            if self.finger_lost_ts is not None:
                # Ngón tay vừa quay lại → điều chỉnh measure_started
                pause_duration = now - self.finger_lost_ts
                self.measure_started += pause_duration  # Dịch thời điểm bắt đầu về sau
                self.logger.debug("Ngón tay quay lại - TIẾP TỤC đếm (đã dừng %.1fs)", pause_duration)
                self.finger_lost_ts = None

        has_valid_metrics = (hr_valid and heart_rate > 0) or (spo2_valid and spo2 > 0)
        if measurement_elapsed >= self.screen.minimum_active_time and (measurement_ready or has_valid_metrics):
            self._finalize(success=True, reason="completed", snapshot=sensor_data)
            return False

        if now >= self.deadline:
            self.logger.warning(
                "Timeout đo nhịp tim (elapsed=%.1fs, chất lượng=%.1f)",
                measurement_elapsed,
                signal_quality,
            )
            self._finalize(success=False, reason="timeout", snapshot=sensor_data)
            return False

        if finger_present and measurement_status == "poor_signal":
            self.screen.show_signal_warning()
        elif finger_present:
            self.screen.show_measurement_guidance(remaining_time)

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

        hr_valid = bool(snapshot.get("hr_valid"))
        spo2_valid = bool(snapshot.get("spo2_valid"))
        heart_rate = float(snapshot.get("heart_rate", 0.0) or 0.0)
        spo2 = float(snapshot.get("spo2", 0.0) or 0.0)
        quality = float(snapshot.get("signal_quality_ir", 0.0) or 0.0)
        status = self._extract_status(snapshot)
        quality = float(status.get("signal_quality_ir", quality))

        self.screen.on_measurement_complete(
            success=success,
            reason=reason,
            heart_rate=heart_rate if hr_valid and heart_rate > 0 else 0.0,
            spo2=spo2 if spo2_valid and spo2 > 0 else 0.0,
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
    """Màn hình đo nhịp tim & SpO₂ với controller tách riêng."""

    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)

        sensor = getattr(self.app_instance, "sensors", {}).get("MAX30102") if hasattr(self.app_instance, "sensors") else None
        default_duration = 8.0
        if sensor and hasattr(sensor, "measurement_window_seconds"):
            try:
                default_duration = float(sensor.measurement_window_seconds)
            except (TypeError, ValueError):
                default_duration = 8.0

        self.measurement_duration = max(5.0, default_duration)
        self.minimum_active_time = max(4.0, self.measurement_duration * 0.5)  # Giảm từ 0.6 xuống 0.5

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
            text="NHỊP TIM & SpO₂",
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
        available_height = Window.height
        panel_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            height=min(dp(140), available_height * 0.42),
        )

        measurement_card = MDCard(
            orientation="vertical",
            size_hint_x=0.48,
            padding=(dp(12), dp(10), dp(12), dp(10)),
            spacing=dp(6),
            radius=[dp(18)],
            md_bg_color=MED_CARD_BG,
        )

        metrics_container = MDBoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint=(1, 1),
        )

        hr_section = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(56),
        )
        hr_icon = MDIcon(
            icon="heart-pulse",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(28), dp(28)),
        )
        hr_icon.icon_size = dp(24)
        hr_section.add_widget(hr_icon)

        hr_texts = MDBoxLayout(orientation="vertical", spacing=dp(2))
        hr_label = MDLabel(
            text="Nhịp tim",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        hr_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        hr_texts.add_widget(hr_label)

        self.hr_value_label = MDLabel(
            text="-- BPM",
            font_style="H5",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
        )
        self.hr_value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        hr_texts.add_widget(self.hr_value_label)
        hr_section.add_widget(hr_texts)
        metrics_container.add_widget(hr_section)

        spo2_section = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(56),
        )
        spo2_icon = MDIcon(
            icon="blood-bag",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(28), dp(28)),
        )
        spo2_icon.icon_size = dp(24)
        spo2_section.add_widget(spo2_icon)

        spo2_texts = MDBoxLayout(orientation="vertical", spacing=dp(2))
        spo2_label = MDLabel(
            text="SpO₂",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        spo2_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        spo2_texts.add_widget(spo2_label)

        self.spo2_value_label = MDLabel(
            text="-- %",
            font_style="H5",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
        )
        self.spo2_value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        spo2_texts.add_widget(self.spo2_value_label)
        spo2_section.add_widget(spo2_texts)
        metrics_container.add_widget(spo2_section)

        card_content = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint=(1, 1),
        )
        card_content.add_widget(metrics_container)

        pulse_wrapper = AnchorLayout(
            anchor_x="center",
            anchor_y="top",
            padding=(0, dp(6), 0, dp(10)),
            size_hint=(None, 1),
            width=dp(72),
        )
        self.pulse_widget = PulseAnimation()
        self.pulse_widget.size_hint = (None, None)
        self.pulse_widget.width = dp(58)
        self.pulse_widget.height = dp(58)
        pulse_wrapper.add_widget(self.pulse_widget)
        card_content.add_widget(pulse_wrapper)

        measurement_card.add_widget(card_content)
        panel_layout.add_widget(measurement_card)

        instruction_card = MDCard(
            orientation="vertical",
            size_hint_x=0.52,
            padding=(dp(12), dp(10), dp(12), dp(10)),
            spacing=dp(6),
            radius=[dp(18)],
            md_bg_color=MED_CARD_BG,
        )

        instruction_header = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(28),
        )
        instruction_icon = MDIcon(
            icon="fingerprint",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(24), dp(24)),
        )
        instruction_icon.icon_size = dp(20)
        instruction_header.add_widget(instruction_icon)

        header_label = MDLabel(
            text="Hướng dẫn nhanh",
            font_style="Subtitle2",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        header_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        instruction_header.add_widget(header_label)
        instruction_card.add_widget(instruction_header)

        self.instruction_label = MDLabel(
            text="1. Bấm 'Bắt đầu đo'\n2. Đặt ngón tay nhẹ nhàng lên cảm biến\n3. Giữ cố định đến khi hoàn tất",
            font_style="Body2",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="top",
        )
        self.instruction_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        instruction_card.add_widget(self.instruction_label)

        self.signal_label = MDLabel(
            text="Chất lượng tín hiệu: --",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
        )
        self.signal_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        instruction_card.add_widget(self.signal_label)

        panel_layout.add_widget(instruction_card)
        parent.add_widget(panel_layout)

    def _create_status_display(self, parent) -> None:
        status_card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(60),
            padding=(dp(12), dp(10), dp(12), dp(10)),
            spacing=dp(6),
            radius=[dp(18)],
            md_bg_color=MED_CARD_BG,
        )

        self.status_label = MDLabel(
            text="Sẵn sàng đo",
            font_style="Body1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
        )
        self.status_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        status_card.add_widget(self.status_label)

        self.progress_bar = MDProgressBar(
            max=100,
            value=0,
            color=MED_CARD_ACCENT,
            size_hint_y=None,
            height=dp(4),
        )
        status_card.add_widget(self.progress_bar)

        parent.add_widget(status_card)

    def _create_controls(self, parent) -> None:
        control_layout = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            spacing=dp(10),
        )

        self.start_stop_btn = MDRectangleFlatIconButton(
            text="Bắt đầu đo",
            icon="play-circle",
            text_color=MED_CARD_ACCENT,
            line_color=MED_CARD_ACCENT,
        )
        self.start_stop_btn.bind(on_press=self._on_start_stop_pressed)
        control_layout.add_widget(self.start_stop_btn)

        self.save_btn = MDRectangleFlatIconButton(
            text="Lưu kết quả",
            icon="content-save",
            disabled=True,
            text_color=(1, 1, 1, 0.3),
            line_color=(1, 1, 1, 0.3),
        )
        self.save_btn.bind(on_press=self._on_save_pressed)
        control_layout.add_widget(self.save_btn)

        parent.add_widget(control_layout)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _style_start_button(self, active: bool) -> None:
        if active:
            self.start_stop_btn.text = "Dừng đo"
            self.start_stop_btn.icon = "stop-circle"
            self.start_stop_btn.text_color = MED_WARNING
            self.start_stop_btn.line_color = MED_WARNING
        else:
            self.start_stop_btn.text = "Bắt đầu đo"
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

    def on_measurement_preparing(self, wait_timeout: float) -> None:
        self._style_start_button(True)
        self._style_save_button(False)
        self.progress_bar.value = 0
        self.hr_value_label.text = "-- BPM"
        self.spo2_value_label.text = "-- %"
        self.status_label.text = "Đang chuẩn bị cảm biến..."
        self.signal_label.text = "Chất lượng tín hiệu: --"
        self.instruction_label.text = (
            "• Đặt nhẹ ngón tay lên cảm biến trong %.0f giây\n"
            "• Giữ cố định, không bóp mạnh"
        ) % wait_timeout
        self.pulse_widget.start_pulse(60.0)

    def show_waiting_instructions(self, remaining_time: float) -> None:
        if remaining_time > 0:
            self.status_label.text = f"Chưa phát hiện ngón tay - còn {remaining_time:.0f}s"
        else:
            self.status_label.text = "Đang kiểm tra tín hiệu từ ngón tay..."

    def on_measurement_started(self, duration: float) -> None:
        self.status_label.text = f"Đang đo (~{duration:.0f}s) - giữ ngón tay thật cố định"
        self.instruction_label.text = (
            "• Giữ nguyên vị trí ngón tay\n"
            "• Tránh rung lắc và ánh sáng trực tiếp"
        )

    def show_finger_instruction(self, missing: bool) -> None:
        if missing:
            self.status_label.text = "Giữ ngón tay áp sát cảm biến"
        else:
            self.status_label.text = "Đang thu tín hiệu, tiếp tục giữ cố định"

    def show_measurement_guidance(self, remaining_time: float) -> None:
        self.status_label.text = f"Đang đo - còn khoảng {remaining_time:.1f}s"

    def show_signal_warning(self) -> None:
        self.status_label.text = "Tín hiệu yếu - hãy nhấn nhẹ hơn và giữ yên"

    def update_progress(self, percent: float, measurement_status: str, remaining_time: float) -> None:
        self.progress_bar.value = max(0.0, min(100.0, percent))
        if measurement_status == "partial":
            self.status_label.text = "Đang thu thêm tín hiệu để đảm bảo chính xác"
        elif measurement_status == "poor_signal":
            self.status_label.text = "Tín hiệu yếu - tránh rung lắc"
        elif measurement_status == "good" and remaining_time > 0:
            self.status_label.text = f"Tín hiệu ổn định - còn {remaining_time:.1f}s"

    def show_signal_info(self, quality: float, detection_score: float, amplitude: float, ratio: float) -> None:
        ratio_scaled = ratio * 10000.0
        self.signal_label.text = (
            f"Chất lượng tín hiệu: {quality:.0f}%\n"
            f"Điểm nhận diện: {detection_score:.2f} | Biên độ: {amplitude:.0f} | AC/DC×1e4: {ratio_scaled:.1f}"
        )

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

        if success and ((hr_valid and heart_rate > 0) or (spo2_valid and spo2 > 0)):
            self.current_hr = heart_rate if hr_valid and heart_rate > 0 else 0.0
            self.current_spo2 = spo2 if spo2_valid and spo2 > 0 else 0.0

            self.hr_value_label.text = f"{self.current_hr:.0f} BPM" if self.current_hr > 0 else "-- BPM"
            self.spo2_value_label.text = f"{self.current_spo2:.1f} %" if self.current_spo2 > 0 else "-- %"
            self.status_label.text = "Đã hoàn tất - nhấn 'Lưu kết quả' nếu cần"
            self.progress_bar.value = 100.0
            self._style_save_button(True)
            self.logger.info(
                "Đo nhịp tim thành công (HR=%.1f valid=%s, SpO₂=%.1f valid=%s)",
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
                "timeout": "Đo không thành công - tín hiệu chưa ổn định",
                "no_finger": "Không phát hiện ngón tay - vui lòng thử lại",
                "finger_removed": "Ngón tay bị rời khỏi cảm biến",
                "user_cancel": "Đã hủy phiên đo",
                "stopped": "Phiên đo đã dừng",
            }.get(reason, "Đo không thành công - thử lại sau")
            self.status_label.text = failure_reason
            if reason != "user_cancel" and previous_state == HeartRateMeasurementController.STATE_MEASURING:
                self.logger.warning(
                    "Measurement failed - hr_valid=%s spo2_valid=%s quality=%.1f reason=%s",
                    hr_valid,
                    spo2_valid,
                    signal_quality,
                    reason,
                )

        self.instruction_label.text = (
            "• Nhấn 'Bắt đầu đo' để thực hiện lại\n"
            "• Lau sạch cảm biến nếu tín hiệu yếu"
        )

    def reset_to_idle(self) -> None:
        self._style_start_button(False)
        self._style_save_button(False)
        self.progress_bar.value = 0
        self.hr_value_label.text = "-- BPM"
        self.spo2_value_label.text = "-- %"
        self.status_label.text = "Nhấn 'Bắt đầu đo' để khởi động"
        self.signal_label.text = "Chất lượng tín hiệu: --"
        self.instruction_label.text = (
            "1. Bấm 'Bắt đầu đo'\n"
            "2. Đặt ngón tay nhẹ nhàng lên cảm biến\n"
            "3. Giữ cố định đến khi hoàn tất"
        )
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
        try:
            self.app_instance.save_measurement_to_database(measurement_data)
            self.logger.info(
                "Đã lưu kết quả HR/SpO₂: HR=%.1f BPM, SpO₂=%.1f%%",
                self.current_hr,
                self.current_spo2,
            )
            self._style_save_button(False)
        except Exception as exc:  # pragma: no cover - safety log
            self.logger.error("Không thể lưu kết quả HR/SpO₂: %s", exc)

    # ------------------------------------------------------------------
    # Screen lifecycle
    # ------------------------------------------------------------------
    def on_enter(self) -> None:
        self.logger.info("Heart rate measurement screen entered")
        self.controller.reset()
        self.reset_to_idle()

    def on_leave(self) -> None:
        self.logger.info("Heart rate measurement screen left")
        self.controller.stop(user_cancelled=True)
        self.controller.reset()
        try:
            self.app_instance.stop_sensor("MAX30102")
        except Exception:
            pass
        self.pulse_widget.stop_pulse()