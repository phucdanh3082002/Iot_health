"""
Heart Rate & SpO2 Measurement Screen
Màn hình đo chi tiết cho MAX30102 (nhịp tim và SpO2)
"""

from typing import Dict, Any, Optional
import logging
import time
import numpy as np
from kivy.uix.screenmanager import Screen
from kivy.uix.anchorlayout import AnchorLayout
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.core.window import Window
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.button import MDRectangleFlatIconButton, MDIconButton
from kivymd.uix.progressbar import MDProgressBar


MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class PulseAnimation(MDBoxLayout):
    """Widget hiển thị animation nhịp tim"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = (0, dp(4), 0, dp(4))
        self.pulse_active = False
        self.pulse_rate = 60  # BPM
        self.base_font_size = dp(44)

        self.heart_icon = MDIcon(
            icon="heart",
            theme_text_color="Custom",
            text_color=(1, 0.36, 0.46, 1),
            halign="center",
        )
        self.heart_icon.font_size = self.base_font_size
        self.heart_icon.pos_hint = {"center_x": 0.5}
        self.add_widget(self.heart_icon)

    def start_pulse(self, bpm: float):
        """Start pulse animation"""
        if bpm <= 0:
            self.stop_pulse()
            return

        self.pulse_rate = bpm
        self.pulse_active = True
        Clock.unschedule(self._pulse_beat)
        interval = 60.0 / bpm
        self._schedule_pulse(interval)

    def stop_pulse(self):
        """Stop pulse animation"""
        self.pulse_active = False
        Clock.unschedule(self._pulse_beat)
        self.heart_icon.font_size = self.base_font_size

    def _schedule_pulse(self, interval):
        """Schedule pulse animation"""
        if self.pulse_active:
            Clock.schedule_once(self._pulse_beat, interval)

    def _pulse_beat(self, dt):
        """Animate one heartbeat"""
        if not self.pulse_active:
            return

        anim = (
            Animation(font_size=self.base_font_size + dp(8), duration=0.12)
            + Animation(font_size=self.base_font_size, duration=0.12)
        )
        anim.start(self.heart_icon)

        interval = 60.0 / self.pulse_rate if self.pulse_rate > 0 else 1.0
        self._schedule_pulse(interval)


class HeartRateScreen(Screen):
    """Màn hình đo chi tiết cho MAX30102"""

    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)

        # Measurement state
        self.measuring = False
        self.measurement_start_time = 0
        self.measurement_duration = 5.0  # 5 seconds measurement time
        self.stable_readings = 0
        self.required_stable_readings = 10

        # Current values
        self.current_hr = 0
        self.current_spo2 = 0

        # Finger detection gate
        self.awaiting_finger = False
        self.finger_wait_event = None
        self.finger_wait_start = 0.0
        self.finger_wait_timeout = 8.0  # seconds to wait for finger before aborting

        # Valid readings collection
        self.valid_hr_readings = []
        self.valid_spo2_readings = []
        self.max_valid_readings = 20  # Maximum readings to collect for filtering

        self._build_layout()

    def _build_layout(self):
        """Build measurement screen layout"""
        main_layout = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=(dp(8), dp(6), dp(8), dp(8)),
        )

        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)

        self._create_header(main_layout)
        self._create_measurement_panel(main_layout)
        self._create_status_display(main_layout)
        self._create_controls(main_layout)

        self.add_widget(main_layout)

    def _update_bg(self, instance, value):
        self.bg_rect.size = instance.size
        self.bg_rect.pos = instance.pos

    def _create_header(self, parent):
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
            text="Giữ ngón tay yên trên cảm biến",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
        )
        subtitle_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(subtitle_label)

        header_card.add_widget(title_box)

        parent.add_widget(header_card)

    def _create_measurement_panel(self, parent):
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
            text="1. Đặt ngón tay lên cảm biến\n2. Giữ yên trong 5 giây\n3. Hít thở đều, tránh rung lắc",
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

    def _create_status_display(self, parent):
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
            text='Sẵn sàng đo',
            font_style='Body1',
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
        )
        self.status_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
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

    def _create_controls(self, parent):
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

    def _style_start_button(self, active: bool) -> None:
        if active:
            self.start_stop_btn.text = 'Dừng đo'
            self.start_stop_btn.icon = 'stop-circle'
            self.start_stop_btn.text_color = MED_WARNING
            self.start_stop_btn.line_color = MED_WARNING
        else:
            self.start_stop_btn.text = 'Bắt đầu đo'
            self.start_stop_btn.icon = 'play-circle'
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

    def _prepare_measurement_session(self) -> None:
        """Reset dữ liệu và giao diện trước khi bắt đầu đo."""
        self.stable_readings = 0
        self.valid_hr_readings.clear()
        self.valid_spo2_readings.clear()
        self.current_hr = 0
        self.current_spo2 = 0
        self.progress_bar.value = 0
        self.signal_label.text = 'Chất lượng tín hiệu: --'
        self.hr_value_label.text = '-- BPM'
        self.spo2_value_label.text = '-- %'
        self._style_save_button(enabled=False)

    def _is_finger_detected(self, sensor_data: Dict[str, Any]) -> bool:
        """Trích xuất trạng thái phát hiện ngón tay từ dữ liệu cảm biến."""
        if not sensor_data:
            return False

        status_map = sensor_data.get('sensor_status') or {}
        max30102_status = status_map.get('MAX30102') or {}

        if 'finger_detected' in max30102_status:
            return bool(max30102_status.get('finger_detected'))

        if 'finger_detected' in sensor_data:
            return bool(sensor_data.get('finger_detected'))

        return False

    def _schedule_finger_wait(self) -> None:
        """Đăng ký vòng lặp kiểm tra ngón tay khi đang chờ."""
        if self.finger_wait_event is None:
            self.finger_wait_event = Clock.schedule_interval(self._check_finger_ready, 0.2)

    def _cancel_finger_wait(self) -> None:
        """Huỷ vòng lặp kiểm tra ngón tay nếu còn tồn tại."""
        if self.finger_wait_event is not None:
            try:
                self.finger_wait_event.cancel()
            except Exception:
                Clock.unschedule(self._check_finger_ready)
            self.finger_wait_event = None

    def _check_finger_ready(self, dt) -> bool:
        """Kiểm tra định kỳ xem ngón tay đã được đặt lên cảm biến chưa."""
        sensor_data = self.app_instance.get_sensor_data()
        if self._is_finger_detected(sensor_data):
            self.awaiting_finger = False
            self.status_label.text = 'Đã phát hiện ngón tay - bắt đầu đo'
            self._cancel_finger_wait()
            # Bắt đầu phiên đo chính thức
            self._begin_active_measurement()
            return False

        elapsed = time.time() - self.finger_wait_start
        remaining = max(0.0, self.finger_wait_timeout - elapsed)

        if elapsed >= self.finger_wait_timeout:
            self.status_label.text = 'Chưa phát hiện ngón tay - hãy đặt ngón tay và nhấn lại'
            self.logger.warning("Timeout chờ ngón tay - hủy phiên đo")
            self._cancel_finger_wait()
            self._style_start_button(active=False)
            self.pulse_widget.stop_pulse()
            self.app_instance.stop_sensor('MAX30102')
            self.awaiting_finger = False
            return False

        self.status_label.text = f'Chưa phát hiện ngón tay - đặt ngón tay lên cảm biến ({remaining:.0f}s)'
        return True

    def _begin_active_measurement(self) -> None:
        """Thiết lập trạng thái và UI khi chính thức bắt đầu đếm thời gian đo."""
        self.measuring = True
        self.measurement_start_time = time.time()
        self._style_start_button(active=True)
        self._style_save_button(enabled=False)
        self.status_label.text = 'Đang đo trong 5 giây... Đặt ngón tay yên cố định'
        self.progress_bar.value = 0
        self.signal_label.text = 'Chất lượng tín hiệu: --'
        self.hr_value_label.text = '-- BPM'
        self.spo2_value_label.text = '-- %'

        # Bật LED đỏ nếu có hỗ trợ
        if 'MAX30102' in self.app_instance.sensors:
            max30102_sensor = self.app_instance.sensors['MAX30102']
            if hasattr(max30102_sensor, 'turn_on_red_led'):
                max30102_sensor.turn_on_red_led()

        # Chạy animation với BPM mặc định trong khi chờ nhịp thật
        self._ensure_pulse_running(60)

        # Bắt đầu cập nhật dữ liệu
        Clock.schedule_interval(self._update_measurement, 0.2)

        self.logger.info("Heart rate measurement started - 5 second timer")

    def _ensure_pulse_running(self, bpm: float) -> None:
        """Đảm bảo animation trái tim chạy với BPM mong muốn trong khi đo."""
        if bpm <= 0:
            bpm = 60.0

        pulse_widget = self.pulse_widget
        if not pulse_widget.pulse_active:
            pulse_widget.start_pulse(bpm)
        elif abs(pulse_widget.pulse_rate - bpm) > 1:
            pulse_widget.start_pulse(bpm)
    
    def _on_back_pressed(self, instance):
        """Handle back button press"""
        if self.measuring:
            self._stop_measurement()
        self.app_instance.navigate_to_screen('dashboard')
    
    def _on_start_stop_pressed(self, instance):
        """Handle start/stop button press"""
        if self.measuring or self.awaiting_finger:
            self._stop_measurement()
        else:
            self._start_measurement()
    
    def _on_save_pressed(self, instance):
        """Handle save button press"""
        if self.current_hr > 0 and self.current_spo2 > 0:
            measurement_data = {
                'timestamp': time.time(),
                'heart_rate': self.current_hr,
                'spo2': self.current_spo2,
                'measurement_type': 'heart_rate_spo2'
            }
            self.app_instance.save_measurement_to_database(measurement_data)
            self.logger.info(f"Saved HR/SpO2 measurement: {self.current_hr}/{self.current_spo2}")
            
            # Reset for next measurement
            self._style_save_button(enabled=False)
    
    def _start_measurement(self):
        """Start measurement process"""
        try:
            if self.measuring or self.awaiting_finger:
                self.logger.debug("Measurement already in progress or waiting for finger")
                return

            if not self.app_instance.ensure_sensor_started('MAX30102'):
                self.status_label.text = 'Không thể khởi động cảm biến nhịp tim'
                self.logger.error("Failed to start MAX30102 sensor on demand")
                return

            # Reset session state trước khi bắt đầu hoặc chờ
            self._prepare_measurement_session()

            # Kiểm tra trạng thái ngón tay hiện tại
            sensor_data = self.app_instance.get_sensor_data()
            finger_detected = self._is_finger_detected(sensor_data)

            if finger_detected:
                self.status_label.text = 'Đã phát hiện ngón tay - bắt đầu đo'
                self._begin_active_measurement()
            else:
                self.awaiting_finger = True
                self.finger_wait_start = time.time()
                self.status_label.text = 'Chưa phát hiện ngón tay - đặt ngón tay lên cảm biến'
                self._style_start_button(active=True)
                self._ensure_pulse_running(60)
                self._schedule_finger_wait()
                self.logger.info("Đang chờ phát hiện ngón tay trước khi bắt đầu đo")
                
        except Exception as e:
            self.logger.error(f"Error starting measurement: {e}")
    
    def _stop_measurement(self):
        """Stop measurement process"""
        try:
            waiting_only = self.awaiting_finger and not self.measuring
            self.awaiting_finger = False
            self._cancel_finger_wait()

            if not self.measuring:
                if waiting_only:
                    self.logger.info("Huỷ đo khi chưa phát hiện ngón tay")
                else:
                    self.logger.debug("Stop measurement called when no active session")

                self._style_start_button(active=False)
                self.pulse_widget.stop_pulse()
                Clock.unschedule(self._update_measurement)
                self.status_label.text = 'Đã hủy - Đặt ngón tay lên cảm biến và thử lại'
                self.progress_bar.value = 0
                self.hr_value_label.text = '-- BPM'
                self.spo2_value_label.text = '-- %'
                self._style_save_button(enabled=False)
                return

            self.measuring = False

            # Turn off RED LED after measurement
            if 'MAX30102' in self.app_instance.sensors:
                max30102_sensor = self.app_instance.sensors['MAX30102']
                if hasattr(max30102_sensor, 'turn_off_red_led'):
                    max30102_sensor.turn_off_red_led()

            # Update UI
            self._style_start_button(active=False)

            # Stop animations
            self.pulse_widget.stop_pulse()
            Clock.unschedule(self._update_measurement)

            # Process collected readings and filter invalid values
            final_hr, final_spo2 = self._process_final_readings()

            if final_hr > 0 and final_spo2 > 0:
                self.current_hr = final_hr
                self.current_spo2 = final_spo2
                self.hr_value_label.text = f'{final_hr:.0f} BPM'
                self.spo2_value_label.text = f'{final_spo2:.0f} %'

                self.status_label.text = 'Đo hoàn thành - Có thể lưu kết quả!'
                self.progress_bar.value = 100
                self._style_save_button(enabled=True)

                self.logger.info(f"Measurement completed: HR={final_hr:.0f}, SpO2={final_spo2:.0f}")
            else:
                self.status_label.text = 'Đo không thành công - Thử lại'
                self.progress_bar.value = 0
                self.hr_value_label.text = '-- BPM'
                self.spo2_value_label.text = '-- %'
                self._style_save_button(enabled=False)
                self.logger.warning("Measurement failed - no valid readings")
            
        except Exception as e:
            self.logger.error(f"Error stopping measurement: {e}")
        finally:
            self.app_instance.stop_sensor('MAX30102')
    
    def _update_measurement(self, dt):
        """Update measurement progress with 5-second timer and data filtering"""
        try:
            if not self.measuring:
                return False
            
            # Calculate elapsed time
            elapsed_time = time.time() - self.measurement_start_time
            remaining_time = max(0, self.measurement_duration - elapsed_time)
            
            # Update progress bar based on time
            time_progress = min(100, (elapsed_time / self.measurement_duration) * 100)
            self.progress_bar.value = time_progress
            
            # Check if measurement time is up
            if elapsed_time >= self.measurement_duration:
                self._stop_measurement()
                return False
            
            # Get current sensor data from app
            sensor_data = self.app_instance.get_sensor_data()
            max30102_status = sensor_data.get('sensor_status', {}).get('MAX30102', {})
            
            # Get MAX30102 specific data
            finger_detected = max30102_status.get('finger_detected', False)
            hr_valid = sensor_data.get('hr_valid', False)
            spo2_valid = sensor_data.get('spo2_valid', False)
            signal_quality_ir = max30102_status.get('signal_quality_ir', 0)
            measurement_status = max30102_status.get('status', 'no_finger')
            
            # Update signal quality display
            self.signal_label.text = f'Chất lượng tín hiệu: {signal_quality_ir:.0f}%'
            
            # Update status with remaining time
            if measurement_status == 'no_finger':
                self.status_label.text = f'Đặt ngón tay lên cảm biến ({remaining_time:.1f}s)'
                self.hr_value_label.text = '-- BPM'
                self.spo2_value_label.text = '-- %'
                self._ensure_pulse_running(60)
                return True
            
            elif measurement_status == 'initializing':
                self.status_label.text = f'Đang khởi tạo... ({remaining_time:.1f}s)'
                self.hr_value_label.text = '-- BPM'
                self.spo2_value_label.text = '-- %'
                self._ensure_pulse_running(60)
                return True
            
            elif measurement_status == 'poor_signal':
                self.status_label.text = f'Tín hiệu yếu - Ấn chặt hơn ({remaining_time:.1f}s)'
                self.hr_value_label.text = '-- BPM'
                self.spo2_value_label.text = '-- %'
                self._ensure_pulse_running(60)
                return True
            
            # Get current HR and SpO2 values
            current_hr = sensor_data.get('heart_rate', 0)
            current_spo2 = sensor_data.get('spo2', 0)
            
            # Validate and collect readings using MAX30102 sensor validation
            max30102_sensor = self.app_instance.sensors.get('MAX30102')
            if max30102_sensor:
                # Use sensor's validation methods if available
                hr_is_valid = (hr_valid and 
                              hasattr(max30102_sensor, 'validate_heart_rate') and 
                              max30102_sensor.validate_heart_rate(current_hr))
                spo2_is_valid = (spo2_valid and 
                               hasattr(max30102_sensor, 'validate_spo2') and 
                               max30102_sensor.validate_spo2(current_spo2))
            else:
                # Fallback validation
                hr_is_valid = hr_valid and 40 <= current_hr <= 200 and current_hr != -999
                spo2_is_valid = spo2_valid and 70 <= current_spo2 <= 100 and current_spo2 != -999
            
            # Collect valid readings for filtering
            if hr_is_valid and len(self.valid_hr_readings) < self.max_valid_readings:
                self.valid_hr_readings.append(current_hr)
            
            if spo2_is_valid and len(self.valid_spo2_readings) < self.max_valid_readings:
                self.valid_spo2_readings.append(current_spo2)
            
            # Update displays with current values if valid
            if hr_is_valid:
                self.hr_value_label.text = f'{current_hr:.0f} BPM'
                self._ensure_pulse_running(current_hr)
            else:
                self.hr_value_label.text = '-- BPM'
                self._ensure_pulse_running(60)
            
            if spo2_is_valid:
                self.spo2_value_label.text = f'{current_spo2:.0f} %'
            else:
                self.spo2_value_label.text = '-- %'
            
            # Update status based on data collection progress
            valid_readings_count = len(self.valid_hr_readings) + len(self.valid_spo2_readings)
            data_progress = min(100, (valid_readings_count / (self.max_valid_readings * 2)) * 100)
            
            if measurement_status in ['good', 'partial']:
                self.status_label.text = f'Đang đo... {remaining_time:.1f}s (Dữ liệu: {data_progress:.0f}%)'
            else:
                self.status_label.text = f'Đang đo... {remaining_time:.1f}s - Giữ ngón tay yên'
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating heart rate measurement: {e}")
            return False
    
    def _process_final_readings(self):
        """
        Process and filter collected readings to get final values
        
        Returns:
            Tuple of (final_hr, final_spo2)
        """
        try:
            final_hr = 0
            final_spo2 = 0
            
            # Process HR readings
            if len(self.valid_hr_readings) >= 3:  # Need at least 3 valid readings
                # Remove outliers using interquartile range (IQR) method
                hr_array = np.array(self.valid_hr_readings)
                q1_hr = np.percentile(hr_array, 25)
                q3_hr = np.percentile(hr_array, 75)
                iqr_hr = q3_hr - q1_hr
                
                # Define outlier bounds
                lower_bound_hr = q1_hr - 1.5 * iqr_hr
                upper_bound_hr = q3_hr + 1.5 * iqr_hr
                
                # Filter outliers
                filtered_hr = hr_array[(hr_array >= lower_bound_hr) & (hr_array <= upper_bound_hr)]
                
                if len(filtered_hr) > 0:
                    # Use median of filtered values for stability
                    final_hr = np.median(filtered_hr)
                    self.logger.info(f"HR processing: {len(self.valid_hr_readings)} readings → {len(filtered_hr)} filtered → {final_hr:.1f}")
            
            # Process SpO2 readings
            if len(self.valid_spo2_readings) >= 3:  # Need at least 3 valid readings
                # Remove outliers using IQR method
                spo2_array = np.array(self.valid_spo2_readings)
                q1_spo2 = np.percentile(spo2_array, 25)
                q3_spo2 = np.percentile(spo2_array, 75)
                iqr_spo2 = q3_spo2 - q1_spo2
                
                # Define outlier bounds (tighter for SpO2 as it's more stable)
                lower_bound_spo2 = q1_spo2 - 1.0 * iqr_spo2
                upper_bound_spo2 = q3_spo2 + 1.0 * iqr_spo2
                
                # Filter outliers
                filtered_spo2 = spo2_array[(spo2_array >= lower_bound_spo2) & (spo2_array <= upper_bound_spo2)]
                
                if len(filtered_spo2) > 0:
                    # Use median of filtered values for stability
                    final_spo2 = np.median(filtered_spo2)
                    self.logger.info(f"SpO2 processing: {len(self.valid_spo2_readings)} readings → {len(filtered_spo2)} filtered → {final_spo2:.1f}")
            
            # Additional validation of final values
            if final_hr > 0 and not (40 <= final_hr <= 200):
                self.logger.warning(f"Final HR {final_hr} out of range, discarding")
                final_hr = 0
                
            if final_spo2 > 0 and not (70 <= final_spo2 <= 100):
                self.logger.warning(f"Final SpO2 {final_spo2} out of range, discarding")
                final_spo2 = 0
            
            return final_hr, final_spo2
            
        except Exception as e:
            self.logger.error(f"Error processing final readings: {e}")
            return 0, 0
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Heart rate measurement screen entered")
        
        # Reset values
        self.hr_value_label.text = '-- BPM'
        self.spo2_value_label.text = '-- %'
        self.progress_bar.value = 0
        self.status_label.text = 'Nhấn "Bắt đầu đo" để khởi động (5 giây)'
        self.signal_label.text = 'Chất lượng tín hiệu: --'
        self.pulse_widget.stop_pulse()
        self.awaiting_finger = False
        self._cancel_finger_wait()
        
        # Clear measurement data
        self.valid_hr_readings.clear()
        self.valid_spo2_readings.clear()
        self.current_hr = 0
        self.current_spo2 = 0
        self.stable_readings = 0
        self.measuring = False

        # Reset control buttons
        self._style_start_button(active=False)
        self._style_save_button(enabled=False)
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Heart rate measurement screen left")
        
        # Stop any ongoing measurement
        if self.measuring:
            self._stop_measurement()
        else:
            self.app_instance.stop_sensor('MAX30102')
            self.pulse_widget.stop_pulse()
            self.awaiting_finger = False
            self._cancel_finger_wait()