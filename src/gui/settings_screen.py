"""
Settings Screen
Screen cho cài đặt hệ thống và preferences
"""

from typing import Dict, Any, Optional
import logging
import subprocess
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
from kivy.graphics import Color, Rectangle


class SettingSection(BoxLayout):
    """Widget cho một section settings"""
    
    def __init__(self, title: str, **kwargs):
        super().__init__(orientation='vertical', spacing=5, **kwargs)
        
        # Background
        with self.canvas.before:
            Color(0.15, 0.15, 0.2, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)
        
        # Title
        title_label = Label(
            text=title,
            font_size='16sp',
            bold=True,
            size_hint_y=None,
            height=40,
            color=(1, 1, 1, 1)
        )
        self.add_widget(title_label)
        
        # Content container
        self.content = BoxLayout(orientation='vertical', spacing=5, padding=(10, 5))
        self.add_widget(self.content)
    
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size
    
    def add_setting_item(self, name: str, widget):
        """Add a setting item to this section"""
        item_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40)
        
        # Setting name
        name_label = Label(
            text=name,
            size_hint_x=0.6,
            color=(0.9, 0.9, 0.9, 1),
            halign='left'
        )
        name_label.bind(size=name_label.setter('text_size'))
        item_layout.add_widget(name_label)
        
        # Setting widget
        widget.size_hint_x = 0.4
        item_layout.add_widget(widget)
        
        self.content.add_widget(item_layout)


class SettingsScreen(Screen):
    """
    Settings screen cho system configuration
    """
    
    def __init__(self, app_instance, **kwargs):
        """
        Initialize settings screen
        
        Args:
            app_instance: Reference to main application
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        self.changes_made = False
        
        # Setting widgets references
        self.setting_widgets = {}
        
        self._build_layout()
    
    def _build_layout(self):
        """Build settings layout"""
        # Main container
        main_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # Header
        self._create_header(main_layout)
        
        # Scrollable content
        scroll = ScrollView(size_hint_y=0.85)
        content = BoxLayout(orientation='vertical', spacing=15, size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        
        # Settings sections
        self._create_sensor_settings(content)
        self._create_display_settings(content)
        self._create_alert_settings(content)
        self._create_system_settings(content)
        
        scroll.add_widget(content)
        main_layout.add_widget(scroll)
        
        # Action buttons
        self._create_action_buttons(main_layout)
        
        self.add_widget(main_layout)
    
    def _create_header(self, parent):
        """Create header with title and back button"""
        header = BoxLayout(orientation='horizontal', size_hint_y=0.1, spacing=10)
        
        # Title
        title = Label(
            text='CÀI ĐẶT HỆ THỐNG',
            font_size='18sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_x=0.8
        )
        header.add_widget(title)
        
        # Back button
        back_btn = Button(
            text='← Quay lại',
            font_size='14sp',
            size_hint_x=0.2,
            background_color=(0.6, 0.6, 0.6, 1)
        )
        back_btn.bind(on_press=self._on_back_pressed)
        header.add_widget(back_btn)
        
        parent.add_widget(header)
    
    def _create_sensor_settings(self, parent):
        """Create sensor configuration section"""
        sensor_section = SettingSection('CẢM BIẾN', size_hint_y=None, height=300)
        
        # MAX30102 settings
        self.setting_widgets['max30102_enabled'] = Switch(active=True)
        sensor_section.add_setting_item('Cảm biến nhịp tim', self.setting_widgets['max30102_enabled'])
        
        self.setting_widgets['max30102_led_brightness'] = Slider(
            min=50, max=255, value=127, step=1
        )
        sensor_section.add_setting_item('Độ sáng LED', self.setting_widgets['max30102_led_brightness'])
        
        # MLX90614 settings
        self.setting_widgets['mlx90614_enabled'] = Switch(active=True)
        sensor_section.add_setting_item('Cảm biến nhiệt độ', self.setting_widgets['mlx90614_enabled'])
        
        self.setting_widgets['temp_offset'] = Slider(
            min=-5, max=5, value=0, step=0.1
        )
        sensor_section.add_setting_item('Hiệu chỉnh nhiệt độ (°C)', self.setting_widgets['temp_offset'])
        
        # Blood pressure settings
        self.setting_widgets['bp_enabled'] = Switch(active=True)
        sensor_section.add_setting_item('Cảm biến huyết áp', self.setting_widgets['bp_enabled'])
        
        self.setting_widgets['bp_max_pressure'] = Slider(
            min=150, max=250, value=180, step=5
        )
        sensor_section.add_setting_item('Áp suất tối đa (mmHg)', self.setting_widgets['bp_max_pressure'])
        
        parent.add_widget(sensor_section)
    
    def _create_display_settings(self, parent):
        """Create display configuration section"""
        display_section = SettingSection('HIỂN THỊ', size_hint_y=None, height=200)
        
        # Screen brightness
        self.setting_widgets['screen_brightness'] = Slider(
            min=10, max=100, value=80, step=5
        )
        display_section.add_setting_item('Độ sáng màn hình (%)', self.setting_widgets['screen_brightness'])
        
        # Auto screen off
        self.setting_widgets['auto_screen_off'] = Switch(active=False)
        display_section.add_setting_item('Tự động tắt màn hình', self.setting_widgets['auto_screen_off'])
        
        # Update frequency
        self.setting_widgets['update_freq'] = Slider(
            min=0.5, max=5, value=1, step=0.5
        )
        display_section.add_setting_item('Tần suất cập nhật (s)', self.setting_widgets['update_freq'])
        
        # Language (placeholder)
        language_btn = Button(
            text='Tiếng Việt',
            background_color=(0.3, 0.5, 0.8, 1)
        )
        display_section.add_setting_item('Ngôn ngữ', language_btn)
        
        parent.add_widget(display_section)
    
    def _create_alert_settings(self, parent):
        """Create alert configuration section"""
        alert_section = SettingSection('CẢNH BÁO', size_hint_y=None, height=250)
        
        # Voice alerts
        self.setting_widgets['voice_alerts'] = Switch(active=True)
        alert_section.add_setting_item('Cảnh báo bằng tiếng', self.setting_widgets['voice_alerts'])
        
        # Voice volume
        self.setting_widgets['voice_volume'] = Slider(
            min=20, max=100, value=80, step=5
        )
        alert_section.add_setting_item('Âm lượng (%)', self.setting_widgets['voice_volume'])
        
        # Heart rate thresholds
        self.setting_widgets['hr_low_threshold'] = Slider(
            min=40, max=80, value=60, step=5
        )
        alert_section.add_setting_item('Nhịp tim thấp (bpm)', self.setting_widgets['hr_low_threshold'])
        
        self.setting_widgets['hr_high_threshold'] = Slider(
            min=100, max=180, value=120, step=5
        )
        alert_section.add_setting_item('Nhịp tim cao (bpm)', self.setting_widgets['hr_high_threshold'])
        
        # Test voice button
        test_voice_btn = Button(
            text='Kiểm tra tiếng',
            background_color=(0.8, 0.6, 0.2, 1)
        )
        test_voice_btn.bind(on_press=self._test_voice_alerts)
        alert_section.add_setting_item('Kiểm tra', test_voice_btn)
        
        parent.add_widget(alert_section)
    
    def _create_system_settings(self, parent):
        """Create system configuration section"""
        system_section = SettingSection('HỆ THỐNG', size_hint_y=None, height=200)
        
        # Patient name
        self.setting_widgets['patient_name'] = TextInput(
            text='Bệnh nhân',
            multiline=False,
            size_hint_y=None,
            height=30
        )
        system_section.add_setting_item('Tên bệnh nhân', self.setting_widgets['patient_name'])
        
        # Data export
        export_btn = Button(
            text='Xuất dữ liệu',
            background_color=(0.2, 0.6, 0.8, 1)
        )
        export_btn.bind(on_press=self._export_data)
        system_section.add_setting_item('Dữ liệu', export_btn)
        
        # Sensor calibration
        calibrate_btn = Button(
            text='Hiệu chỉnh',
            background_color=(0.8, 0.3, 0.8, 1)
        )
        calibrate_btn.bind(on_press=self._calibrate_sensors)
        system_section.add_setting_item('Cảm biến', calibrate_btn)
        
        # System info
        info_btn = Button(
            text='Thông tin',
            background_color=(0.5, 0.5, 0.5, 1)
        )
        info_btn.bind(on_press=self._show_system_info)
        system_section.add_setting_item('Hệ thống', info_btn)
        
        parent.add_widget(system_section)
    
    def _create_action_buttons(self, parent):
        """Create action buttons"""
        action_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=0.05,
            spacing=10
        )
        
        # Save button
        save_btn = Button(
            text='Lưu cài đặt',
            font_size='14sp',
            background_color=(0.2, 0.8, 0.2, 1)
        )
        save_btn.bind(on_press=self._save_settings)
        action_layout.add_widget(save_btn)
        
        # Reset button
        reset_btn = Button(
            text='Khôi phục mặc định',
            font_size='14sp',
            background_color=(0.8, 0.6, 0.2, 1)
        )
        reset_btn.bind(on_press=self._reset_settings)
        action_layout.add_widget(reset_btn)
        
        parent.add_widget(action_layout)
    
    def _on_back_pressed(self, instance):
        """Handle back button press"""
        if self.changes_made:
            # TODO: Show save confirmation dialog
            pass
        self.app_instance.navigate_to_screen('dashboard')
    
    def _save_settings(self, instance):
        """Save current settings"""
        try:
            # Collect settings from widgets
            settings = {}
            
            # Sensor settings
            settings['max30102_enabled'] = self.setting_widgets['max30102_enabled'].active
            settings['max30102_led_brightness'] = int(self.setting_widgets['max30102_led_brightness'].value)
            settings['mlx90614_enabled'] = self.setting_widgets['mlx90614_enabled'].active
            settings['temp_offset'] = round(self.setting_widgets['temp_offset'].value, 1)
            settings['bp_enabled'] = self.setting_widgets['bp_enabled'].active
            settings['bp_max_pressure'] = int(self.setting_widgets['bp_max_pressure'].value)
            
            # Display settings
            settings['screen_brightness'] = int(self.setting_widgets['screen_brightness'].value)
            settings['auto_screen_off'] = self.setting_widgets['auto_screen_off'].active
            settings['update_freq'] = self.setting_widgets['update_freq'].value
            
            # Alert settings
            settings['voice_alerts'] = self.setting_widgets['voice_alerts'].active
            settings['voice_volume'] = int(self.setting_widgets['voice_volume'].value)
            settings['hr_low_threshold'] = int(self.setting_widgets['hr_low_threshold'].value)
            settings['hr_high_threshold'] = int(self.setting_widgets['hr_high_threshold'].value)
            
            # System settings
            settings['patient_name'] = self.setting_widgets['patient_name'].text
            
            # Apply settings (placeholder - should save to config file)
            self.logger.info(f"Settings saved: {settings}")
            self._play_voice_feedback("Đã lưu cài đặt thành công")
            
            self.changes_made = False
            
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}")
            self._play_voice_feedback("Lỗi khi lưu cài đặt")
    
    def _reset_settings(self, instance):
        """Reset settings to defaults"""
        try:
            # Reset all widgets to default values
            self.setting_widgets['max30102_enabled'].active = True
            self.setting_widgets['max30102_led_brightness'].value = 127
            self.setting_widgets['mlx90614_enabled'].active = True
            self.setting_widgets['temp_offset'].value = 0
            self.setting_widgets['bp_enabled'].active = True
            self.setting_widgets['bp_max_pressure'].value = 180
            
            self.setting_widgets['screen_brightness'].value = 80
            self.setting_widgets['auto_screen_off'].active = False
            self.setting_widgets['update_freq'].value = 1
            
            self.setting_widgets['voice_alerts'].active = True
            self.setting_widgets['voice_volume'].value = 80
            self.setting_widgets['hr_low_threshold'].value = 60
            self.setting_widgets['hr_high_threshold'].value = 120
            
            self.setting_widgets['patient_name'].text = 'Bệnh nhân'
            
            self._play_voice_feedback("Đã khôi phục cài đặt mặc định")
            self.changes_made = True
            
        except Exception as e:
            self.logger.error(f"Error resetting settings: {e}")
    
    def _test_voice_alerts(self, instance):
        """Test voice alert system"""
        volume = int(self.setting_widgets['voice_volume'].value)
        test_msg = "Đây là kiểm tra hệ thống cảnh báo bằng giọng nói"
        self._play_voice_feedback(test_msg, volume)
    
    def _calibrate_sensors(self, instance):
        """Start sensor calibration"""
        self._play_voice_feedback("Bắt đầu hiệu chỉnh cảm biến. Vui lòng làm theo hướng dẫn")
        # TODO: Implement sensor calibration
        self.logger.info("Sensor calibration started")
    
    def _export_data(self, instance):
        """Export measurement data"""
        try:
            # TODO: Implement data export
            self._play_voice_feedback("Đang xuất dữ liệu")
            self.logger.info("Data export started")
        except Exception as e:
            self.logger.error(f"Error exporting data: {e}")
    
    def _show_system_info(self, instance):
        """Show system information"""
        # TODO: Show system info dialog
        info_msg = "Hệ thống giám sát sức khỏe IoT phiên bản 1.0"
        self._play_voice_feedback(info_msg)
        self.logger.info("System info requested")
    
    def _play_voice_feedback(self, message: str, volume: int = None):
        """Play voice feedback"""
        try:
            if not self.setting_widgets['voice_alerts'].active:
                return
                
            if volume is None:
                volume = int(self.setting_widgets['voice_volume'].value)
            
            # Use espeak-ng for Vietnamese TTS
            subprocess.Popen([
                'espeak-ng', '-v', 'vi', '-s', '150', '-a', str(volume), message
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        except Exception as e:
            self.logger.error(f"Error playing voice feedback: {e}")
    
    def load_settings(self):
        """Load settings from configuration"""
        try:
            # TODO: Load from actual config file
            # For now, settings are initialized with default values
            self.logger.info("Settings loaded")
        except Exception as e:
            self.logger.error(f"Error loading settings: {e}")
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Settings screen entered")
        self.load_settings()
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Settings screen left")