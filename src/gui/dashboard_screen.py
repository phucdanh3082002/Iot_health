"""
Dashboard Screen - Enhanced Version
Main dashboard screen với 3 khối cảm biến lớn
"""

from typing import Dict, Any, Optional
import logging
from datetime import datetime
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle, Ellipse, Line
from kivy.uix.widget import Widget
from kivy.animation import Animation
import math


class SensorButton(Button):
    """Button lớn cho từng loại cảm biến"""
    
    def __init__(self, sensor_name: str, icon: str, status_color=(0.3, 0.3, 0.3, 1), **kwargs):
        super().__init__(**kwargs)
        
        self.sensor_name = sensor_name
        self.icon = icon
        self.status_color = status_color
        self.current_value = "--"
        self.current_status = "Chưa đo"
        
        # Button appearance
        self.font_size = '16sp'
        self.background_color = status_color
        self.update_button_text()
        
        # Animation properties
        self.pulse_animation = None
    
    def update_button_text(self):
        """Cập nhật text hiển thị trên button"""
        self.text = f"{self.icon}\n{self.sensor_name}\n{self.current_value}\n{self.current_status}"
    
    def update_sensor_data(self, value: str, status: str, color=(0.3, 0.3, 0.3, 1)):
        """Cập nhật dữ liệu cảm biến"""
        self.current_value = value
        self.current_status = status
        self.background_color = color
        self.update_button_text()
        
        # Pulse animation cho heart rate
        if self.sensor_name == "Nhịp tim" and status not in ["Chưa đo", "Không có ngón tay"]:
            self.start_pulse_animation()
        else:
            self.stop_pulse_animation()
    
    def start_pulse_animation(self):
        """Bắt đầu animation pulse"""
        if self.pulse_animation:
            self.pulse_animation.cancel(self)
        
        # Tạo pulse effect
        pulse_anim = Animation(background_color=(1, 0.3, 0.3, 1), duration=0.5) + \
                    Animation(background_color=self.status_color, duration=0.5)
        pulse_anim.repeat = True
        pulse_anim.start(self)
        self.pulse_animation = pulse_anim
    
    def stop_pulse_animation(self):
        """Dừng animation pulse"""
        if self.pulse_animation:
            self.pulse_animation.cancel(self)
            self.pulse_animation = None


class StatusBar(BoxLayout):
    """Thanh trạng thái hiển thị thời gian và thông tin hệ thống"""
    
    def __init__(self, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=0.12, **kwargs)
        
        # Thời gian
        self.time_label = Label(
            text=datetime.now().strftime('%H:%M:%S'),
            font_size='14sp',
            size_hint_x=0.4
        )
        self.add_widget(self.time_label)
        
        # Thông tin bệnh nhân
        self.patient_label = Label(
            text='Bệnh nhân: Demo User',
            font_size='12sp',
            size_hint_x=0.4
        )
        self.add_widget(self.patient_label)
        
        # Nút cài đặt
        settings_btn = Button(
            text='⚙',
            font_size='18sp',
            size_hint_x=0.2,
            background_color=(0.4, 0.4, 0.4, 1)
        )
        self.add_widget(settings_btn)
        
        # Cập nhật thời gian định kỳ
        Clock.schedule_interval(self.update_time, 1)
    
    def update_time(self, dt):
        """Cập nhật thời gian"""
        self.time_label.text = datetime.now().strftime('%H:%M:%S')





class DashboardScreen(Screen):
    """
    Dashboard screen hiển thị vital signs chính
    """
    
    def __init__(self, app_instance, **kwargs):
        """
        Initialize dashboard screen
        
        Args:
            app_instance: Reference to main application
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # Build layout
        self._build_layout()
    
    def _build_layout(self):
        """Build dashboard layout"""
        # Main container
        main_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # Header with time and navigation
        self._create_header(main_layout)
        
        # Vital signs grid
        self._create_vital_signs_grid(main_layout)
        
        # Bottom navigation buttons
        self._create_bottom_navigation(main_layout)
        
        self.add_widget(main_layout)
    
    def _create_header(self, parent):
        """Create header with time and patient info"""
        header = BoxLayout(orientation='horizontal', size_hint_y=0.15, spacing=10)
        
        # Patient info
        patient_info = BoxLayout(orientation='vertical')
        patient_name = Label(
            text='Bệnh nhân: Người cao tuổi',
            font_size='14sp',
            size_hint_y=0.6,
            halign='left',
            color=(0.9, 0.9, 0.9, 1)
        )
        patient_name.bind(size=patient_name.setter('text_size'))
        
        self.time_label = Label(
            text=datetime.now().strftime('%H:%M:%S - %d/%m/%Y'),
            font_size='12sp',
            size_hint_y=0.4,
            halign='left',
            color=(0.7, 0.7, 0.7, 1)
        )
        self.time_label.bind(size=self.time_label.setter('text_size'))
        
        patient_info.add_widget(patient_name)
        patient_info.add_widget(self.time_label)
        header.add_widget(patient_info)
        
        # Settings button
        settings_btn = Button(
            text='⚙',
            font_size='20sp',
            size_hint_x=0.2,
            background_color=(0.3, 0.3, 0.8, 1)
        )
        settings_btn.bind(on_press=lambda x: self.app_instance.navigate_to_screen('settings'))
        header.add_widget(settings_btn)
        
        parent.add_widget(header)
    
    def _create_vital_signs_grid(self, parent):
        """Create 3 sensor buttons layout"""
        # Container for sensor buttons
        sensors_container = BoxLayout(orientation='vertical', size_hint_y=0.75, spacing=15, padding=[20, 10])
        
        # Heart Rate button (MAX30102)
        self.heart_rate_button = SensorButton(
            sensor_name="Nhịp tim & SpO2",
            icon="❤",
            status_color=(0.3, 0.6, 0.3, 1)
        )
        self.heart_rate_button.bind(on_press=self._on_heart_rate_pressed)
        sensors_container.add_widget(self.heart_rate_button)
        
        # Temperature button (MLX90614)
        self.temperature_button = SensorButton(
            sensor_name="Nhiệt độ",
            icon="🌡",
            status_color=(0.6, 0.4, 0.2, 1)
        )
        self.temperature_button.bind(on_press=self._on_temperature_pressed)
        sensors_container.add_widget(self.temperature_button)
        
        # Blood Pressure button
        self.bp_button = SensorButton(
            sensor_name="Huyết áp",
            icon="🩺",
            status_color=(0.6, 0.3, 0.3, 1)
        )
        self.bp_button.bind(on_press=self._on_blood_pressure_pressed)
        sensors_container.add_widget(self.bp_button)
        
        parent.add_widget(sensors_container)
    
    def _create_bottom_navigation(self, parent):
        """Create bottom navigation buttons"""
        nav_layout = BoxLayout(orientation='horizontal', size_hint_y=0.15, spacing=10)
        
        # Blood pressure measurement button
        bp_btn = Button(
            text='Đo huyết áp',
            font_size='16sp',
            background_color=(0.8, 0.3, 0.3, 1)
        )
        bp_btn.bind(on_press=lambda x: self.app_instance.navigate_to_screen('bp_measurement'))
        nav_layout.add_widget(bp_btn)
        
        # History button
        history_btn = Button(
            text='Lịch sử',
            font_size='16sp',
            background_color=(0.3, 0.6, 0.8, 1)
        )
        history_btn.bind(on_press=lambda x: self.app_instance.navigate_to_screen('history'))
        nav_layout.add_widget(history_btn)
        
        # Emergency button
        emergency_btn = Button(
            text='Khẩn cấp',
            font_size='16sp',
            background_color=(1, 0.2, 0.2, 1)
        )
        emergency_btn.bind(on_press=self._on_emergency_pressed)
        nav_layout.add_widget(emergency_btn)
        
        parent.add_widget(nav_layout)
    
    def _on_heart_rate_pressed(self, instance):
        """Handle heart rate button press"""
        self.app_instance.navigate_to_screen('heart_rate')
    
    def _on_temperature_pressed(self, instance):
        """Handle temperature button press"""
        self.app_instance.navigate_to_screen('temperature')
    
    def _on_blood_pressure_pressed(self, instance):
        """Handle blood pressure button press"""
        self.app_instance.navigate_to_screen('bp_measurement')
    
    def _on_emergency_pressed(self, instance):
        """Handle emergency button press"""
        # TODO: Implement emergency alert
        self.logger.warning("Emergency button pressed!")
    
    def update_data(self, sensor_data: Dict[str, Any]):
        """Update display with new sensor data"""
        try:
            # Update heart rate button based on MAX30102 sensor logic
            hr = sensor_data.get('heart_rate', 0)
            spo2 = sensor_data.get('spo2', 0)
            max30102_status = sensor_data.get('sensor_status', {}).get('MAX30102', {})
            
            # Use MAX30102 measurement status
            measurement_status = max30102_status.get('status', 'no_finger')
            hr_valid = sensor_data.get('hr_valid', False)
            spo2_valid = sensor_data.get('spo2_valid', False)
            signal_quality = max30102_status.get('signal_quality', 0)
            
            if measurement_status == 'no_finger':
                hr_display = "Đặt ngón tay"
                hr_status = "Chưa phát hiện"
                color = (0.4, 0.4, 0.4, 1)
            elif measurement_status == 'initializing':
                hr_display = "Đang khởi tạo..."
                hr_status = "Đang chuẩn bị"
                color = (0.6, 0.6, 0.3, 1)
            elif measurement_status == 'poor_signal':
                hr_display = "Tín hiệu yếu"
                hr_status = f"Chất lượng: {signal_quality:.0f}%"
                color = (0.6, 0.4, 0.2, 1)
            elif measurement_status in ['good', 'partial']:
                # Show valid readings based on MAX30102 validation ranges
                hr_text = f"{hr:.0f} bpm" if (hr_valid and 40 <= hr <= 200) else "--"
                spo2_text = f"{spo2:.0f}%" if (spo2_valid and 70 <= spo2 <= 100) else "--"
                hr_display = f"❤ {hr_text}\n🫁 {spo2_text}"
                
                # Status based on both HR and SpO2
                hr_status = self._get_combined_hr_status(hr, spo2, hr_valid, spo2_valid)
                color = self._get_status_color(hr_status)
            else:
                hr_display = "Lỗi cảm biến"
                hr_status = "Kiểm tra kết nối"
                color = (0.8, 0.2, 0.2, 1)
            
            self.heart_rate_button.update_sensor_data(hr_display, hr_status, color)
            
            # Update temperature button based on MLX90614 sensor logic
            object_temp = sensor_data.get('temperature', 0)
            ambient_temp = sensor_data.get('ambient_temperature', 0)
            mlx90614_status = sensor_data.get('sensor_status', {}).get('MLX90614', {})
            temp_status_code = mlx90614_status.get('status', 'normal')
            measurement_type = mlx90614_status.get('measurement_type', 'object')
            
            # Validate temperature using MLX90614 ranges
            if object_temp > 0 and -70 <= object_temp <= 380:
                temp_display = f"🌡 {object_temp:.1f}°C"
                if ambient_temp > 0 and -40 <= ambient_temp <= 85:
                    temp_display += f"\n🏠 {ambient_temp:.1f}°C"
                
                # Map MLX90614 status to display text
                temp_status = self._get_mlx90614_status_text(temp_status_code, object_temp)
                color = self._get_mlx90614_status_color(temp_status_code, object_temp)
            else:
                if object_temp <= 0:
                    temp_display = "Không có tín hiệu"
                    temp_status = "Kiểm tra cảm biến"
                elif object_temp < -70:
                    temp_display = "Quá thấp"
                    temp_status = "< -70°C"
                elif object_temp > 380:
                    temp_display = "Quá cao"
                    temp_status = "> 380°C"
                else:
                    temp_display = "Chưa đo"
                    temp_status = "Sẵn sàng"
                color = (0.6, 0.4, 0.2, 1)
            
            self.temperature_button.update_sensor_data(temp_display, temp_status, color)
            
            # Update blood pressure button
            systolic = sensor_data.get('blood_pressure_systolic', 0)
            diastolic = sensor_data.get('blood_pressure_diastolic', 0)
            
            if systolic > 0 and diastolic > 0:
                bp_display = f"{systolic:.0f}/{diastolic:.0f} mmHg"
                bp_status = self._get_bp_status_text(systolic, diastolic)
                color = self._get_bp_status_color(systolic, diastolic)
            else:
                bp_display = "Chưa đo"
                bp_status = "Nhấn để đo"
                color = (0.6, 0.3, 0.3, 1)
            
            self.bp_button.update_sensor_data(bp_display, bp_status, color)
            
        except Exception as e:
            self.logger.error(f"Error updating dashboard data: {e}")
    
    def _get_combined_hr_status(self, hr: float, spo2: float, hr_valid: bool, spo2_valid: bool) -> str:
        """Get combined HR and SpO2 status based on MAX30102 logic"""
        if not hr_valid and not spo2_valid:
            return 'invalid'
        
        # Check critical conditions first (following MAX30102 thresholds)
        if hr_valid and (hr < 40 or hr > 200):
            return 'critical'
        if spo2_valid and spo2 < 70:
            return 'critical'
            
        # Check warning conditions
        if hr_valid and (hr < 60 or hr > 150):
            return 'warning'
        if spo2_valid and spo2 < 90:
            return 'critical'  # SpO2 < 90 is critical
        elif spo2_valid and spo2 < 95:
            return 'warning'
            
        # Both values are in normal range
        if hr_valid and spo2_valid:
            return 'normal'
        elif hr_valid or spo2_valid:
            return 'partial'  # Only one measurement valid
        else:
            return 'invalid'
    
    def _get_mlx90614_status_text(self, status_code: str, temp: float) -> str:
        """Get temperature status text based on MLX90614 status codes"""
        if status_code == 'critical_low':
            return f'Rất thấp ({temp:.1f}°C)'
        elif status_code == 'low':
            return f'Thấp ({temp:.1f}°C)'
        elif status_code == 'normal':
            return f'Bình thường ({temp:.1f}°C)'
        elif status_code == 'high':
            return f'Hơi sốt ({temp:.1f}°C)'
        elif status_code == 'critical_high':
            return f'Sốt cao ({temp:.1f}°C)'
        else:
            return f'Đo được ({temp:.1f}°C)'
    
    def _get_bp_status_text(self, systolic: float, diastolic: float) -> str:
        """Get blood pressure status text"""
        if systolic >= 180 or diastolic >= 110:
            return 'Rất cao'
        elif systolic >= 140 or diastolic >= 90:
            return 'Cao'
        elif systolic < 90 or diastolic < 60:
            return 'Thấp'
        else:
            return 'Bình thường'
    
    def _get_status_color(self, status: str) -> tuple:
        """Get color for status"""
        colors = {
            'normal': (0.2, 0.8, 0.2, 1),      # Green
            'partial': (0.2, 0.6, 0.8, 1),     # Blue  
            'warning': (1, 0.8, 0, 1),         # Yellow
            'critical': (1, 0.2, 0.2, 1),      # Red
            'invalid': (0.5, 0.5, 0.5, 1),     # Gray
        }
        return colors.get(status, (0.5, 0.5, 0.5, 1))
    
    def _get_mlx90614_status_color(self, status_code: str, temp: float) -> tuple:
        """Get color for MLX90614 temperature status"""
        if status_code in ['critical_low', 'critical_high']:
            return (1, 0.2, 0.2, 1)  # Red - Critical
        elif status_code in ['low', 'high']:
            return (1, 0.8, 0, 1)    # Yellow - Warning
        elif status_code == 'normal':
            return (0.2, 0.8, 0.2, 1)  # Green - Normal
        else:
            return (0.6, 0.4, 0.2, 1)  # Orange - Default
    
    def _get_bp_status_color(self, systolic: float, diastolic: float) -> tuple:
        """Get color for BP status"""
        if systolic >= 180 or diastolic >= 110 or systolic < 90 or diastolic < 60:
            return (1, 0.2, 0.2, 1)  # Red
        elif systolic >= 140 or diastolic >= 90:
            return (1, 0.8, 0, 1)    # Yellow
        else:
            return (0.2, 0.8, 0.2, 1)  # Green
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Dashboard screen entered")
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Dashboard screen left")