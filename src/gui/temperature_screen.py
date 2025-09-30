"""
Temperature Measurement Screen
Màn hình đo chi tiết cho MLX90614 (nhiệt độ)
"""

import logging
import math
import statistics
import time
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle, Ellipse
from kivy.animation import Animation

from src.utils.tts_manager import ScenarioID


class TemperatureGauge(BoxLayout):
    """Widget hiển thị nhiệt độ dạng gauge"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self.current_temp = 36.0
        
        # Temperature display
        self.temp_label = Label(
            text='36.0°C',
            font_size='48sp',
            bold=True,
            color=(0, 0, 0, 1)  # Black text for better visibility
        )
        self.add_widget(self.temp_label)
        
        # Background gauge
        with self.canvas.before:
            # Cold zone (blue)
            Color(0.2, 0.4, 1, 0.3)
            self.cold_arc = Ellipse(size=(150, 150), pos=(50, 50))
            
            # Normal zone (green)
            Color(0.2, 0.8, 0.2, 0.3)
            self.normal_arc = Ellipse(size=(150, 150), pos=(50, 50))
            
            # Hot zone (red)
            Color(1, 0.3, 0.3, 0.3)
            self.hot_arc = Ellipse(size=(150, 150), pos=(50, 50))
            
            # Current temperature indicator
            Color(1, 1, 1, 1)
            self.temp_indicator = Ellipse(size=(10, 10), pos=(120, 120))
        
        self.bind(size=self._update_gauge, pos=self._update_gauge)
    
    def _update_gauge(self, instance, value):
        """Update gauge graphics"""
        center_x = self.center_x
        center_y = self.center_y
        radius = min(self.width, self.height) * 0.4
        
        # Update arcs
        self.cold_arc.pos = (center_x - radius, center_y - radius)
        self.cold_arc.size = (radius * 2, radius * 2)
        
        self.normal_arc.pos = (center_x - radius, center_y - radius)
        self.normal_arc.size = (radius * 2, radius * 2)
        
        self.hot_arc.pos = (center_x - radius, center_y - radius)
        self.hot_arc.size = (radius * 2, radius * 2)
        
        # Update temperature indicator position
        self._update_temp_indicator()
    
    def _update_temp_indicator(self):
        """Update temperature indicator position"""
        # Map temperature to angle (30°C = bottom, 42°C = top)
        temp_range = (30, 42)
        angle_range = (-90, 90)  # degrees
        
        temp_normalized = (self.current_temp - temp_range[0]) / (temp_range[1] - temp_range[0])
        temp_normalized = max(0, min(1, temp_normalized))
        
        angle = angle_range[0] + temp_normalized * (angle_range[1] - angle_range[0])
        
        # Convert to radians and calculate position
        angle_rad = math.radians(angle)
        radius = min(self.width, self.height) * 0.3
        
        x = self.center_x + radius * math.cos(angle_rad) - 5
        y = self.center_y + radius * math.sin(angle_rad) - 5
        
        self.temp_indicator.pos = (x, y)
    
    def update_temperature(self, temp: float):
        """Update displayed temperature"""
        # Animate temperature change
        anim = Animation(current_temp=temp, duration=0.5)
        anim.bind(on_progress=self._animate_temp)
        anim.start(self)
    
    def _animate_temp(self, animation, widget, progress):
        """Animate temperature value"""
        self.temp_label.text = f"{self.current_temp:.1f}°C"
        self._update_temp_indicator()
        
        # Update color based on temperature with better contrast
        if self.current_temp < 35.0:
            self.temp_label.color = (0.2, 0.2, 0.8, 1)  # Dark blue (low)
        elif self.current_temp < 36.0:
            self.temp_label.color = (0.2, 0.4, 0.8, 1)  # Blue
        elif self.current_temp <= 37.5:
            self.temp_label.color = (0.1, 0.6, 0.1, 1)  # Dark green (normal)
        elif self.current_temp <= 38.5:
            self.temp_label.color = (0.8, 0.4, 0, 1)     # Dark orange (fever)
        else:
            self.temp_label.color = (0.8, 0.1, 0.1, 1)   # Dark red (high fever)


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
        # Main container
        main_layout = BoxLayout(orientation='vertical', spacing=15, padding=20)
        
        # Background
        with main_layout.canvas.before:
            Color(0.1, 0.05, 0.05, 1)  # Dark red background
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)
        
        # Header
        self._create_header(main_layout)
        
        # Instructions
        self._create_instructions(main_layout)
        
        # Temperature gauge
        self._create_temperature_display(main_layout)
        
        # Status and readings
        self._create_status_display(main_layout)
        
        # Controls
        self._create_controls(main_layout)
        
        self.add_widget(main_layout)
    
    def _update_bg(self, instance, value):
        self.bg_rect.size = instance.size
        self.bg_rect.pos = instance.pos
    
    def _create_header(self, parent):
        """Create header"""
        header = BoxLayout(orientation='horizontal', size_hint_y=0.08, spacing=10)
        
        # Back button
        back_btn = Button(
            text='← Dashboard',
            font_size='14sp',
            size_hint_x=0.25,
            background_color=(0.4, 0.4, 0.4, 1)
        )
        back_btn.bind(on_press=self._on_back_pressed)
        header.add_widget(back_btn)
        
        # Title
        title = Label(
            text='NHIỆT ĐỘ CƠ THỂ',
            font_size='20sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_x=0.75
        )
        header.add_widget(title)
        
        parent.add_widget(header)
    
    def _create_instructions(self, parent):
        """Create instructions panel"""
        instruction_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.12,
            spacing=5
        )
        
        # Background
        with instruction_container.canvas.before:
            Color(0.3, 0.1, 0.1, 0.3)
            self.instruction_rect = RoundedRectangle(
                size=instruction_container.size,
                pos=instruction_container.pos,
                radius=[10]
            )
        instruction_container.bind(
            size=self._update_instruction_rect,
            pos=self._update_instruction_rect
        )
        
        # Instructions
        self.instruction_label = Label(
            text='Đưa cảm biến gần trán (2-5cm)\\nGiữ ổn định trong vài giây\\nTránh di chuyển khi đo',
            font_size='12sp',
            color=(0.9, 0.9, 0.9, 1),
            halign='center'
        )
        self.instruction_label.bind(size=self.instruction_label.setter('text_size'))
        instruction_container.add_widget(self.instruction_label)
        
        parent.add_widget(instruction_container)
    
    def _update_instruction_rect(self, instance, value):
        self.instruction_rect.pos = instance.pos
        self.instruction_rect.size = instance.size
    
    def _create_temperature_display(self, parent):
        """Create temperature gauge display"""
        temp_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.45,
            spacing=10
        )
        
        # Temperature gauge
        self.temp_gauge = TemperatureGauge(size_hint_y=0.8)
        temp_container.add_widget(self.temp_gauge)
        
        # Temperature range indicator
        range_layout = BoxLayout(orientation='horizontal', size_hint_y=0.2)
        
        # Normal range
        range_label = Label(
            text='Bình thường: 36.0 - 37.5°C',
            font_size='12sp',
            color=(0.2, 0.8, 0.2, 1)
        )
        range_layout.add_widget(range_label)
        
        temp_container.add_widget(range_layout)
        
        parent.add_widget(temp_container)
    
    def _create_status_display(self, parent):
        """Create status and readings display"""
        status_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.25,
            spacing=10
        )
        
        # Status label
        self.status_label = Label(
            text='Sẵn sàng đo',
            font_size='16sp',
            color=(1, 1, 1, 1)
        )
        status_container.add_widget(self.status_label)
        
        # Readings info
        readings_layout = BoxLayout(orientation='horizontal', spacing=20)
        
        # Object temperature
        obj_temp_layout = BoxLayout(orientation='vertical')
        obj_temp_title = Label(
            text='Nhiệt độ cơ thể',
            font_size='12sp',
            size_hint_y=0.4,
            color=(0.8, 0.8, 0.8, 1)
        )
        self.obj_temp_label = Label(
            text='--°C',
            font_size='18sp',
            bold=True,
            size_hint_y=0.6,
            color=(1, 1, 1, 1)
        )
        obj_temp_layout.add_widget(obj_temp_title)
        obj_temp_layout.add_widget(self.obj_temp_label)
        readings_layout.add_widget(obj_temp_layout)
        
        # Ambient temperature
        amb_temp_layout = BoxLayout(orientation='vertical')
        amb_temp_title = Label(
            text='Nhiệt độ môi trường',
            font_size='12sp',
            size_hint_y=0.4,
            color=(0.8, 0.8, 0.8, 1)
        )
        self.amb_temp_label = Label(
            text='--°C',
            font_size='18sp',
            size_hint_y=0.6,
            color=(0.7, 0.7, 0.7, 1)
        )
        amb_temp_layout.add_widget(amb_temp_title)
        amb_temp_layout.add_widget(self.amb_temp_label)
        readings_layout.add_widget(amb_temp_layout)
        
        status_container.add_widget(readings_layout)
        
        # Progress bar
        self.progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=0.2
        )
        status_container.add_widget(self.progress_bar)
        
        parent.add_widget(status_container)
    
    def _create_controls(self, parent):
        """Create control buttons"""
        control_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=0.1,
            spacing=15
        )
        
        # Start/Stop button
        self.start_stop_btn = Button(
            text='Bắt đầu đo',
            font_size='16sp',
            background_color=(0.8, 0.3, 0.3, 1)  # Red theme
        )
        self.start_stop_btn.bind(on_press=self._on_start_stop_pressed)
        control_layout.add_widget(self.start_stop_btn)
        
        # Save button
        self.save_btn = Button(
            text='Lưu kết quả',
            font_size='16sp',
            background_color=(0.2, 0.6, 0.8, 1),
            disabled=True
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
            self.save_btn.disabled = True
            self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
    
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
            self.current_temp = 0.0
            self.ambient_temp = 0.0
            
            # Update UI
            self.start_stop_btn.text = 'Dừng đo'
            self.start_stop_btn.background_color = (1, 0.2, 0.2, 1)
            self.save_btn.disabled = True
            self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
            
            self.status_label.text = f'Đang đo... 0.0/{self.measurement_duration:.1f}s'
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
            self.start_stop_btn.text = 'Bắt đầu đo'
            self.start_stop_btn.background_color = (0.8, 0.3, 0.3, 1)
            if reset_progress:
                self.progress_bar.value = 0

            if final_message:
                self.status_label.text = final_message
            elif reset_progress:
                self.status_label.text = 'Đã dừng đo'

            if not keep_save_state:
                self.save_btn.disabled = True
                self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
            
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
            self.status_label.text = f'Đang đo... {elapsed_display:.1f}/{self.measurement_duration:.1f}s'
            
            # Get current sensor data
            sensor_data = self.app_instance.get_sensor_data()
            mlx90614_status = sensor_data.get('sensor_status', {}).get('MLX90614', {})
            
            # Get temperature data following MLX90614 logic
            object_temp = sensor_data.get('temperature')
            ambient_temp = sensor_data.get('ambient_temperature')

            # Validate and collect samples
            if self._is_valid_object_temp(object_temp):
                if self._accept_sample(object_temp):
                    sample = {
                        'timestamp': now,
                        'object': float(object_temp),
                        'ambient': self._validate_ambient_temp(ambient_temp),
                    }
                    self.samples.append(sample)

                    running_avg, running_ambient = self._compute_average()
                    if running_avg is not None:
                        self.current_temp = running_avg
                        self.obj_temp_label.text = f"{running_avg:.1f}°C"
                        self.temp_gauge.update_temperature(running_avg)
                    if running_ambient is not None:
                        self.ambient_temp = running_ambient
                        self.amb_temp_label.text = f"{running_ambient:.1f}°C"
                    elif ambient_temp is not None:
                        self.amb_temp_label.text = '--°C'
                else:
                    self.logger.debug(
                        "Rejected temperature sample %.2f°C as outlier (baseline %.2f°C)",
                        object_temp,
                        statistics.median([s['object'] for s in self.samples]) if self.samples else object_temp,
                    )
            else:
                self.status_label.text = (
                    f'Đang đo... {elapsed_display:.1f}/{self.measurement_duration:.1f}s '
                    '(giữ cảm biến ổn định)'
                )

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

                self.current_temp = average_temp
                self.obj_temp_label.text = f"{average_temp:.1f}°C"
                self.temp_gauge.update_temperature(average_temp)

                if average_ambient is not None:
                    self.ambient_temp = average_ambient
                    self.amb_temp_label.text = f"{average_ambient:.1f}°C"
                elif ambient_temp is not None:
                    self.amb_temp_label.text = '--°C'

                scenario_id, result_message = self._determine_result_scenario(average_temp)
                self.save_btn.disabled = False
                self.save_btn.background_color = (0.2, 0.6, 0.8, 1)
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
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Temperature measurement screen entered")
        
        # Reset displays
        self.obj_temp_label.text = '--°C'
        self.amb_temp_label.text = '--°C'
        self.progress_bar.value = 0
        self.status_label.text = 'Nhấn "Bắt đầu đo" để khởi động'
        self.temp_gauge.update_temperature(36.0)
        self.measuring = False
        self.measurement_start_ts = None
        self.samples.clear()

        # Reset control buttons
        self.start_stop_btn.text = 'Bắt đầu đo'
        self.start_stop_btn.background_color = (0.8, 0.3, 0.3, 1)
        self.save_btn.disabled = True
        self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Temperature measurement screen left")
        
        # Stop any ongoing measurement
        if self.measuring:
            self._stop_measurement()
        else:
            self.measurement_start_ts = None
            self.samples.clear()