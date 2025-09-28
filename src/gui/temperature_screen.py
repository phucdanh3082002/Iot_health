"""
Temperature Measurement Screen
Màn hình đo chi tiết cho MLX90614 (nhiệt độ)
"""

from typing import Dict, Any, Optional
import logging
import time
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle, Ellipse
from kivy.animation import Animation


class TemperatureGauge(BoxLayout):
    """Widget hiển thị nhiệt độ dạng gauge"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self.current_temp = 36.0
        self.target_temp = 36.0
        
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
        import math
        angle_rad = math.radians(angle)
        radius = min(self.width, self.height) * 0.3
        
        x = self.center_x + radius * math.cos(angle_rad) - 5
        y = self.center_y + radius * math.sin(angle_rad) - 5
        
        self.temp_indicator.pos = (x, y)
    
    def update_temperature(self, temp: float):
        """Update displayed temperature"""
        self.target_temp = temp
        
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
        self.measurements = []
        self.stable_count = 0
        self.required_stable = 5
        
        # Current values
        self.current_temp = 0
        self.ambient_temp = 0
        
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
            self.measuring = True
            self.measurements.clear()
            self.stable_count = 0
            
            # Update UI
            self.start_stop_btn.text = 'Dừng đo'
            self.start_stop_btn.background_color = (1, 0.2, 0.2, 1)
            self.save_btn.disabled = True
            self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
            
            self.status_label.text = 'Đang đo... Giữ cảm biến ổn định'
            self.progress_bar.value = 0
            
            # Schedule updates
            Clock.schedule_interval(self._update_measurement, 0.5)
            
            self.logger.info("Temperature measurement started")
            
        except Exception as e:
            self.logger.error(f"Error starting measurement: {e}")
    
    def _stop_measurement(self):
        """Stop temperature measurement"""
        try:
            self.measuring = False
            
            # Update UI
            self.start_stop_btn.text = 'Bắt đầu đo'
            self.start_stop_btn.background_color = (0.8, 0.3, 0.3, 1)
            self.status_label.text = 'Đã dừng đo'
            self.progress_bar.value = 0
            
            # Stop updates
            Clock.unschedule(self._update_measurement)
            
            self.logger.info("Temperature measurement stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping measurement: {e}")
    
    def _update_measurement(self, dt):
        """Update measurement progress"""
        try:
            if not self.measuring:
                return False
            
            # Get current sensor data
            sensor_data = self.app_instance.get_sensor_data()
            mlx90614_status = sensor_data.get('sensor_status', {}).get('MLX90614', {})
            
            # Get temperature data following MLX90614 logic
            object_temp = sensor_data.get('temperature', 0)  # Primary temperature (object)
            ambient_temp = sensor_data.get('ambient_temperature', 0)
            temp_status = mlx90614_status.get('status', 'normal')
            measurement_type = mlx90614_status.get('measurement_type', 'object')
            
            # Validate temperature readings based on MLX90614 ranges
            if object_temp > 0 and -70 <= object_temp <= 380:
                # Update displays with current temperature
                self.current_temp = object_temp
                self.obj_temp_label.text = f"{object_temp:.1f}°C"
                self.temp_gauge.update_temperature(object_temp)
                
                # Update ambient temperature if available
                if ambient_temp > 0 and -40 <= ambient_temp <= 85:
                    self.ambient_temp = ambient_temp
                    self.amb_temp_label.text = f"{ambient_temp:.1f}°C"
                else:
                    self.amb_temp_label.text = "--°C"
                
                # Add to measurements list for stability checking
                self.measurements.append(object_temp)
                if len(self.measurements) > 10:
                    self.measurements.pop(0)
                
                # Check stability using MLX90614 smoothing criteria
                if len(self.measurements) >= 5:
                    recent_temps = self.measurements[-5:]
                    temp_std = sum([(t - sum(recent_temps)/len(recent_temps))**2 for t in recent_temps]) ** 0.5
                    temp_range = max(recent_temps) - min(recent_temps)
                    
                    # Consider stable if standard deviation < 0.15°C and range < 0.3°C
                    if temp_std < 0.15 and temp_range < 0.3:
                        self.stable_count += 1
                    else:
                        self.stable_count = max(0, self.stable_count - 1)
                    
                    # Update progress based on stability
                    progress = min((self.stable_count / self.required_stable) * 100, 100)
                    self.progress_bar.value = progress
                    
                    # Update status based on temperature status from MLX90614
                    if self.stable_count >= self.required_stable:
                        if temp_status == 'critical_low':
                            self.status_label.text = f'Hoàn thành - Nhiệt độ rất thấp ({object_temp:.1f}°C)'
                        elif temp_status == 'critical_high':
                            self.status_label.text = f'Hoàn thành - Sốt cao ({object_temp:.1f}°C)'
                        elif temp_status == 'high':
                            self.status_label.text = f'Hoàn thành - Hơi sốt ({object_temp:.1f}°C)'
                        elif temp_status == 'low':
                            self.status_label.text = f'Hoàn thành - Hơi thấp ({object_temp:.1f}°C)'
                        else:
                            self.status_label.text = f'Hoàn thành - Bình thường ({object_temp:.1f}°C)'
                        
                        self.save_btn.disabled = False
                        self.save_btn.background_color = (0.2, 0.6, 0.8, 1)
                        self._stop_measurement()
                    else:
                        stability_percent = (self.stable_count / self.required_stable) * 100
                        self.status_label.text = f'Đang ổn định... {stability_percent:.0f}%'
                else:
                    # Not enough measurements yet
                    self.status_label.text = 'Đang thu thập dữ liệu...'
                    self.progress_bar.value = len(self.measurements) * 10  # Show initial progress
                    
            else:
                # Invalid temperature reading
                if object_temp <= 0:
                    self.status_label.text = 'Không nhận được dữ liệu từ cảm biến'
                elif object_temp < -70:
                    self.status_label.text = 'Nhiệt độ quá thấp (< -70°C)'
                elif object_temp > 380:
                    self.status_label.text = 'Nhiệt độ quá cao (> 380°C)'
                else:
                    self.status_label.text = 'Dữ liệu không hợp lệ'
                    
                self.stable_count = 0
                self.progress_bar.value = 0
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating measurement: {e}")
            return False
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Temperature measurement screen entered")
        
        # Reset displays
        self.obj_temp_label.text = '--°C'
        self.amb_temp_label.text = '--°C'
        self.progress_bar.value = 0
        self.status_label.text = 'Sẵn sàng đo'
        self.temp_gauge.update_temperature(36.0)
        
        # Auto-start measurement when entering screen
        self._start_measurement()
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Temperature measurement screen left")
        
        # Stop any ongoing measurement
        if self.measuring:
            self._stop_measurement()