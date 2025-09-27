"""
Dashboard Screen
Main dashboard screen hiển thị tất cả vital signs
"""

from typing import Dict, Any, Optional
import logging
from datetime import datetime
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, Line
from kivy.uix.widget import Widget


class VitalSignCard(BoxLayout):
    """Widget hiển thị một chỉ số sinh hiệu"""
    
    def __init__(self, title: str, unit: str, normal_range: str = "", **kwargs):
        super().__init__(orientation='vertical', spacing=5, **kwargs)
        
        self.title = title
        self.unit = unit
        self.normal_range = normal_range
        
        # Background color
        with self.canvas.before:
            Color(0.2, 0.2, 0.2, 1)  # Dark gray background
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)
        
        # Title label
        self.title_label = Label(
            text=self.title,
            font_size='14sp',
            size_hint_y=0.2,
            color=(0.8, 0.8, 0.8, 1)
        )
        self.add_widget(self.title_label)
        
        # Value label (main display)
        self.value_label = Label(
            text='--',
            font_size='28sp',
            bold=True,
            size_hint_y=0.5,
            color=(1, 1, 1, 1)
        )
        self.add_widget(self.value_label)
        
        # Unit and range label
        unit_text = f"{self.unit}"
        if self.normal_range:
            unit_text += f"\n({self.normal_range})"
        
        self.unit_label = Label(
            text=unit_text,
            font_size='10sp',
            size_hint_y=0.2,
            color=(0.6, 0.6, 0.6, 1)
        )
        self.add_widget(self.unit_label)
        
        # Status indicator
        self.status_label = Label(
            text='Chưa đo',
            font_size='10sp',
            size_hint_y=0.1,
            color=(0.6, 0.6, 0.6, 1)
        )
        self.add_widget(self.status_label)
    
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size
    
    def update_value(self, value: float, status: str = 'normal'):
        """Update the displayed value and status"""
        if value > 0:
            if self.unit == 'bpm' or self.unit == '%' or self.unit == '°C':
                self.value_label.text = f"{value:.1f}"
            else:
                self.value_label.text = f"{value:.0f}"
        else:
            self.value_label.text = '--'
        
        # Update color based on status
        status_colors = {
            'normal': (0.2, 0.8, 0.2, 1),      # Green
            'low': (1, 0.8, 0, 1),             # Yellow
            'high': (1, 0.6, 0, 1),            # Orange
            'critical': (1, 0.2, 0.2, 1),     # Red
            'poor_signal': (0.6, 0.6, 0.6, 1), # Gray
            'no_finger': (0.4, 0.4, 0.4, 1)   # Dark gray
        }
        
        self.value_label.color = status_colors.get(status, (1, 1, 1, 1))
        
        # Update status text
        status_text = {
            'normal': 'Bình thường',
            'low': 'Thấp',
            'high': 'Cao',
            'critical': 'Nguy hiểm',
            'poor_signal': 'Tín hiệu yếu',
            'no_finger': 'Không phát hiện ngón tay',
            'initializing': 'Đang đo...'
        }
        
        self.status_label.text = status_text.get(status, 'Chưa rõ')


class BloodPressureCard(BoxLayout):
    """Widget đặc biệt cho huyết áp (hiển thị 2 giá trị)"""
    
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=5, **kwargs)
        
        # Background
        with self.canvas.before:
            Color(0.2, 0.2, 0.2, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)
        
        # Title
        self.title_label = Label(
            text='Huyết áp',
            font_size='14sp',
            size_hint_y=0.2,
            color=(0.8, 0.8, 0.8, 1)
        )
        self.add_widget(self.title_label)
        
        # BP values container
        bp_container = BoxLayout(orientation='horizontal', size_hint_y=0.5)
        
        self.systolic_label = Label(
            text='--',
            font_size='24sp',
            bold=True,
            color=(1, 1, 1, 1)
        )
        bp_container.add_widget(self.systolic_label)
        
        separator = Label(
            text='/',
            font_size='20sp',
            size_hint_x=0.2,
            color=(0.8, 0.8, 0.8, 1)
        )
        bp_container.add_widget(separator)
        
        self.diastolic_label = Label(
            text='--',
            font_size='24sp',
            bold=True,
            color=(1, 1, 1, 1)
        )
        bp_container.add_widget(self.diastolic_label)
        
        self.add_widget(bp_container)
        
        # Unit label
        self.unit_label = Label(
            text='mmHg\n(90-140 / 60-90)',
            font_size='10sp',
            size_hint_y=0.2,
            color=(0.6, 0.6, 0.6, 1)
        )
        self.add_widget(self.unit_label)
        
        # Status
        self.status_label = Label(
            text='Chưa đo',
            font_size='10sp',
            size_hint_y=0.1,
            color=(0.6, 0.6, 0.6, 1)
        )
        self.add_widget(self.status_label)
    
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size
    
    def update_values(self, systolic: float, diastolic: float, status: str = 'normal'):
        """Update blood pressure values"""
        if systolic > 0 and diastolic > 0:
            self.systolic_label.text = f"{systolic:.0f}"
            self.diastolic_label.text = f"{diastolic:.0f}"
        else:
            self.systolic_label.text = '--'
            self.diastolic_label.text = '--'
        
        # Color coding
        status_colors = {
            'normal': (0.2, 0.8, 0.2, 1),
            'high': (1, 0.6, 0, 1),
            'critical': (1, 0.2, 0.2, 1)
        }
        
        color = status_colors.get(status, (1, 1, 1, 1))
        self.systolic_label.color = color
        self.diastolic_label.color = color
        
        status_text = {
            'normal': 'Bình thường',
            'high': 'Cao',
            'critical': 'Rất cao'
        }
        
        self.status_label.text = status_text.get(status, 'Chưa đo')


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
        """Create grid of vital signs cards"""
        # Container for vital signs
        vitals_container = BoxLayout(orientation='vertical', size_hint_y=0.7, spacing=5)
        
        # Top row: Heart Rate and SpO2
        top_row = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=0.5)
        
        self.heart_rate_card = VitalSignCard(
            title='Nhịp tim',
            unit='bpm',
            normal_range='60-100'
        )
        top_row.add_widget(self.heart_rate_card)
        
        self.spo2_card = VitalSignCard(
            title='SpO2',
            unit='%',
            normal_range='95-100'
        )
        top_row.add_widget(self.spo2_card)
        
        vitals_container.add_widget(top_row)
        
        # Bottom row: Temperature and Blood Pressure
        bottom_row = BoxLayout(orientation='horizontal', spacing=10, size_hint_y=0.5)
        
        self.temperature_card = VitalSignCard(
            title='Nhiệt độ',
            unit='°C',
            normal_range='36.0-37.5'
        )
        bottom_row.add_widget(self.temperature_card)
        
        self.bp_card = BloodPressureCard()
        bottom_row.add_widget(self.bp_card)
        
        vitals_container.add_widget(bottom_row)
        
        parent.add_widget(vitals_container)
    
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
    
    def _on_emergency_pressed(self, instance):
        """Handle emergency button press"""
        # TODO: Implement emergency alert
        self.logger.warning("Emergency button pressed!")
    
    def update_data(self, sensor_data: Dict[str, Any]):
        """Update display with new sensor data"""
        try:
            # Update time
            self.time_label.text = datetime.now().strftime('%H:%M:%S - %d/%m/%Y')
            
            # Update heart rate
            hr = sensor_data.get('heart_rate', 0)
            hr_status = self._get_heart_rate_status(hr)
            
            # Check sensor status for heart rate
            max30102_status = sensor_data.get('sensor_status', {}).get('MAX30102', {})
            if not max30102_status.get('finger_detected', False):
                hr_status = 'no_finger'
            elif max30102_status.get('status') == 'poor_signal':
                hr_status = 'poor_signal'
            elif max30102_status.get('status') == 'initializing':
                hr_status = 'initializing'
            
            self.heart_rate_card.update_value(hr, hr_status)
            
            # Update SpO2
            spo2 = sensor_data.get('spo2', 0)
            spo2_status = self._get_spo2_status(spo2)
            
            # Use same sensor status as heart rate
            if not max30102_status.get('finger_detected', False):
                spo2_status = 'no_finger'
            elif max30102_status.get('status') == 'poor_signal':
                spo2_status = 'poor_signal'
            elif max30102_status.get('status') == 'initializing':
                spo2_status = 'initializing'
            
            self.spo2_card.update_value(spo2, spo2_status)
            
            # Update temperature
            temp = sensor_data.get('temperature', 0)
            temp_status = self._get_temperature_status(temp)
            self.temperature_card.update_value(temp, temp_status)
            
            # Update blood pressure
            systolic = sensor_data.get('blood_pressure_systolic', 0)
            diastolic = sensor_data.get('blood_pressure_diastolic', 0)
            bp_status = self._get_bp_status(systolic, diastolic)
            self.bp_card.update_values(systolic, diastolic, bp_status)
            
        except Exception as e:
            self.logger.error(f"Error updating dashboard data: {e}")
    
    def _get_heart_rate_status(self, hr: float) -> str:
        """Get heart rate status"""
        if hr <= 0:
            return 'poor_signal'
        elif hr < 50:
            return 'critical'
        elif hr < 60:
            return 'low'
        elif hr <= 100:
            return 'normal'
        elif hr <= 150:
            return 'high'
        else:
            return 'critical'
    
    def _get_spo2_status(self, spo2: float) -> str:
        """Get SpO2 status"""
        if spo2 <= 0:
            return 'poor_signal'
        elif spo2 < 90:
            return 'critical'
        elif spo2 < 95:
            return 'low'
        else:
            return 'normal'
    
    def _get_temperature_status(self, temp: float) -> str:
        """Get temperature status"""
        if temp <= 0:
            return 'poor_signal'
        elif temp < 35.0:
            return 'critical'
        elif temp < 36.0:
            return 'low'
        elif temp <= 37.5:
            return 'normal'
        elif temp <= 39.0:
            return 'high'
        else:
            return 'critical'
    
    def _get_bp_status(self, systolic: float, diastolic: float) -> str:
        """Get blood pressure status"""
        if systolic <= 0 or diastolic <= 0:
            return 'normal'  # Not measured yet
        elif systolic >= 140 or diastolic >= 90:
            return 'high'
        elif systolic >= 160 or diastolic >= 100:
            return 'critical'
        else:
            return 'normal'
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Dashboard screen entered")
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Dashboard screen left")
        """
        Update heart rate and SpO2 display
        
        Args:
            heart_rate: Heart rate value
            spo2: SpO2 value
        """
        pass
    
    def update_temperature(self, temperature: float):
        """
        Update temperature display
        
        Args:
            temperature: Temperature value
        """
        pass
    
    def update_blood_pressure(self, systolic: float, diastolic: float, map_value: float):
        """
        Update blood pressure display
        
        Args:
            systolic: Systolic pressure
            diastolic: Diastolic pressure
            map_value: Mean arterial pressure
        """
        pass
    
    def update_sensor_status(self, sensor_name: str, status: str, color: str):
        """
        Update sensor status indicator
        
        Args:
            sensor_name: Name of sensor
            status: Status text
            color: Color for status indicator
        """
        pass
    
    def _apply_threshold_colors(self, value: float, thresholds: Dict[str, float]) -> str:
        """
        Apply color based on threshold values
        
        Args:
            value: Current value
            thresholds: Dictionary of threshold values
            
        Returns:
            Color string for display
        """
        pass
    
    def _update_sparklines(self, sensor_data: Dict[str, Any]):
        """
        Update sparkline charts with new data
        
        Args:
            sensor_data: New sensor data
        """
        pass
    
    def on_measure_bp_button(self):
        """
        Handle blood pressure measurement button press
        """
        pass
    
    def on_settings_button(self):
        """
        Handle settings button press
        """
        pass
    
    def show_alert_banner(self, alert_message: str, alert_type: str):
        """
        Show alert banner on dashboard
        
        Args:
            alert_message: Alert message text
            alert_type: Type of alert
        """
        pass
    
    def hide_alert_banner(self):
        """
        Hide alert banner
        """
        pass