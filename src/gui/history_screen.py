"""Lịch sử đo lường và cảnh báo cho hệ thống IoT Health."""

from typing import Dict, Any, Optional, List, Union
import logging
import random
from datetime import datetime, timedelta
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.core.window import Window

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRectangleFlatIconButton, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.toolbar import MDTopAppBar


# Medical-themed color scheme (đồng nhất với các màn hình khác)
MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class MeasurementRecord(MDCard):
    """Widget hiển thị một bản ghi đo - Material Design style."""

    def __init__(self, record_data: Dict[str, Any], **kwargs):
        super().__init__(
            orientation='vertical',
            size_hint_y=None,
            height=dp(78),
            padding=(dp(12), dp(8), dp(12), dp(8)),
            spacing=dp(4),
            radius=[dp(12)],
            md_bg_color=MED_CARD_BG,
            **kwargs
        )

        self.record_data = record_data
        self._build_content()

    def _build_content(self):
        """Xây dựng nội dung card."""
        # Header row: timestamp + alert indicator
        header_row = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(18),
            spacing=dp(6),
        )

        timestamp = self.record_data.get('timestamp')
        time_icon = MDIcon(
            icon='clock-outline',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
            size_hint=(None, None),
            size=(dp(16), dp(16)),
        )
        time_icon.icon_size = dp(14)
        header_row.add_widget(time_icon)

        time_label = MDLabel(
            text=self._format_timestamp(timestamp),
            font_style='Caption',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
            halign='left',
            valign='middle',
        )
        header_row.add_widget(time_label)

        # Alert indicator if exists
        alert = self.record_data.get('alert')
        if alert:
            alert_icon = MDIcon(
                icon='alert-circle',
                theme_text_color='Custom',
                text_color=MED_WARNING,
                size_hint=(None, None),
                size=(dp(16), dp(16)),
            )
            alert_icon.icon_size = dp(14)
            header_row.add_widget(alert_icon)

        self.add_widget(header_row)

        # Measurements row: HR, SpO2, Temp, BP
        measurements_row = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(8),
            size_hint_y=None,
            height=dp(42),
        )

        # Heart Rate
        hr = self.record_data.get('heart_rate') or self.record_data.get('hr') or 0
        hr_box = self._create_measurement_box(
            icon='heart-pulse',
            value=f"{hr:.0f}" if hr else "--",
            unit='bpm',
            color=self._get_hr_color(hr)
        )
        measurements_row.add_widget(hr_box)

        # SpO2
        spo2 = self.record_data.get('spo2')
        spo2_box = self._create_measurement_box(
            icon='water-percent',
            value=f"{spo2:.0f}" if spo2 else "--",
            unit='%',
            color=self._get_spo2_color(spo2 or 0)
        )
        measurements_row.add_widget(spo2_box)

        # Temperature
        temp = (
            self.record_data.get('temperature')
            or self.record_data.get('temp')
            or self.record_data.get('object_temperature')
        )
        temp_box = self._create_measurement_box(
            icon='thermometer',
            value=f"{temp:.1f}" if temp else "--",
            unit='°C',
            color=self._get_temp_color(temp or 0)
        )
        measurements_row.add_widget(temp_box)

        # Blood Pressure
        systolic = self.record_data.get('blood_pressure_systolic') or self.record_data.get('systolic')
        diastolic = self.record_data.get('blood_pressure_diastolic') or self.record_data.get('diastolic')
        bp_text = f"{systolic:.0f}/{diastolic:.0f}" if systolic and diastolic else "--/--"
        bp_box = self._create_measurement_box(
            icon='heart-box',
            value=bp_text,
            unit='mmHg',
            color=self._get_bp_color(systolic or 0, diastolic or 0)
        )
        measurements_row.add_widget(bp_box)

        self.add_widget(measurements_row)

    def _create_measurement_box(self, icon: str, value: str, unit: str, color: tuple) -> MDBoxLayout:
        """Tạo box hiển thị một chỉ số."""
        box = MDBoxLayout(
            orientation='vertical',
            spacing=dp(2),
        )

        # Icon + Value
        top_row = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(20),
            spacing=dp(4),
        )

        measure_icon = MDIcon(
            icon=icon,
            theme_text_color='Custom',
            text_color=color,
            size_hint=(None, None),
            size=(dp(18), dp(18)),
        )
        measure_icon.icon_size = dp(16)
        top_row.add_widget(measure_icon)

        value_label = MDLabel(
            text=value,
            font_style='Subtitle2',
            theme_text_color='Custom',
            text_color=color,
            halign='left',
            valign='middle',
        )
        top_row.add_widget(value_label)

        box.add_widget(top_row)

        # Unit
        unit_label = MDLabel(
            text=unit,
            font_style='Caption',
            theme_text_color='Custom',
            text_color=TEXT_MUTED,
            halign='left',
            valign='middle',
        )
        box.add_widget(unit_label)

        return box

    @staticmethod
    def _format_timestamp(value: Union[datetime, str, float, int, None]) -> str:
        """Format timestamp hiển thị."""
        if isinstance(value, datetime):
            ts = value
        elif isinstance(value, (int, float)):
            ts = datetime.fromtimestamp(value)
        elif isinstance(value, str):
            try:
                ts = datetime.fromisoformat(value.strip())
            except ValueError:
                return value
        else:
            return "--"
        return ts.strftime('%H:%M %d/%m')

    def _get_hr_color(self, hr: float) -> tuple:
        """Lấy màu cho giá trị nhịp tim."""
        if hr <= 0:
            return TEXT_MUTED
        elif hr < 50 or hr > 150:
            return MED_WARNING
        elif hr < 60 or hr > 120:
            return (1, 0.6, 0, 1)
        else:
            return MED_CARD_ACCENT

    def _get_spo2_color(self, spo2: float) -> tuple:
        """Lấy màu cho giá trị SpO2."""
        if spo2 <= 0:
            return TEXT_MUTED
        elif spo2 < 90:
            return MED_WARNING
        elif spo2 < 95:
            return (1, 0.6, 0, 1)
        else:
            return MED_CARD_ACCENT

    def _get_temp_color(self, temp: float) -> tuple:
        """Lấy màu cho giá trị nhiệt độ."""
        if temp <= 0:
            return TEXT_MUTED
        elif temp < 35.0 or temp > 39.0:
            return MED_WARNING
        elif temp < 36.0 or temp > 37.5:
            return (1, 0.6, 0, 1)
        else:
            return MED_CARD_ACCENT

    def _get_bp_color(self, systolic: float, diastolic: float) -> tuple:
        """Lấy màu cho giá trị huyết áp."""
        if systolic <= 0 or diastolic <= 0:
            return TEXT_MUTED
        elif systolic >= 160 or diastolic >= 100:
            return MED_WARNING
        elif systolic >= 140 or diastolic >= 90:
            return (1, 0.6, 0, 1)
        else:
            return MED_CARD_ACCENT



class HistoryScreen(Screen):
    """Screen hiển thị lịch sử các phép đo - Material Design style."""

    def __init__(self, app_instance, **kwargs):
        """
        Initialize history screen.

        Args:
            app_instance: Reference to main application
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)

        # Current filter settings
        self.current_filter = 'today'
        self.records_list = None
        self.filter_buttons = {}

        self._build_layout()

    def _build_layout(self):
        """Xây dựng layout chính."""
        # Main container với background color
        main_layout = MDBoxLayout(orientation='vertical', spacing=dp(8), padding=dp(10))

        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg_rect, pos=self._update_bg_rect)

        # Header
        self._create_header(main_layout)

        # Filter buttons
        self._create_filter_buttons(main_layout)

        # Scrollable records list
        scroll = ScrollView(
            size_hint_y=0.75,
            scroll_type=['bars', 'content'],
            bar_width=dp(8),
        )
        self.records_list = MDBoxLayout(
            orientation='vertical',
            spacing=dp(6),
            size_hint_y=None,
            padding=(0, dp(4), 0, dp(4)),
        )
        self.records_list.bind(minimum_height=self.records_list.setter('height'))

        scroll.add_widget(self.records_list)
        main_layout.add_widget(scroll)

        # Bottom controls
        self._create_bottom_controls(main_layout)

        self.add_widget(main_layout)

    def _update_bg_rect(self, instance, value):
        """Update background rectangle."""
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def _create_header(self, parent):
        """Tạo header với back button và title."""
        header_card = MDCard(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(50),
            padding=(dp(8), dp(6), dp(8), dp(6)),
            radius=[dp(20)],
            md_bg_color=MED_CARD_BG,
        )

        # Back button
        back_btn = MDIconButton(
            icon='arrow-left',
            theme_text_color='Custom',
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        back_btn.bind(on_press=self._on_back_pressed)
        header_card.add_widget(back_btn)

        # Title
        title = MDLabel(
            text='LỊCH SỬ ĐO',
            font_style='H6',
            bold=True,
            halign='center',
            valign='middle',
            theme_text_color='Custom',
            text_color=TEXT_PRIMARY,
        )
        header_card.add_widget(title)

        # Spacer for balance
        spacer = MDBoxLayout(size_hint=(None, None), size=(dp(40), dp(40)))
        header_card.add_widget(spacer)

        parent.add_widget(header_card)

    def _create_filter_buttons(self, parent):
        """Tạo filter buttons cho các khoảng thời gian."""
        filter_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(38),
            spacing=dp(6),
        )

        filters = [
            ('today', 'Hôm nay', 'calendar-today'),
            ('week', '7 ngày', 'calendar-week'),
            ('month', '30 ngày', 'calendar-month'),
            ('all', 'Tất cả', 'calendar-range')
        ]

        for filter_key, filter_name, icon in filters:
            btn = MDRectangleFlatIconButton(
                text=filter_name,
                icon=icon,
                text_color=MED_CARD_ACCENT if filter_key == 'today' else TEXT_MUTED,
                line_color=MED_CARD_ACCENT if filter_key == 'today' else TEXT_MUTED,
            )
            btn.bind(on_press=lambda x, key=filter_key: self._on_filter_changed(key))
            self.filter_buttons[filter_key] = btn
            filter_layout.add_widget(btn)

        parent.add_widget(filter_layout)

    def _create_bottom_controls(self, parent):
        """Tạo bottom control buttons."""
        control_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(42),
            spacing=dp(8),
        )

        # Export button
        export_btn = MDRectangleFlatIconButton(
            text='Xuất CSV',
            icon='download',
            text_color=MED_CARD_ACCENT,
            line_color=MED_CARD_ACCENT,
        )
        export_btn.bind(on_press=self._export_data)
        control_layout.add_widget(export_btn)

        # Statistics button
        stats_btn = MDRectangleFlatIconButton(
            text='Thống kê',
            icon='chart-line',
            text_color=MED_PRIMARY,
            line_color=MED_PRIMARY,
        )
        stats_btn.bind(on_press=self._show_statistics)
        control_layout.add_widget(stats_btn)

        # Clear history button
        clear_btn = MDRectangleFlatIconButton(
            text='Xóa lịch sử',
            icon='delete-sweep',
            text_color=MED_WARNING,
            line_color=MED_WARNING,
        )
        clear_btn.bind(on_press=self._clear_history)
        control_layout.add_widget(clear_btn)

        parent.add_widget(control_layout)

    def _on_back_pressed(self, instance):
        """Xử lý back button press."""
        self.app_instance.navigate_to_screen('dashboard')

    def _on_filter_changed(self, filter_key: str):
        """Xử lý filter button press."""
        # Update button colors
        for key, btn in self.filter_buttons.items():
            if key == filter_key:
                btn.text_color = MED_CARD_ACCENT
                btn.line_color = MED_CARD_ACCENT
            else:
                btn.text_color = TEXT_MUTED
                btn.line_color = TEXT_MUTED

        self.current_filter = filter_key
        self._load_records()

    def _load_records(self):
        """Load records dựa trên current filter."""
        try:
            # Clear existing records
            self.records_list.clear_widgets()

            # Get date range based on filter
            now = datetime.now()

            if self.current_filter == 'today':
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif self.current_filter == 'week':
                start_date = now - timedelta(days=7)
            elif self.current_filter == 'month':
                start_date = now - timedelta(days=30)
            else:
                start_date = None

            records = self.app_instance.get_history_records(start_date, now, limit=200)

            if not records:
                # No records message - Material Design style
                no_records_card = MDCard(
                    orientation='vertical',
                    size_hint_y=None,
                    height=dp(100),
                    padding=dp(20),
                    radius=[dp(12)],
                    md_bg_color=MED_CARD_BG,
                )

                no_icon = MDIcon(
                    icon='folder-open-outline',
                    theme_text_color='Custom',
                    text_color=TEXT_MUTED,
                    size_hint=(None, None),
                    size=(dp(48), dp(48)),
                    pos_hint={'center_x': 0.5},
                )
                no_icon.icon_size = dp(42)
                no_records_card.add_widget(no_icon)

                no_records_label = MDLabel(
                    text='Không có dữ liệu trong khoảng thời gian này',
                    font_style='Body2',
                    halign='center',
                    valign='middle',
                    theme_text_color='Custom',
                    text_color=TEXT_MUTED,
                )
                no_records_card.add_widget(no_records_label)

                self.records_list.add_widget(no_records_card)
            else:
                # Add records to list
                for record in records:
                    record_widget = MeasurementRecord(record)
                    self.records_list.add_widget(record_widget)

            self.logger.info(f"Loaded {len(records)} records for filter: {self.current_filter}")

        except Exception as e:
            self.logger.error(f"Error loading records: {e}")

    def _export_data(self, instance):
        """Export measurement data."""
        try:
            # TODO: Implement actual data export
            self.logger.info("Data export requested")

            # Show confirmation message
            self._show_message("Đã xuất dữ liệu thành công")

        except Exception as e:
            self.logger.error(f"Error exporting data: {e}")
            self._show_message("Lỗi khi xuất dữ liệu")

    def _clear_history(self, instance):
        """Clear measurement history."""
        try:
            # TODO: Show confirmation dialog first
            # TODO: Implement actual history clearing
            self.logger.info("History clear requested")

            # Reload records (will be empty after clearing)
            self._load_records()

            self._show_message("Đã xóa lịch sử")

        except Exception as e:
            self.logger.error(f"Error clearing history: {e}")
            self._show_message("Lỗi khi xóa lịch sử")

    def _show_statistics(self, instance):
        """Show measurement statistics."""
        try:
            # TODO: Implement statistics screen or popup
            self.logger.info("Statistics requested")
            self._show_message("Tính năng thống kê đang phát triển")

        except Exception as e:
            self.logger.error(f"Error showing statistics: {e}")

    def _show_message(self, message: str):
        """Show temporary message (placeholder for popup)."""
        # For now, just log the message
        # In a real implementation, this would show a popup or toast message
        self.logger.info(f"User message: {message}")

    def on_enter(self):
        """Called when screen is entered."""
        self.logger.info("History screen entered")
        self._load_records()

    def on_leave(self):
        """Called when screen is left."""
        self.logger.info("History screen left")