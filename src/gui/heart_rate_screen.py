"""
Heart Rate & SpO2 Measurement Screen
Màn hình đo chi tiết cho MAX30102 (nhịp tim và SpO2)
"""

from typing import Dict, Any, Optional
import logging
import time
import numpy as np
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.animation import Animation


class PulseAnimation(BoxLayout):
    """Widget hiển thị animation nhịp tim"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        self.pulse_active = False
        self.pulse_rate = 60  # BPM
        
        # Heart icon
        self.heart_label = Label(
            text='💓',
            font_size='48sp',
            color=(1, 0.2, 0.2, 1)
        )
        self.add_widget(self.heart_label)
    
    def start_pulse(self, bpm: float):
        """Start pulse animation"""
        self.pulse_rate = bpm
        self.pulse_active = True
        
        if bpm > 0:
            interval = 60.0 / bpm  # seconds per beat
            self._schedule_pulse(interval)
    
    def stop_pulse(self):
        """Stop pulse animation"""
        self.pulse_active = False
        Clock.unschedule(self._pulse_beat)
    
    def _schedule_pulse(self, interval):
        """Schedule pulse animation"""
        if self.pulse_active:
            Clock.schedule_once(self._pulse_beat, interval)
    
    def _pulse_beat(self, dt):
        """Animate one heartbeat"""
        if not self.pulse_active:
            return
            
        # Scale animation
        anim = Animation(size_hint=(1.2, 1.2), duration=0.1) + \
               Animation(size_hint=(1.0, 1.0), duration=0.1)
        anim.start(self.heart_label)
        
        # Schedule next beat
        interval = 60.0 / self.pulse_rate if self.pulse_rate > 0 else 1.0
        self._schedule_pulse(interval)


class HeartRateScreen(Screen):
    """
    Màn hình đo chi tiết cho MAX30102
    """
    
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
        self.signal_quality = 0
        
        # Valid readings collection
        self.valid_hr_readings = []
        self.valid_spo2_readings = []
        self.max_valid_readings = 20  # Maximum readings to collect for filtering
        
        self._build_layout()
    
    def _build_layout(self):
        """Build measurement screen layout"""
        # Main container
        main_layout = BoxLayout(orientation='vertical', spacing=15, padding=20)
        
        # Background
        with main_layout.canvas.before:
            Color(0.05, 0.05, 0.1, 1)
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)
        
        # Header
        self._create_header(main_layout)
        
        # Instruction panel
        self._create_instructions(main_layout)
        
        # Pulse animation
        self._create_pulse_display(main_layout)
        
        # Values display
        self._create_values_display(main_layout)
        
        # Progress and status
        self._create_progress_display(main_layout)
        
        # Control buttons
        self._create_controls(main_layout)
        
        self.add_widget(main_layout)
    
    def _update_bg(self, instance, value):
        self.bg_rect.size = instance.size
        self.bg_rect.pos = instance.pos
    
    def _create_header(self, parent):
        """Create header with title and back button"""
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
            text='NHỊP TIM & SpO2',
            font_size='20sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_x=0.75
        )
        header.add_widget(title)
        
        parent.add_widget(header)
    
    def _create_instructions(self, parent):
        """Create instruction panel"""
        instruction_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.15,
            spacing=5
        )
        
        # Background
        with instruction_container.canvas.before:
            Color(0.1, 0.3, 0.1, 0.3)
            self.instruction_rect = RoundedRectangle(
                size=instruction_container.size,
                pos=instruction_container.pos,
                radius=[10]
            )
        instruction_container.bind(
            size=self._update_instruction_rect,
            pos=self._update_instruction_rect
        )
        
        # Instruction text
        self.instruction_label = Label(
            text='Đặt ngón tay lên cảm biến\\nGiữ yên trong 5 giây\\nKhông cử động và thở đều',
            font_size='14sp',
            color=(0.9, 0.9, 0.9, 1),
            halign='center'
        )
        self.instruction_label.bind(size=self.instruction_label.setter('text_size'))
        instruction_container.add_widget(self.instruction_label)
        
        parent.add_widget(instruction_container)
    
    def _update_instruction_rect(self, instance, value):
        self.instruction_rect.pos = instance.pos
        self.instruction_rect.size = instance.size
    
    def _create_pulse_display(self, parent):
        """Create pulse animation display"""
        pulse_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.25,
            spacing=10
        )
        
        # Pulse animation
        self.pulse_widget = PulseAnimation(size_hint_y=0.7)
        pulse_container.add_widget(self.pulse_widget)
        
        # Signal quality indicator
        self.signal_label = Label(
            text='Chất lượng tín hiệu: --',
            font_size='12sp',
            size_hint_y=0.3,
            color=(0.7, 0.7, 0.7, 1)
        )
        pulse_container.add_widget(self.signal_label)
        
        parent.add_widget(pulse_container)
    
    def _create_values_display(self, parent):
        """Create values display section"""
        values_container = BoxLayout(
            orientation='horizontal',
            size_hint_y=0.3,
            spacing=20
        )
        
        # Heart Rate display
        hr_container = self._create_value_card('NHỊP TIM', '--', 'bpm', (1, 0.3, 0.3, 1))
        values_container.add_widget(hr_container)
        
        # SpO2 display
        spo2_container = self._create_value_card('SpO2', '--', '%', (0.3, 0.6, 1, 1))
        values_container.add_widget(spo2_container)
        
        parent.add_widget(values_container)
    
    def _create_value_card(self, title: str, value: str, unit: str, color: tuple):
        """Create a value display card"""
        card = BoxLayout(orientation='vertical', spacing=5)
        
        # Background
        with card.canvas.before:
            Color(*color, 0.2)
            card_rect = RoundedRectangle(
                size=card.size,
                pos=card.pos,
                radius=[15]
            )
        card.bind(size=lambda i, v, r=card_rect: setattr(r, 'size', v))
        card.bind(pos=lambda i, v, r=card_rect: setattr(r, 'pos', v))
        
        # Title
        title_label = Label(
            text=title,
            font_size='14sp',
            bold=True,
            size_hint_y=0.3,
            color=color
        )
        card.add_widget(title_label)
        
        # Value
        value_label = Label(
            text=value,
            font_size='36sp',
            bold=True,
            size_hint_y=0.5,
            color=(0, 0, 0, 1)  # Black text for better contrast
        )
        
        # Store reference for updates
        if title == 'NHỊP TIM':
            self.hr_value_label = value_label
        elif title == 'SpO2':
            self.spo2_value_label = value_label
            
        card.add_widget(value_label)
        
        # Unit
        unit_label = Label(
            text=unit,
            font_size='12sp',
            size_hint_y=0.2,
            color=(0.8, 0.8, 0.8, 1)
        )
        card.add_widget(unit_label)
        
        return card
    
    def _create_progress_display(self, parent):
        """Create progress display"""
        progress_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.12,
            spacing=5
        )
        
        # Status label
        self.status_label = Label(
            text='Sẵn sàng đo',
            font_size='14sp',
            color=(1, 1, 1, 1)
        )
        progress_container.add_widget(self.status_label)
        
        # Progress bar
        self.progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=0.4
        )
        progress_container.add_widget(self.progress_bar)
        
        parent.add_widget(progress_container)
    
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
            background_color=(0.2, 0.8, 0.2, 1)
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
        """Handle back button press"""
        if self.measuring:
            self._stop_measurement()
        self.app_instance.navigate_to_screen('dashboard')
    
    def _on_start_stop_pressed(self, instance):
        """Handle start/stop button press"""
        if self.measuring:
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
            self.save_btn.disabled = True
            self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
    
    def _start_measurement(self):
        """Start measurement process"""
        try:
            if not self.app_instance.ensure_sensor_started('MAX30102'):
                self.status_label.text = 'Không thể khởi động cảm biến nhịp tim'
                self.logger.error("Failed to start MAX30102 sensor on demand")
                return

            self.measuring = True
            self.measurement_start_time = time.time()
            self.stable_readings = 0
            
            # Clear previous readings
            self.valid_hr_readings.clear()
            self.valid_spo2_readings.clear()
            
            # Turn on RED LED for measurement
            if 'MAX30102' in self.app_instance.sensors:
                max30102_sensor = self.app_instance.sensors['MAX30102']
                if hasattr(max30102_sensor, 'turn_on_red_led'):
                    max30102_sensor.turn_on_red_led()
            
            # Update UI
            self.start_stop_btn.text = 'Dừng đo'
            self.start_stop_btn.background_color = (0.8, 0.2, 0.2, 1)
            self.save_btn.disabled = True
            self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
            
            self.status_label.text = 'Đang đo trong 5 giây... Đặt ngón tay lên cảm biến'
            self.progress_bar.value = 0
            
            # Start pulse animation
            self.pulse_widget.start_pulse(60)  # Default 60 BPM
            
            # Schedule updates more frequently for better responsiveness
            Clock.schedule_interval(self._update_measurement, 0.2)
            
            self.logger.info("Heart rate measurement started - 5 second timer")
            
        except Exception as e:
            self.logger.error(f"Error starting measurement: {e}")
    
    def _stop_measurement(self):
        """Stop measurement process"""
        try:
            self.measuring = False
            
            # Turn off RED LED after measurement
            if 'MAX30102' in self.app_instance.sensors:
                max30102_sensor = self.app_instance.sensors['MAX30102']
                if hasattr(max30102_sensor, 'turn_off_red_led'):
                    max30102_sensor.turn_off_red_led()
            
            # Update UI
            self.start_stop_btn.text = 'Bắt đầu đo'
            self.start_stop_btn.background_color = (0.2, 0.8, 0.2, 1)
            
            # Stop animations
            self.pulse_widget.stop_pulse()
            Clock.unschedule(self._update_measurement)
            
            # Process collected readings and filter invalid values
            final_hr, final_spo2 = self._process_final_readings()
            
            if final_hr > 0 and final_spo2 > 0:
                self.current_hr = final_hr
                self.current_spo2 = final_spo2
                self.hr_value_label.text = f'{final_hr:.0f}'
                self.spo2_value_label.text = f'{final_spo2:.0f}'
                
                self.status_label.text = 'Đo hoàn thành - Có thể lưu kết quả!'
                self.progress_bar.value = 100
                self.save_btn.disabled = False
                self.save_btn.background_color = (0.2, 0.6, 0.8, 1)
                
                self.logger.info(f"Measurement completed: HR={final_hr:.0f}, SpO2={final_spo2:.0f}")
            else:
                self.status_label.text = 'Đo không thành công - Thử lại'
                self.progress_bar.value = 0
                self.hr_value_label.text = '--'
                self.spo2_value_label.text = '--'
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
            signal_quality_ir = max30102_status.get('signal_quality', 0)
            measurement_status = max30102_status.get('status', 'no_finger')
            
            # Update signal quality display
            self.signal_label.text = f'Chất lượng tín hiệu: {signal_quality_ir:.0f}%'
            
            # Update status with remaining time
            if measurement_status == 'no_finger':
                self.status_label.text = f'Đặt ngón tay lên cảm biến ({remaining_time:.1f}s)'
                self.pulse_widget.stop_pulse()
                self.hr_value_label.text = '--'
                self.spo2_value_label.text = '--'
                return True
            
            elif measurement_status == 'initializing':
                self.status_label.text = f'Đang khởi tạo... ({remaining_time:.1f}s)'
                return True
            
            elif measurement_status == 'poor_signal':
                self.status_label.text = f'Tín hiệu yếu - Ấn chặt hơn ({remaining_time:.1f}s)'
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
                self.hr_value_label.text = f'{current_hr:.0f}'
                self.pulse_widget.start_pulse(current_hr)
            else:
                self.hr_value_label.text = '--'
                self.pulse_widget.stop_pulse()
            
            if spo2_is_valid:
                self.spo2_value_label.text = f'{current_spo2:.0f}'
            else:
                self.spo2_value_label.text = '--'
            
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
        self.hr_value_label.text = '--'
        self.spo2_value_label.text = '--'
        self.progress_bar.value = 0
        self.status_label.text = 'Sẵn sàng đo (5 giây)'
        self.signal_label.text = 'Chất lượng tín hiệu: --'
        
        # Clear measurement data
        self.valid_hr_readings.clear()
        self.valid_spo2_readings.clear()
        self.current_hr = 0
        self.current_spo2 = 0
        self.stable_readings = 0
        
        # Auto-start measurement when entering screen
        self._start_measurement()
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Heart rate measurement screen left")
        
        # Stop any ongoing measurement
        if self.measuring:
            self._stop_measurement()