"""
Settings Screen
Screen cho cài đặt hệ thống và preferences - Material Design style
"""

from typing import Dict, Any, Optional, List
import logging
import subprocess
import threading
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.clock import Clock

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton, MDFlatButton, MDRaisedButton, MDFillRoundFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.slider import MDSlider
from kivymd.uix.textfield import MDTextField
from kivymd.uix.selectioncontrol import MDSwitch
from kivymd.uix.dialog import MDDialog
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.list import MDList, OneLineAvatarIconListItem, IconLeftWidget, IconRightWidget


# Medical-themed color scheme (đồng nhất với các màn hình khác)
MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
MED_SUCCESS = (0.2, 0.78, 0.35, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class SettingSection(MDCard):
    """Widget cho một section settings - Material Design style."""
    
    def __init__(self, title: str, icon: str = 'cog', **kwargs):
        # Extract size_hint_y from kwargs if provided, otherwise default to None
        if 'size_hint_y' not in kwargs:
            kwargs['size_hint_y'] = None
            
        super().__init__(
            orientation='vertical',
            padding=(dp(12), dp(10), dp(12), dp(10)),
            spacing=dp(6),
            radius=[dp(18)],
            md_bg_color=MED_CARD_BG,
            **kwargs
        )
        
        # Header với icon và title
        header = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(28),
            spacing=dp(6),
        )
        
        section_icon = MDIcon(
            icon=icon,
            theme_text_color='Custom',
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        section_icon.icon_size = dp(20)
        header.add_widget(section_icon)
        
        title_label = MDLabel(
            text=title,
            font_style='H6',
            bold=True,
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
            halign='left',
            valign='middle',
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
        header.add_widget(title_label)
        
        self.add_widget(header)
        
        # Content container
        self.content = MDBoxLayout(
            orientation='vertical',
            spacing=dp(8),
            size_hint_y=None,
        )
        self.content.bind(minimum_height=self.content.setter('height'))
        self.add_widget(self.content)
        self.content.bind(height=lambda instance, value: setattr(self, 'height', value + dp(48)))
    def add_setting_item(self, name: str, widget, subtitle: str = None):
        """Add a setting item to this section."""
        item_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48) if not subtitle else dp(60),
            spacing=dp(10),
        )
        
        # Setting name và subtitle
        text_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(2),
            size_hint_x=0.6,
        )
        
        name_label = MDLabel(
            text=name,
            font_style='Body1',
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
            halign='left',
            valign='middle' if not subtitle else 'bottom',
        )
        name_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
        text_layout.add_widget(name_label)
        
        if subtitle:
            subtitle_label = MDLabel(
                text=subtitle,
                font_style='Caption',
                theme_text_color='Custom',
                text_color=TEXT_MUTED,
                halign='left',
                valign='top',
            )
            subtitle_label.bind(size=lambda lbl, _: setattr(lbl, 'text_size', lbl.size))
            text_layout.add_widget(subtitle_label)
        
        item_layout.add_widget(text_layout)
        
        # Setting widget
        if isinstance(widget, MDSwitch):
            # MDSwitch should not stretch, keep compact size
            widget.size_hint_x = None
            widget.width = dp(40)
            widget.pos_hint = {'right': 0.85}
        else:
            # Other widgets (sliders, textfields, buttons) can stretch
            widget.size_hint_x = 0.4
        item_layout.add_widget(widget)
        
        self.content.add_widget(item_layout)


class SettingsScreen(Screen):
    """Settings screen cho system configuration - Material Design style."""
    
    # ------------------------------------------------------------------
    # Initialization & Lifecycle
    # ------------------------------------------------------------------
    
    def __init__(self, app_instance, **kwargs):
        """
        Initialize settings screen.
        
        Args:
            app_instance: Reference to main application
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        self.changes_made = False
        
        # Setting widgets references
        self.setting_widgets = {}
        
        # Dialog references
        self.save_dialog = None
        self.reset_dialog = None
        
        self._build_layout()
    
    # ------------------------------------------------------------------
    # UI Construction & Layout
    # ------------------------------------------------------------------
    
    def _build_layout(self):
        """Build settings layout."""
        # Main container với background color
        main_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(6),
            padding=(dp(8), dp(6), dp(8), dp(8)),
        )
        
        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg_rect, pos=self._update_bg_rect)
        
        # Header
        self._create_header(main_layout)
        
        # Scrollable content
        scroll = ScrollView(
            size_hint_y=0.88,
            scroll_type=['bars', 'content'],
            bar_width=dp(8),
        )
        content = MDBoxLayout(
            orientation='vertical',
            spacing=dp(6),
            size_hint_y=None,
            padding=(0, dp(4), 0, dp(4)),
        )
        content.bind(minimum_height=content.setter('height'))
        
        # Settings sections
        self._create_wifi_settings(content)
        self._create_sensor_settings(content)
        self._create_display_settings(content)
        self._create_alert_settings(content)
        self._create_system_settings(content)
        
        scroll.add_widget(content)
        main_layout.add_widget(scroll)
        
        # Action buttons
        self._create_action_buttons(main_layout)
        
        self.add_widget(main_layout)
    
    def _update_bg_rect(self, instance, value):
        """Update background rectangle."""
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size
    
    def _create_header(self, parent):
        """Create header với MDTopAppBar - Material Design style."""
        toolbar = MDTopAppBar(
            title='CÀI ĐẶT HỆ THỐNG',
            elevation=0,
            md_bg_color=MED_PRIMARY,
            specific_text_color=TEXT_PRIMARY,
            left_action_items=[["arrow-left", lambda _: self._on_back_pressed(None)]],
            size_hint_y=None,
            height=dp(50),
        )
        parent.add_widget(toolbar)
    
    def _create_wifi_settings(self, parent):
        """Create WiFi configuration section - ĐẦU TIÊN."""
        wifi_section = SettingSection(
            'CẤU HÌNH WIFI',
            icon='wifi',
            size_hint_y=None,
        )
        
        # WiFi status
        self._wifi_status_label = MDLabel(
            text="Đang kiểm tra...",
            font_style='Body2',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
            halign='left',
        )
        wifi_section.content.add_widget(self._wifi_status_label)
        
        # Scan button
        scan_btn = MDFillRoundFlatIconButton(
            text='QUÉT WIFI',
            icon='wifi-sync',
            md_bg_color=MED_CARD_ACCENT,
            text_color=TEXT_PRIMARY,
            size_hint_y=None,
            height=dp(48),
            pos_hint={'center_x': 0.5},
        )
        scan_btn.bind(on_release=self._on_scan_wifi_pressed)
        wifi_section.content.add_widget(scan_btn)
        
        # WiFi list container (initially empty)
        self._wifi_list_container = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=0,
        )
        wifi_section.content.add_widget(self._wifi_list_container)
        
        wifi_section.height = dp(28 + 10 + 120 + 10)  # header + padding + content + padding
        parent.add_widget(wifi_section)
        
        # Update status on enter
        Clock.schedule_once(lambda dt: self._update_wifi_status(), 0.5)
    
    def _create_sensor_settings(self, parent):
        """Create sensor configuration section."""
        sensor_section = SettingSection(
            'CẢM BIẾN',
            icon='heart-pulse',
            size_hint_y=None,
        )
        
        # MAX30102 settings
        self.setting_widgets['max30102_enabled'] = MDSwitch()
        self.setting_widgets['max30102_enabled'].active = True
        sensor_section.add_setting_item(
            'Cảm biến nhịp tim',
            self.setting_widgets['max30102_enabled'],
            subtitle='MAX30102 (HR/SpO₂)'
        )
        
        self.setting_widgets['max30102_led_brightness'] = MDSlider(
            min=50,
            max=255,
            value=127,
            color=MED_CARD_ACCENT,
        )
        sensor_section.add_setting_item(
            'Độ sáng LED',
            self.setting_widgets['max30102_led_brightness'],
            subtitle='50-255'
        )
        
        # MLX90614 settings
        self.setting_widgets['mlx90614_enabled'] = MDSwitch()
        self.setting_widgets['mlx90614_enabled'].active = True
        sensor_section.add_setting_item(
            'Cảm biến nhiệt độ',
            self.setting_widgets['mlx90614_enabled'],
            subtitle='MLX90614 IR'
        )
        
        self.setting_widgets['temp_offset'] = MDSlider(
            min=-5,
            max=5,
            value=0,
            color=MED_CARD_ACCENT,
        )
        sensor_section.add_setting_item(
            'Hiệu chỉnh nhiệt độ',
            self.setting_widgets['temp_offset'],
            subtitle='±5°C'
        )
        
        # Blood pressure settings
        self.setting_widgets['bp_enabled'] = MDSwitch()
        self.setting_widgets['bp_enabled'].active = True
        sensor_section.add_setting_item(
            'Cảm biến huyết áp',
            self.setting_widgets['bp_enabled'],
            subtitle='HX710B'
        )
        
        self.setting_widgets['bp_max_pressure'] = MDSlider(
            min=150,
            max=250,
            value=180,
            color=MED_CARD_ACCENT,
        )
        sensor_section.add_setting_item(
            'Áp suất tối đa',
            self.setting_widgets['bp_max_pressure'],
            subtitle='150-250 mmHg'
        )
        
        # Auto-calculate height based on content
        sensor_section.height = dp(28 + 10 + (6 * 60) + 10)  # header + padding + 6 items + padding
        parent.add_widget(sensor_section)
    
    def _create_display_settings(self, parent):
        """Create display configuration section."""
        display_section = SettingSection(
            'HIỂN THỊ',
            icon='monitor',
            size_hint_y=None,
        )
        
        # Screen brightness
        self.setting_widgets['screen_brightness'] = MDSlider(
            min=10,
            max=100,
            value=80,
            color=MED_CARD_ACCENT,
        )
        display_section.add_setting_item(
            'Độ sáng màn hình',
            self.setting_widgets['screen_brightness'],
            subtitle='10-100%'
        )
        
        # Auto screen off
        self.setting_widgets['auto_screen_off'] = MDSwitch()
        self.setting_widgets['auto_screen_off'].active = False
        display_section.add_setting_item(
            'Tự động tắt màn hình',
            self.setting_widgets['auto_screen_off'],
            subtitle='Tiết kiệm pin'
        )
        
        # Update frequency
        self.setting_widgets['update_freq'] = MDSlider(
            min=0.5,
            max=5,
            value=1,
            color=MED_CARD_ACCENT,
        )
        display_section.add_setting_item(
            'Tần suất cập nhật',
            self.setting_widgets['update_freq'],
            subtitle='0.5-5s'
        )
        
        # Language button
        language_btn = MDRectangleFlatIconButton(
            text='Tiếng Việt',
            icon='translate',
            text_color=MED_PRIMARY,
            line_color=MED_PRIMARY,
            size_hint_y=None,
            height=dp(36),
        )
        display_section.add_setting_item(
            'Ngôn ngữ',
            language_btn
        )
        
        display_section.height = dp(28 + 10 + (4 * 60) + 10)
        parent.add_widget(display_section)
    
    def _create_alert_settings(self, parent):
        """Create alert configuration section."""
        alert_section = SettingSection(
            'CẢNH BÁO',
            icon='alert',
            size_hint_y=None,
        )
        
        # Voice alerts
        self.setting_widgets['voice_alerts'] = MDSwitch()
        self.setting_widgets['voice_alerts'].active = True
        alert_section.add_setting_item(
            'Cảnh báo bằng tiếng',
            self.setting_widgets['voice_alerts'],
            subtitle='Text-to-Speech'
        )
        
        # Voice volume
        self.setting_widgets['voice_volume'] = MDSlider(
            min=20,
            max=100,
            value=80,
            color=MED_CARD_ACCENT,
        )
        alert_section.add_setting_item(
            'Âm lượng',
            self.setting_widgets['voice_volume'],
            subtitle='20-100%'
        )
        
        # Heart rate thresholds
        self.setting_widgets['hr_low_threshold'] = MDSlider(
            min=40,
            max=80,
            value=60,
            color=MED_CARD_ACCENT,
        )
        alert_section.add_setting_item(
            'Nhịp tim thấp',
            self.setting_widgets['hr_low_threshold'],
            subtitle='40-80 bpm'
        )
        
        self.setting_widgets['hr_high_threshold'] = MDSlider(
            min=100,
            max=180,
            value=120,
            color=MED_CARD_ACCENT,
        )
        alert_section.add_setting_item(
            'Nhịp tim cao',
            self.setting_widgets['hr_high_threshold'],
            subtitle='100-180 bpm'
        )
        
        # Test voice button
        test_voice_btn = MDRectangleFlatIconButton(
            text='Kiểm tra tiếng',
            icon='volume-high',
            text_color=MED_PRIMARY,
            line_color=MED_PRIMARY,
            size_hint_y=None,
            height=dp(36),
        )
        test_voice_btn.bind(on_press=self._test_voice_alerts)
        alert_section.add_setting_item(
            'Kiểm tra hệ thống',
            test_voice_btn
        )
        
        alert_section.height = dp(28 + 10 + (5 * 60) + 10)
        parent.add_widget(alert_section)
    
    def _create_system_settings(self, parent):
        """Create system configuration section."""
        system_section = SettingSection(
            'HỆ THỐNG',
            icon='cog',
            size_hint_y=None,
        )
        
        # Patient name
        self.setting_widgets['patient_name'] = MDTextField(
            text='Bệnh nhân',
            mode='line',
            size_hint_y=None,
            height=dp(48),
            hint_text='Nhập tên bệnh nhân',
            line_color_focus=MED_CARD_ACCENT,
        )
        system_section.add_setting_item(
            'Tên bệnh nhân',
            self.setting_widgets['patient_name']
        )
        
        # Data export button
        export_btn = MDRectangleFlatIconButton(
            text='Xuất dữ liệu',
            icon='download',
            text_color=MED_PRIMARY,
            line_color=MED_PRIMARY,
            size_hint_y=None,
            height=dp(36),
        )
        export_btn.bind(on_press=self._export_data)
        system_section.add_setting_item(
            'Dữ liệu đo lường',
            export_btn
        )
        
        # Sensor calibration button
        calibrate_btn = MDRectangleFlatIconButton(
            text='Hiệu chỉnh',
            icon='tune',
            text_color=MED_CARD_ACCENT,
            line_color=MED_CARD_ACCENT,
            size_hint_y=None,
            height=dp(36),
        )
        calibrate_btn.bind(on_press=self._calibrate_sensors)
        system_section.add_setting_item(
            'Cảm biến',
            calibrate_btn
        )
        
        # System info button
        info_btn = MDRectangleFlatIconButton(
            text='Thông tin',
            icon='information',
            text_color=TEXT_MUTED,
            line_color=TEXT_MUTED,
            size_hint_y=None,
            height=dp(36),
        )
        info_btn.bind(on_press=self._show_system_info)
        system_section.add_setting_item(
            'Hệ thống',
            info_btn
        )
        
        system_section.height = dp(28 + 10 + (4 * 60) + 10)
        parent.add_widget(system_section)
    
    def _create_action_buttons(self, parent):
        """Create action buttons."""
        action_layout = MDBoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(4),
        )
        
        # Buttons container
        buttons_container = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(42),
            spacing=dp(8),
        )
        
        # Reset button
        self.reset_btn = MDRectangleFlatIconButton(
            text='Khôi phục mặc định',
            icon='restore',
            text_color=MED_WARNING,
            line_color=MED_WARNING,
        )
        self.reset_btn.bind(on_press=self._show_reset_dialog)
        buttons_container.add_widget(self.reset_btn)
        
        # Save button
        self.save_btn = MDRectangleFlatIconButton(
            text='Lưu cài đặt',
            icon='content-save',
            text_color=MED_CARD_ACCENT,
            line_color=MED_CARD_ACCENT,
        )
        self.save_btn.bind(on_press=self._show_save_dialog)
        buttons_container.add_widget(self.save_btn)
        
        action_layout.add_widget(buttons_container)
        
        # Progress bar for save/reset actions
        self.action_progress = MDProgressBar(
            max=100,
            value=0,
            color=MED_CARD_ACCENT,
            size_hint_y=None,
            height=dp(4),
        )
        action_layout.add_widget(self.action_progress)
        
        parent.add_widget(action_layout)
    
    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    
    def _on_back_pressed(self, instance):
        """Handle back button press."""
        if self.changes_made:
            # Show save confirmation dialog if changes were made
            if self.save_dialog is None:
                self.save_dialog = MDDialog(
                    title="Cài đặt chưa lưu",
                    text="Bạn có các thay đổi chưa được lưu. Bạn có muốn lưu chúng?",
                    buttons=[
                        MDFlatButton(
                            text="HỦY BỎ",
                            on_release=lambda x: self.save_dialog.dismiss()
                        ),
                        MDFlatButton(
                            text="KHÔNG LƯU",
                            on_release=lambda x: self._discard_changes_and_navigate()
                        ),
                        MDFlatButton(
                            text="LƯU",
                            text_color=MED_CARD_ACCENT,
                            on_release=lambda x: self._confirm_save_settings_and_navigate()
                        ),
                    ],
                )
            self.save_dialog.open()
        else:
            self.app_instance.navigate_to_screen('dashboard')

    def _discard_changes_and_navigate(self):
        """Dismiss dialog, reset changes_made, and navigate to dashboard."""
        if self.save_dialog:
            self.save_dialog.dismiss()
        self.changes_made = False
        self.app_instance.navigate_to_screen('dashboard')

    def _confirm_save_settings_and_navigate(self, instance):
        """Confirm save settings, then navigate to dashboard."""
        if self.save_dialog:
            self.save_dialog.dismiss()
        # Save settings, then navigate after save completes
        self._save_settings(instance, navigate_after_save=True)
    
    def _show_save_dialog(self, instance):
        """Show save confirmation dialog."""
        try:
            if self.save_dialog is None:
                self.save_dialog = MDDialog(
                    title="Lưu cài đặt",
                    text="Bạn có muốn lưu các thay đổi cài đặt?",
                    buttons=[
                        MDFlatButton(
                            text="HỦY",
                            on_release=lambda x: self.save_dialog.dismiss()
                        ),
                        MDFlatButton(
                            text="LƯU",
                            text_color=MED_CARD_ACCENT,
                            on_release=self._confirm_save_settings
                        ),
                    ],
                )
            
            self.save_dialog.open()
            
        except Exception as e:
            self.logger.error(f"Error showing save dialog: {e}")
    
    def _show_reset_dialog(self, instance):
        """Show reset confirmation dialog."""
        try:
            if self.reset_dialog is None:
                self.reset_dialog = MDDialog(
                    title="Khôi phục mặc định",
                    text="Bạn có chắc chắn muốn khôi phục tất cả cài đặt về giá trị mặc định?",
                    buttons=[
                        MDFlatButton(
                            text="HỦY",
                            on_release=lambda x: self.reset_dialog.dismiss()
                        ),
                        MDFlatButton(
                            text="KHÔI PHỤC",
                            text_color=MED_WARNING,
                            on_release=self._confirm_reset_settings
                        ),
                    ],
                )
            
            self.reset_dialog.open()
            
        except Exception as e:
            self.logger.error(f"Error showing reset dialog: {e}")
    
    def _confirm_save_settings(self, instance):
        """Confirm and save settings."""
        if self.save_dialog:
            self.save_dialog.dismiss()
        self._save_settings(instance)
    
    def _confirm_reset_settings(self, instance):
        """Confirm and reset settings."""
        if self.reset_dialog:
            self.reset_dialog.dismiss()
        self._reset_settings(instance)
    
    # ------------------------------------------------------------------
    # Settings Management
    # ------------------------------------------------------------------
    
    def _save_settings(self, instance):
        """Save current settings"""
        try:
            # Show progress
            self.action_progress.value = 50
            self.save_btn.disabled = True
            self.reset_btn.disabled = True
            
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
            
            config_data = self.app_instance.config_data
            
            # Update config_data dictionary with new values
            # Sensor settings
            config_data.setdefault('sensors', {}).setdefault('max30102', {})['enabled'] = settings['max30102_enabled']
            config_data['sensors']['max30102']['led_brightness'] = settings['max30102_led_brightness']
            config_data.setdefault('sensors', {}).setdefault('mlx90614', {})['enabled'] = settings['mlx90614_enabled']
            config_data['sensors']['mlx90614']['temperature_offset'] = settings['temp_offset']
            config_data.setdefault('sensors', {}).setdefault('blood_pressure', {})['enabled'] = settings['bp_enabled']
            config_data['sensors']['blood_pressure']['max_pressure_mmhg'] = settings['bp_max_pressure']
            
            # Display settings (assuming these are managed by app_instance attributes for now)
            setattr(self.app_instance, 'screen_brightness', settings['screen_brightness'])
            setattr(self.app_instance, 'auto_screen_off', settings['auto_screen_off'])
            setattr(self.app_instance, 'update_freq', settings['update_freq'])
            
            # Alert settings
            config_data.setdefault('audio', {})['voice_enabled'] = settings['voice_alerts']
            config_data['audio']['volume'] = settings['voice_volume']
            # Lưu vào threshold_management.baseline (format mới)
            baseline = config_data.setdefault('threshold_management', {}).setdefault('baseline', {})
            baseline.setdefault('heart_rate', {})['min_normal'] = settings['hr_low_threshold']
            baseline['heart_rate']['max_normal'] = settings['hr_high_threshold']
            
            # System settings - Patient Name (this needs special handling for device-centric)
            # For now, update a temporary patient_name in app_instance.current_data
            # In a real device-centric flow, this would update a patient record in the cloud DB.
            self.app_instance.current_data['patient_name'] = settings['patient_name']

            # Persist the updated configuration to app_config.yaml
            self.app_instance.persist_config()
            self.logger.info(f"Settings saved to app_config.yaml and applied.")
            self._play_voice_feedback("Đã lưu cài đặt thành công")
            
            self.changes_made = False
            
            # Complete progress
            self.action_progress.value = 100
            
            # Reset UI after short delay
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: self._reset_action_ui(), 1.0)
            
        except Exception as e:
            self.logger.error(f"Error saving settings: {e}", exc_info=True)
            self._play_voice_feedback("Lỗi khi lưu cài đặt")
            self._reset_action_ui()
    
    def _reset_settings(self, instance):
        """Reset settings to defaults"""
        try:
            # Show progress
            self.action_progress.value = 50
            self.save_btn.disabled = True
            self.reset_btn.disabled = True
            
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
            self.changes_made = False # No changes needed if we reset to defaults and save
            
            # Persist default configuration to app_config.yaml
            self.app_instance.persist_config()
            self.logger.info("Default settings restored and persisted to app_config.yaml")

            # Complete progress
            self.action_progress.value = 100
            
            # Reset UI after short delay
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: self._reset_action_ui(), 1.0)
            
        except Exception as e:
            self.logger.error(f"Error resetting settings: {e}", exc_info=True)
            self._play_voice_feedback("Lỗi khi khôi phục cài đặt mặc định")
            self._reset_action_ui()
    
    # ------------------------------------------------------------------
    # Utilities & Helpers
    # ------------------------------------------------------------------
    
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
            
            speak_fn = getattr(self.app_instance, 'speak_text', None)
            if speak_fn is None:
                self.logger.warning("TTS engine (speak_text) not available on app instance")
                return

            speak_fn(message, volume=volume, force=True) # Force to play, even if other TTS is active
            
        except Exception as e:
            self.logger.error(f"Error playing voice feedback: {e}", exc_info=True)
    
    def _reset_action_ui(self):
        """Reset action buttons and progress bar to default state"""
        try:
            self.action_progress.value = 0
            self.save_btn.disabled = False
            self.reset_btn.disabled = False
        except Exception as e:
            self.logger.error(f"Error resetting action UI: {e}")
    
    # ------------------------------------------------------------------
    # WiFi Management
    # ------------------------------------------------------------------
    
    def _update_wifi_status(self):
        """Update WiFi connection status"""
        try:
            # Get current WiFi status using nmcli
            result = subprocess.run(
                ['sudo', 'nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL', 'device', 'wifi', 'list'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if line.startswith('yes:'):
                        parts = line.split(':')
                        ssid = parts[1] if len(parts) > 1 else "Unknown"
                        signal = parts[2] if len(parts) > 2 else "0"
                        self._wifi_status_label.text = f"Đã kết nối: {ssid} ({signal}%)"
                        self._wifi_status_label.text_color = MED_SUCCESS
                        return
                
                self._wifi_status_label.text = "Chưa kết nối WiFi"
                self._wifi_status_label.text_color = MED_WARNING
            else:
                self._wifi_status_label.text = "Không thể kiểm tra WiFi"
                self._wifi_status_label.text_color = TEXT_MUTED
                
        except Exception as e:
            self.logger.error(f"Error updating WiFi status: {e}")
            self._wifi_status_label.text = f"Lỗi: {e}"
            self._wifi_status_label.text_color = MED_WARNING
    
    def _on_scan_wifi_pressed(self, instance):
        """Handle scan WiFi button press"""
        self.logger.info("Scan WiFi button pressed")
        instance.disabled = True
        instance.text = "ĐANG QUÉT..."
        
        def scan_thread():
            networks = self._scan_wifi_networks()
            Clock.schedule_once(lambda dt: self._on_wifi_scan_complete(networks, instance))
        
        threading.Thread(target=scan_thread, daemon=True).start()
    
    def _scan_wifi_networks(self) -> List[Dict[str, Any]]:
        """Scan WiFi networks using nmcli"""
        try:
            # Rescan (cần sudo)
            subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'], timeout=10, check=False)
            
            # Get list
            result = subprocess.run(
                ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                return []
            
            networks = []
            for line in result.stdout.strip().split('\n'):
                parts = line.split(':')
                if len(parts) >= 3:
                    ssid = parts[0].strip()
                    signal = int(parts[1]) if parts[1].isdigit() else 0
                    security = parts[2].strip()
                    
                    if ssid and ssid != '--':
                        networks.append({
                            'ssid': ssid,
                            'signal': signal,
                            'security': 'WPA' if security else 'Open'
                        })
            
            # Sort by signal strength
            networks.sort(key=lambda x: x['signal'], reverse=True)
            return networks
            
        except Exception as e:
            self.logger.error(f"Error scanning WiFi: {e}")
            return []
    
    def _on_wifi_scan_complete(self, networks: List[Dict[str, Any]], button):
        """Handle WiFi scan complete"""
        button.disabled = False
        button.text = "QUÉT WIFI"
        
        # Clear old list
        self._wifi_list_container.clear_widgets()
        
        if not networks:
            no_wifi_label = MDLabel(
                text="Không tìm thấy mạng WiFi",
                font_style='Caption',
                theme_text_color='Custom',
                text_color=TEXT_MUTED,
                halign='center',
                size_hint_y=None,
                height=dp(40),
            )
            self._wifi_list_container.add_widget(no_wifi_label)
            self._wifi_list_container.height = dp(40)
            return
        
        # Add networks to list
        for network in networks[:10]:  # Show top 10
            item = self._create_wifi_item(network)
            self._wifi_list_container.add_widget(item)
        
        self._wifi_list_container.height = len(networks[:10]) * dp(56)
    
    def _create_wifi_item(self, network: Dict[str, Any]) -> MDCard:
        """Create WiFi network item"""
        card = MDCard(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(52),
            padding=dp(8),
            radius=[dp(12)],
            md_bg_color=(0.1, 0.3, 0.4, 0.5),
            ripple_behavior=True,
        )
        
        # Icon
        icon = MDIcon(
            icon='wifi' if network['signal'] > 50 else 'wifi-strength-2',
            theme_text_color='Custom',
            text_color=MED_SUCCESS if network['signal'] > 50 else TEXT_MUTED,
            size_hint=(None, None),
            size=(dp(24), dp(24)),
        )
        card.add_widget(icon)
        
        # Network info
        info_box = MDBoxLayout(orientation='vertical', padding=(dp(8), 0))
        
        ssid_label = MDLabel(
            text=network['ssid'],
            font_style='Body1',
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
            bold=True,
        )
        info_box.add_widget(ssid_label)
        
        detail_label = MDLabel(
            text=f"{network['signal']}% | {'Bảo mật' if network['security'] != 'Open' else 'Mở'}",
            font_style='Caption',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
        )
        info_box.add_widget(detail_label)
        
        card.add_widget(info_box)
        
        # Bind click
        card.bind(on_release=lambda x: self._on_wifi_item_clicked(network))
        
        return card
    
    def _on_wifi_item_clicked(self, network: Dict[str, Any]):
        """Handle WiFi item click - show password dialog"""
        self.logger.info(f"WiFi clicked: {network['ssid']}")
        
        if network['security'] == 'Open':
            # Connect directly
            self._connect_to_wifi(network['ssid'], '')
        else:
            # Show password dialog
            self._show_wifi_password_dialog(network)
    
    def _show_wifi_password_dialog(self, network: Dict[str, Any]):
        """Show password input dialog with virtual keyboard"""
        password_field = MDTextField(
            hint_text="Mật khẩu WiFi (tối thiểu 8 ký tự)",
            password=True,
            size_hint_x=0.9,
            pos_hint={'center_x': 0.5},
            input_type='text',
            keyboard_mode='managed',  # Enable virtual keyboard
        )
        
        # Force show keyboard when dialog opens
        def show_keyboard(dt):
            password_field.focus = True
        
        dialog = MDDialog(
            title=f"Kết nối: {network['ssid']}",
            type="custom",
            content_cls=password_field,
            buttons=[
                MDFlatButton(
                    text="HỦY",
                    on_release=lambda x: dialog.dismiss()
                ),
                MDRaisedButton(
                    text="KẾT NỐI",
                    md_bg_color=MED_CARD_ACCENT,
                    on_release=lambda x: self._on_wifi_password_submit(network['ssid'], password_field.text, dialog)
                ),
            ],
        )
        dialog.open()
        
        # Show keyboard after dialog is fully rendered
        Clock.schedule_once(show_keyboard, 0.5)
    
    def _on_wifi_password_submit(self, ssid: str, password: str, dialog):
        """Handle password submit"""
        dialog.dismiss()
        
        if len(password) < 8:
            self._show_error_dialog("Mật khẩu phải có ít nhất 8 ký tự")
            return
        
        self._connect_to_wifi(ssid, password)
    
    def _connect_to_wifi(self, ssid: str, password: str):
        """Connect to WiFi network"""
        self.logger.info(f"Connecting to WiFi: {ssid}")
        
        # Show loading
        self._wifi_status_label.text = f"Đang kết nối {ssid}..."
        self._wifi_status_label.text_color = TEXT_MUTED
        
        def connect_thread():
            try:
                # Connect using nmcli
                cmd = ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid]
                if password:
                    cmd.extend(['password', password])
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    Clock.schedule_once(lambda dt: self._on_wifi_connect_success(ssid))
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Không thể kết nối"
                    Clock.schedule_once(lambda dt: self._on_wifi_connect_failed(error_msg))
                    
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_wifi_connect_failed(str(e)))
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def _on_wifi_connect_success(self, ssid: str):
        """Handle WiFi connect success"""
        self.logger.info(f"WiFi connected: {ssid}")
        self._update_wifi_status()
        self._show_success_dialog(f"Đã kết nối WiFi: {ssid}")
    
    def _on_wifi_connect_failed(self, error: str):
        """Handle WiFi connect failed"""
        self.logger.error(f"WiFi connect failed: {error}")
        self._wifi_status_label.text = " Kết nối thất bại"
        self._wifi_status_label.text_color = MED_WARNING
        self._show_error_dialog(f"Kết nối thất bại: {error}")
    
    def _show_success_dialog(self, message: str):
        """Show success dialog"""
        dialog = MDDialog(
            title="Thành công",
            text=message,
            buttons=[
                MDRaisedButton(
                    text="OK",
                    md_bg_color=MED_SUCCESS,
                    on_release=lambda x: dialog.dismiss()
                ),
            ],
        )
        dialog.open()
    
    def _show_error_dialog(self, message: str):
        """Show error dialog"""
        dialog = MDDialog(
            title="Lỗi",
            text=message,
            buttons=[
                MDRaisedButton(
                    text="ĐÓNG",
                    md_bg_color=MED_WARNING,
                    on_release=lambda x: dialog.dismiss()
                ),
            ],
        )
        dialog.open()
    
    # ------------------------------------------------------------------
    # Screen Lifecycle
    # ------------------------------------------------------------------
    
    def load_settings(self):
        """Load settings from configuration"""
        try:
            # TODO: Load from actual config file
            config_data = self.app_instance.config_data
            
            # Sensor settings
            self.setting_widgets['max30102_enabled'].active = config_data.get('sensors', {}).get('max30102', {}).get('enabled', True)
            self.setting_widgets['max30102_led_brightness'].value = config_data.get('sensors', {}).get('max30102', {}).get('led_brightness', 127)
            self.setting_widgets['mlx90614_enabled'].active = config_data.get('sensors', {}).get('mlx90614', {}).get('enabled', True)
            self.setting_widgets['temp_offset'].value = config_data.get('sensors', {}).get('mlx90614', {}).get('temperature_offset', 0.0)
            self.setting_widgets['bp_enabled'].active = config_data.get('sensors', {}).get('blood_pressure', {}).get('enabled', True)
            self.setting_widgets['bp_max_pressure'].value = config_data.get('sensors', {}).get('blood_pressure', {}).get('max_pressure_mmhg', 180)
            
            # Display settings (not in config yet, use app_instance attributes if they exist or defaults)
            # Assuming screen_brightness, auto_screen_off, update_freq might be managed differently
            # For now, these are not directly linked to app_config.yaml in the provided structure
            self.setting_widgets['screen_brightness'].value = getattr(self.app_instance, 'screen_brightness', 80)
            self.setting_widgets['auto_screen_off'].active = getattr(self.app_instance, 'auto_screen_off', False)
            self.setting_widgets['update_freq'].value = getattr(self.app_instance, 'update_freq', 1.0)
            
            # Alert settings
            self.setting_widgets['voice_alerts'].active = config_data.get('audio', {}).get('voice_enabled', True)
            self.setting_widgets['voice_volume'].value = config_data.get('audio', {}).get('volume', 80)
            # Thresholds từ threshold_management.baseline (format mới)
            baseline = config_data.get('threshold_management', {}).get('baseline', {})
            self.setting_widgets['hr_low_threshold'].value = baseline.get('heart_rate', {}).get('min_normal', 60)
            self.setting_widgets['hr_high_threshold'].value = baseline.get('heart_rate', {}).get('max_normal', 100)
            
            # System settings
            # Patient name is dynamic and not directly in config for device-centric.
            # Instead, it might be in app_instance.current_data or resolved from DB.
            # For now, display a placeholder or device_id if patient_id is not resolved
            patient_name = self.app_instance.current_data.get('patient_name', 'Bệnh nhân') 
            if not patient_name or patient_name == 'Bệnh nhân': # If not resolved yet, try device_id
                patient_name = self.app_instance.device_id
            self.setting_widgets['patient_name'].text = patient_name
            
            self.logger.info("Settings loaded from config")
        except Exception as e:
            self.logger.error(f"Error loading settings: {e}")
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("Settings screen entered")
        self.load_settings()
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("Settings screen left")
