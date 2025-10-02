"""
Temperature Measurement Screen
Màn hình đo chi tiết cho MLX90614 (nhiệt độ)
"""
import logging
import statistics
import time
from kivy.uix.screenmanager import Screen
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.toolbar import MDTopAppBar

from src.utils.tts_manager import ScenarioID


MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class TemperatureScreen(Screen):
    """
    Màn hình đo chi tiết cho MLX90614
    """
    
    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # Measurement state
        self.measuring = False
        self.measurement_start_ts = None
        self.measurement_duration = 5.0  # seconds
        self.sample_interval = 0.2  # seconds between UI updates
        self.max_temp_deviation = 0.7  # °C, for outlier rejection
        self.samples = []

        # Current values
        self.current_temp = 0.0
        self.ambient_temp = 0.0
        
        self._build_layout()
    
    def _build_layout(self):
        """Build temperature measurement screen"""
        main_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(10),
            padding=(dp(12), dp(10), dp(12), dp(10)),
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
        """Create header"""
        toolbar = MDTopAppBar(
            title='NHIỆT ĐỘ CƠ THỂ',
            elevation=0,
            md_bg_color=MED_PRIMARY,
            specific_text_color=TEXT_PRIMARY,
            left_action_items=[["arrow-left", lambda _: self._on_back_pressed(None)]],
            size_hint_y=None,
            height=dp(42),
        )
        parent.add_widget(toolbar)

    def _create_measurement_panel(self, parent):
        """Create compact measurement + instructions row cho màn 3.5"""
        panel_layout = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(10),
            size_hint_y=None,
            height=dp(132),
        )

        measurement_card = MDCard(
            orientation='vertical',
            size_hint_x=0.48,
            padding=(dp(14), dp(12), dp(14), dp(12)),
            spacing=dp(6),
            radius=[dp(18)],
            md_bg_color=MED_CARD_BG,
        )

        header_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(28),
            spacing=dp(6),
        )
        measure_icon = MDIcon(
            icon='thermometer',
            theme_text_color='Custom',
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        measure_icon.icon_size = dp(20)
        header_layout.add_widget(measure_icon)

        title_label = MDLabel(
            text='Nhiệt độ cơ thể',
            font_style='Subtitle2',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
            halign='left',
            valign='middle',
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
        header_layout.add_widget(title_label)
        measurement_card.add_widget(header_layout)

        self.temp_value_label = MDLabel(
            text='--°C',
            font_style='H2',
            halign='center',
            valign='middle',
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
        )
        self.temp_value_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
        measurement_card.add_widget(self.temp_value_label)

        self.temp_state_label = MDLabel(
            text='Chờ đo',
            font_style='Caption',
            halign='center',
            valign='middle',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
        )
        self.temp_state_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
        measurement_card.add_widget(self.temp_state_label)

        panel_layout.add_widget(measurement_card)

        instruction_card = MDCard(
            orientation='vertical',
            size_hint_x=0.52,
            padding=(dp(14), dp(12), dp(14), dp(12)),
            spacing=dp(6),
            radius=[dp(18)],
            md_bg_color=MED_CARD_BG,
        )

        instruction_header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(28),
            spacing=dp(6),
        )
        instruction_icon = MDIcon(
            icon='clipboard-pulse-outline',
            theme_text_color='Custom',
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        instruction_icon.icon_size = dp(20)
        instruction_header.add_widget(instruction_icon)

        instruction_title = MDLabel(
            text='Hướng dẫn nhanh',
            font_style='Subtitle2',
            halign='left',
            valign='middle',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
        )
        instruction_title.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
        instruction_header.add_widget(instruction_title)
        instruction_card.add_widget(instruction_header)

        self.instruction_label = MDLabel(
            text='1. Đưa cảm biến cách trán 2-5cm\n2. Giữ tay chắc suốt 5 giây\n3. Tránh rung lắc, gió lạnh',
            font_style='Caption',
            halign='left',
            valign='top',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
        )
        self.instruction_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
        instruction_card.add_widget(self.instruction_label)

        panel_layout.add_widget(instruction_card)

        parent.add_widget(panel_layout)
    
    def _create_status_display(self, parent):
        """Create status and readings display"""
        status_card = MDCard(
            orientation='vertical',
            size_hint_y=None,
            height=dp(92),
            padding=(dp(14), dp(12), dp(14), dp(12)),
            spacing=dp(8),
            radius=[dp(18)],
            md_bg_color=MED_CARD_BG,
        )

        self.status_label = MDLabel(
            text='Sẵn sàng đo',
            font_style='Body2',
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
        )
        status_card.add_widget(self.status_label)

        readings_layout = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(16),
            size_hint_y=None,
            height=dp(40),
        )

        obj_temp_layout = MDBoxLayout(orientation='vertical', spacing=dp(2))
        obj_icon = MDIcon(
            icon='account-heart',
            theme_text_color='Custom',
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        obj_icon.icon_size = dp(20)
        obj_temp_layout.add_widget(obj_icon)
        obj_temp_title = MDLabel(
            text='Nhiệt độ cơ thể',
            font_style='Caption',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
        )
        self.obj_temp_label = MDLabel(
            text='--°C',
            font_style='Subtitle1',
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
        )
        obj_temp_layout.add_widget(obj_temp_title)
        obj_temp_layout.add_widget(self.obj_temp_label)
        readings_layout.add_widget(obj_temp_layout)

        amb_temp_layout = MDBoxLayout(orientation='vertical', spacing=dp(2))
        amb_icon = MDIcon(
            icon='home-thermometer',
            theme_text_color='Custom',
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        amb_icon.icon_size = dp(20)
        amb_temp_layout.add_widget(amb_icon)
        amb_temp_title = MDLabel(
            text='Nhiệt độ môi trường',
            font_style='Caption',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
        )
        self.amb_temp_label = MDLabel(
            text='--°C',
            font_style='Subtitle2',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
        )
        amb_temp_layout.add_widget(amb_temp_title)
        amb_temp_layout.add_widget(self.amb_temp_label)
        readings_layout.add_widget(amb_temp_layout)

        status_card.add_widget(readings_layout)

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
        """Create control buttons"""
        control_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(12),
        )

        self.start_stop_btn = MDRectangleFlatIconButton(
            text='Bắt đầu đo',
            icon='play-circle',
            text_color=MED_CARD_ACCENT,
            line_color=MED_CARD_ACCENT,
        )
        self.start_stop_btn.bind(on_press=self._on_start_stop_pressed)
        control_layout.add_widget(self.start_stop_btn)

        self.save_btn = MDRectangleFlatIconButton(
            text='Lưu kết quả',
            icon='content-save',
            disabled=True,
            text_color=(1, 1, 1, 0.3),
            line_color=(1, 1, 1, 0.3),
        )
        self.save_btn.bind(on_press=self._on_save_pressed)
        control_layout.add_widget(self.save_btn)

        parent.add_widget(control_layout)
    
    def _on_back_pressed(self, instance):
        """Handle back button"""
        if self.measuring:
            self._stop_measurement()
        self.app_instance.navigate_to_screen('dashboard')
    
    def _on_start_stop_pressed(self, instance):
        """Handle start/stop button"""
        if self.measuring:
            self._stop_measurement()
        else:
            self._start_measurement()
    
    def _on_save_pressed(self, instance):
        """Handle save button"""
        if self.current_temp > 0:
            measurement_data = {
                'timestamp': time.time(),
                'temperature': self.current_temp,
                'ambient_temperature': self.ambient_temp,
                'measurement_type': 'temperature'
            }
            self.app_instance.save_measurement_to_database(measurement_data)
            self.logger.info(f"Saved temperature measurement: {self.current_temp}°C")
            
            # Reset for next measurement
            self._style_save_button(enabled=False)

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
    
    def _start_measurement(self):
        """Start temperature measurement"""
        try:
            if not self.app_instance.ensure_sensor_started('MLX90614'):
                self.status_label.text = 'Không thể khởi động cảm biến nhiệt độ'
                self.logger.error("Failed to start MLX90614 sensor on demand")
                return

            self.measuring = True
            self.measurement_start_ts = time.time()
            self.samples.clear()
            self._display_object_temp(None)
            self._display_ambient_temp(None)
            self.temp_state_label.text = 'Đang đo trong 5 giây'
            
            # Update UI
            self._style_start_button(active=True)
            self._style_save_button(enabled=False)
            
            self.status_label.text = self._format_measurement_status(0.0)
            self.progress_bar.value = 0
            
            # Schedule updates
            Clock.schedule_interval(self._update_measurement, self.sample_interval)
            
            self._speak_temp_scenario(ScenarioID.TEMP_MEASURING)
            self.logger.info("Temperature measurement started")
            
        except Exception as e:
            self.logger.error(f"Error starting measurement: {e}")
            self.status_label.text = 'Lỗi khi khởi động đo nhiệt độ'
    
    def _stop_measurement(self, final_message: str | None = None, reset_progress: bool = True, keep_save_state: bool = False):
        """Stop temperature measurement"""
        try:
            if self.measuring:
                self.measuring = False
            
            # Update UI
            self._style_start_button(active=False)
            if reset_progress:
                self.progress_bar.value = 0

            if final_message:
                self.status_label.text = final_message
            elif reset_progress:
                self.status_label.text = 'Đã dừng đo'

            if not keep_save_state:
                self._style_save_button(enabled=False)
                self.temp_state_label.text = 'Chờ đo'
            elif final_message:
                self.temp_state_label.text = 'Sẵn sàng cho lần đo tiếp theo'
            
            # Stop updates
            Clock.unschedule(self._update_measurement)
            self.measurement_start_ts = None
            self.samples.clear()
            
            self.logger.info("Temperature measurement stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping measurement: {e}")
        finally:
            try:
                self.app_instance.stop_sensor('MLX90614')
            except Exception as sensor_error:
                self.logger.error(f"Error stopping MLX90614 sensor: {sensor_error}")
    
    def _update_measurement(self, dt):
        """Update measurement progress"""
        try:
            if not self.measuring or not self.measurement_start_ts:
                return False

            now = time.time()
            elapsed = max(0.0, now - self.measurement_start_ts)
            progress_ratio = min(elapsed / self.measurement_duration, 1.0)
            self.progress_bar.value = progress_ratio * 100
            elapsed_display = min(elapsed, self.measurement_duration)
            self.status_label.text = self._format_measurement_status(elapsed_display)
            
            # Get current sensor data
            sensor_data = self.app_instance.get_sensor_data()
            # Get temperature data following MLX90614 logic
            object_temp = sensor_data.get('temperature')
            ambient_temp = sensor_data.get('ambient_temperature')

            # Validate and collect samples
            if self._is_valid_object_temp(object_temp):
                if self._accept_sample(object_temp):
                    ambient_validated = self._validate_ambient_temp(ambient_temp)
                    sample = {
                        'timestamp': now,
                        'object': float(object_temp),
                        'ambient': ambient_validated,
                    }
                    self.samples.append(sample)

                    running_avg, running_ambient = self._compute_average()
                    if running_avg is not None:
                        self._display_object_temp(running_avg)

                    effective_ambient = running_ambient if running_ambient is not None else ambient_validated
                    self._display_ambient_temp(effective_ambient)
                else:
                    self.logger.debug(
                        "Rejected temperature sample %.2f°C as outlier (baseline %.2f°C)",
                        object_temp,
                        statistics.median([s['object'] for s in self.samples]) if self.samples else object_temp,
                    )
            else:
                self.status_label.text = f"{self._format_measurement_status(elapsed_display)} (giữ cảm biến ổn định)"

            # Finalise after duration window
            if elapsed >= self.measurement_duration:
                average_temp, average_ambient = self._compute_average()

                if average_temp is None:
                    self.logger.warning("Temperature measurement finished without valid samples")
                    self._stop_measurement(
                        final_message='Không đủ mẫu hợp lệ, vui lòng đo lại.',
                        reset_progress=True,
                        keep_save_state=False,
                    )
                    return False

                self._display_object_temp(average_temp)
                self._display_ambient_temp(average_ambient)

                scenario_id, result_message = self._determine_result_scenario(average_temp)
                self._style_save_button(enabled=True)
                self.progress_bar.value = 100
                self.logger.info(
                    "Temperature measurement completed with %d samples, average %.2f°C",
                    len(self.samples),
                    average_temp,
                )

                if scenario_id is not None:
                    self._speak_temp_scenario(scenario_id, temp=average_temp)

                self._stop_measurement(
                    final_message=result_message,
                    reset_progress=False,
                    keep_save_state=True,
                )
                self.temp_state_label.text = 'Đã hoàn tất'
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error updating measurement: {e}")
            self._stop_measurement(
                final_message='Xảy ra lỗi trong quá trình đo, vui lòng thử lại.',
                reset_progress=True,
                keep_save_state=False,
            )
            return False

    def _is_valid_object_temp(self, value: float | None) -> bool:
        if value is None:
            return False
        return value > 0 and -70 <= value <= 380

    def _validate_ambient_temp(self, value: float | None) -> float | None:
        if value is None:
            return None
        return float(value) if -40 <= value <= 85 else None

    def _accept_sample(self, temp_value: float) -> bool:
        if len(self.samples) < 3:
            return True
        baseline = statistics.median(sample['object'] for sample in self.samples)
        return abs(temp_value - baseline) <= self.max_temp_deviation

    def _compute_average(self) -> tuple[float | None, float | None]:
        if not self.samples:
            return None, None

        temps = [sample['object'] for sample in self.samples]
        median_temp = statistics.median(temps)
        filtered_temps = [temp for temp in temps if abs(temp - median_temp) <= self.max_temp_deviation]
        if not filtered_temps:
            filtered_temps = temps

        avg_temp = sum(filtered_temps) / len(filtered_temps)

        ambient_values = [sample['ambient'] for sample in self.samples if sample['ambient'] is not None]
        avg_ambient = None
        if ambient_values:
            median_ambient = statistics.median(ambient_values)
            filtered_ambient = [val for val in ambient_values if abs(val - median_ambient) <= 1.5]
            if not filtered_ambient:
                filtered_ambient = ambient_values
            avg_ambient = sum(filtered_ambient) / len(filtered_ambient)

        return avg_temp, avg_ambient

    def _determine_result_scenario(self, avg_temp: float) -> tuple[ScenarioID | None, str]:
        if avg_temp < 35.0:
            return (
                ScenarioID.TEMP_RESULT_CRITICAL_LOW,
                f'Hoàn thành - Nhiệt độ rất thấp ({avg_temp:.1f}°C)',
            )
        if avg_temp < 36.0:
            return (
                ScenarioID.TEMP_RESULT_LOW,
                f'Hoàn thành - Nhiệt độ hơi thấp ({avg_temp:.1f}°C)',
            )
        if avg_temp <= 37.5:
            return (
                ScenarioID.TEMP_RESULT_NORMAL,
                f'Hoàn thành - Nhiệt độ bình thường ({avg_temp:.1f}°C)',
            )
        if avg_temp <= 38.5:
            return (
                ScenarioID.TEMP_RESULT_FEVER,
                f'Hoàn thành - Cảnh báo sốt nhẹ ({avg_temp:.1f}°C)',
            )
        if avg_temp <= 40.0:
            return (
                ScenarioID.TEMP_RESULT_HIGH_FEVER,
                f'Hoàn thành - Cảnh báo sốt cao ({avg_temp:.1f}°C)',
            )
        return (
            ScenarioID.TEMP_RESULT_CRITICAL_HIGH,
            f'Hoàn thành - Nguy hiểm: sốt rất cao ({avg_temp:.1f}°C)',
        )

    def _speak_temp_scenario(self, scenario_id: ScenarioID, **kwargs) -> None:
        if not scenario_id:
            return

        speak_fn = getattr(self.app_instance, '_speak_scenario', None)
        if callable(speak_fn):
            try:
                speak_fn(scenario_id, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive logging
                self.logger.error("Không thể phát TTS cho kịch bản %s: %s", scenario_id, exc)

    def _format_measurement_status(self, elapsed_seconds: float) -> str:
        elapsed_clamped = max(0.0, min(elapsed_seconds, self.measurement_duration))
        return f'Đang đo... {elapsed_clamped:.1f}/{self.measurement_duration:.1f}s'

    def _display_object_temp(self, value: float | None) -> None:
        if value is None:
            self.current_temp = 0.0
            self.obj_temp_label.text = '--°C'
            self.temp_value_label.text = '--°C'
            self.temp_value_label.text_color = TEXT_PRIMARY
            return

        self.current_temp = value
        self.obj_temp_label.text = f"{value:.1f}°C"
        self.temp_value_label.text = f"{value:.1f}°C"
        self.temp_value_label.text_color = self._get_temp_color(value)

    def _display_ambient_temp(self, value: float | None) -> None:
        if value is None:
            self.ambient_temp = 0.0
            self.amb_temp_label.text = '--°C'
            return

        self.ambient_temp = value
        self.amb_temp_label.text = f"{value:.1f}°C"

    def _get_temp_color(self, value: float) -> tuple[float, float, float, float]:
        if value < 35.0:
            return (0.2, 0.4, 0.9, 1)
        if value < 36.0:
            return (0.2, 0.55, 0.95, 1)
        if value <= 37.5:
            return (0.0, 0.72, 0.58, 1)
        if value <= 38.5:
            return (0.95, 0.6, 0.2, 1)
        return (0.94, 0.28, 0.28, 1)
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Temperature measurement screen entered")
        
        # Reset displays
        self._display_object_temp(None)
        self._display_ambient_temp(None)
        self.progress_bar.value = 0
        self.status_label.text = 'Nhấn "Bắt đầu đo" để khởi động'
        self.temp_state_label.text = 'Chờ đo'
        self.measuring = False
        self.measurement_start_ts = None
        self.samples.clear()

        # Reset control buttons
        self._style_start_button(active=False)
        self._style_save_button(enabled=False)
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Temperature measurement screen left")
        
        # Stop any ongoing measurement
        if self.measuring:
            self._stop_measurement()
        else:
            self.measurement_start_ts = None
            self.samples.clear()
            self._style_start_button(active=False)
            self._style_save_button(enabled=False)