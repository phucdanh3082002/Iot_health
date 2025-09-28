"""
Dashboard Screen - Redesigned layout for Waveshare 3.5" display
"""

from typing import Dict, Any, Optional
import logging
from datetime import datetime
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.image import Image


class FeatureButton(ButtonBehavior, BoxLayout):
    """Custom button hiển thị trạng thái chức năng đo với icon ổn định."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        icon_text: str = "",
        icon_source: Optional[str] = None,
        bg_color=(0.2, 0.25, 0.35, 1),
        **kwargs,
    ):
        super().__init__(orientation='vertical', padding=(10, 12), spacing=4, **kwargs)

        self.title = title
        self.subtitle = subtitle
        self.icon_text = icon_text or title[:2].upper()
        self.icon_source = icon_source
        self.primary_bg = bg_color
        self.value_text = "--"
        self.status_text = "Chưa đo"

        with self.canvas.before:
            Color(*self.primary_bg)
            self._bg_rect = RoundedRectangle(radius=[18], pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

        def _bind_text_size(widget, horizontal_padding: int = 0):
            def _update_text_size(instance, value):
                width = max(0, value[0] - horizontal_padding)
                instance.text_size = (width, None)
            widget.bind(size=_update_text_size)
            _update_text_size(widget, widget.size)

        # Icon area
        icon_container = AnchorLayout(size_hint=(1, 0.34))
        if self.icon_source:
            icon_widget = Image(
                source=self.icon_source,
                allow_stretch=True,
                keep_ratio=True,
                size_hint=(0.55, 0.55)
            )
        else:
            icon_widget = Label(
                text=self.icon_text,
                font_size='24sp',
                bold=True,
                color=(1, 1, 1, 1),
                halign='center',
                valign='middle'
            )
            _bind_text_size(icon_widget)
        icon_container.add_widget(icon_widget)
        self.add_widget(icon_container)

        # Title label
        self.title_label = Label(
            text=f"[b]{self.title}[/b]",
            font_size='14sp',
            halign='center',
            valign='middle',
            color=(1, 1, 1, 1),
            markup=True,
            size_hint=(1, 0.2)
        )
        _bind_text_size(self.title_label, horizontal_padding=8)
        self.add_widget(self.title_label)

        # Value label
        self.value_label = Label(
            text='--',
            font_size='26sp',
            bold=True,
            halign='center',
            valign='middle',
            color=(1, 1, 1, 1),
            size_hint=(1, 0.24)
        )
        _bind_text_size(self.value_label)
        self.add_widget(self.value_label)

        # Status + subtitle labels
        self.status_label = Label(
            text='Chưa đo',
            font_size='12sp',
            halign='center',
            valign='middle',
            color=(0.87, 0.87, 0.9, 1),
            size_hint=(1, 0.12)
        )
        _bind_text_size(self.status_label, horizontal_padding=6)
        self.add_widget(self.status_label)

        self.subtitle_label = Label(
            text=self.subtitle,
            font_size='11sp',
            halign='center',
            valign='middle',
            color=(0.78, 0.78, 0.82, 1),
            size_hint=(1, 0.12)
        )
        _bind_text_size(self.subtitle_label, horizontal_padding=6)
        self.add_widget(self.subtitle_label)

    def _update_rect(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def update_state(
        self,
        value_text: str,
        status_text: str,
        subtitle: Optional[str] = None,
        bg_color=None
    ):
        self.value_text = value_text
        self.status_text = status_text
        self.value_label.text = value_text
        self.status_label.text = status_text
        if subtitle is not None:
            self.subtitle = subtitle
            self.subtitle_label.text = subtitle
        if bg_color is not None:
            self.primary_bg = bg_color
            self.canvas.before.clear()
            with self.canvas.before:
                Color(*self.primary_bg)
                self._bg_rect = RoundedRectangle(radius=[18], pos=self.pos, size=self.size)
            self.bind(pos=self._update_rect, size=self._update_rect)



class DashboardScreen(Screen):
    """Dashboard chính với các chức năng đo và lịch sử"""

    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)

        self._build_layout()

    def _build_layout(self):
        main_layout = BoxLayout(orientation='vertical', spacing=12, padding=12)

        self._create_header(main_layout)
        self._create_measurement_grid(main_layout)
        self._create_history_panel(main_layout)

        self.add_widget(main_layout)

    def _create_header(self, parent):
        header = BoxLayout(orientation='horizontal', size_hint_y=0.18, spacing=10)

        info_box = BoxLayout(orientation='vertical', padding=[6, 4])
        self.title_label = Label(
            text='IoT Health Monitor',
            font_size='18sp',
            bold=True,
            halign='left',
            valign='middle',
            color=(0.95, 0.95, 0.95, 1)
        )
        self.title_label.bind(size=self.title_label.setter('text_size'))

        self.time_label = Label(
            text=datetime.now().strftime('%H:%M:%S - %d/%m/%Y'),
            font_size='12sp',
            halign='left',
            valign='middle',
            color=(0.75, 0.75, 0.8, 1)
        )
        self.time_label.bind(size=self.time_label.setter('text_size'))

        info_box.add_widget(self.title_label)
        info_box.add_widget(self.time_label)

        header.add_widget(info_box)

        settings_btn = Button(
            text='⚙ Cài đặt',
            font_size='14sp',
            size_hint_x=0.32,
            background_color=(0.25, 0.35, 0.55, 1)
        )
        settings_btn.bind(on_press=lambda *_: self.app_instance.navigate_to_screen('settings'))
        header.add_widget(settings_btn)

        parent.add_widget(header)

    def _create_measurement_grid(self, parent):
        grid = GridLayout(cols=2, rows=2, spacing=12, size_hint_y=0.56)

        self.cardio_button = FeatureButton(
            title='Đo nhịp tim + SpO2',
            subtitle='Nhấn để đo trực tiếp',
            icon_text='HR',
            bg_color=(0.55, 0.3, 0.45, 1)
        )
        self.cardio_button.bind(on_press=self._on_cardio_pressed)
        grid.add_widget(self.cardio_button)

        self.temp_button = FeatureButton(
            title='Đo nhiệt độ',
            subtitle='Đưa cảm biến gần trán',
            icon_text='TEMP',
            bg_color=(0.35, 0.55, 0.4, 1)
        )
        self.temp_button.bind(on_press=self._on_temperature_pressed)
        grid.add_widget(self.temp_button)

        self.auto_button = FeatureButton(
            title='Chế độ tự động',
            subtitle='Đo tuần tự HR → SpO2 → Nhiệt độ',
            icon_text='AUTO',
            bg_color=(0.45, 0.35, 0.55, 1)
        )
        self.auto_button.bind(on_press=self._on_auto_sequence_pressed)
        grid.add_widget(self.auto_button)

        self.bp_button = FeatureButton(
            title='Đo huyết áp',
            subtitle='Chưa triển khai - chờ phần cứng HX710B',
            icon_text='BP',
            bg_color=(0.55, 0.4, 0.25, 1)
        )
        self.bp_button.bind(on_press=self._on_bp_pressed)
        grid.add_widget(self.bp_button)

        parent.add_widget(grid)

    def _create_history_panel(self, parent):
        panel = BoxLayout(orientation='vertical', spacing=8, size_hint_y=0.26)
        self.history_panel = panel

        with panel.canvas.before:
            Color(0.16, 0.18, 0.24, 1)
            self._history_bg = RoundedRectangle(radius=[14], pos=panel.pos, size=panel.size)
        panel.bind(pos=self._update_history_rect, size=self._update_history_rect)

        header = Label(
            text='TÓM TẮT GẦN ĐÂY',
            font_size='14sp',
            bold=True,
            color=(0.85, 0.85, 0.9, 1),
            size_hint_y=0.35
        )
        panel.add_widget(header)

        self.summary_label = Label(
            text='Chưa có dữ liệu mới.',
            font_size='12sp',
            color=(0.75, 0.75, 0.8, 1),
            halign='left',
            valign='middle'
        )
        self.summary_label.bind(size=self.summary_label.setter('text_size'))
        panel.add_widget(self.summary_label)

        controls = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=0.4)

        history_btn = Button(
            text='📖 Lịch sử đo',
            font_size='14sp',
            background_color=(0.28, 0.45, 0.65, 1)
        )
        history_btn.bind(on_press=lambda *_: self.app_instance.navigate_to_screen('history'))
        controls.add_widget(history_btn)

        emergency_btn = Button(
            text='🚨 Khẩn cấp',
            font_size='14sp',
            background_color=(0.8, 0.2, 0.2, 1)
        )
        emergency_btn.bind(on_press=self._on_emergency_pressed)
        controls.add_widget(emergency_btn)

        panel.add_widget(controls)

        parent.add_widget(panel)

    def _update_history_rect(self, *_):
        if hasattr(self, '_history_bg') and hasattr(self, 'history_panel'):
            self._history_bg.pos = self.history_panel.pos
            self._history_bg.size = self.history_panel.size

    def _on_cardio_pressed(self, *_):
        self.logger.info("Cardio button pressed, navigating to heart rate screen")
        self.app_instance.navigate_to_screen('heart_rate')

    def _on_temperature_pressed(self, *_):
        self.app_instance.navigate_to_screen('temperature')

    def _on_auto_sequence_pressed(self, *_):
        self.logger.info("Auto-measure sequence requested")
        self.auto_button.update_state("--", "Đang chuẩn bị", subtitle='Giữ bệnh nhân ổn định')

    def _on_emergency_pressed(self, *_):
        self.logger.warning("Emergency button pressed from dashboard")

    def _on_bp_pressed(self, *_):
        self.logger.info("Blood pressure button pressed, navigating to BP measurement screen")
        self.app_instance.navigate_to_screen('bp_measurement')

    def update_data(self, sensor_data: Dict[str, Any]):
        try:
            hr = sensor_data.get('heart_rate')
            spo2 = sensor_data.get('spo2')
            temp = sensor_data.get('object_temperature')

            cardio_values = []
            if hr and hr > 0:
                cardio_values.append(f"{hr:.0f} BPM")
            if spo2 and spo2 > 0:
                cardio_values.append(f"{spo2:.0f}% SpO2")

            if cardio_values:
                self.cardio_button.update_state("\n".join(cardio_values), "Đã đo", subtitle='Nhấn để xem chi tiết')
            else:
                self.cardio_button.update_state("--", "Nhấn để đo", subtitle='Nhấn để đo trực tiếp')

            if temp and temp > 0:
                self.temp_button.update_state(f"{temp:.1f}°C", "Đã đo", subtitle='Nhấn để xem chi tiết')
            else:
                self.temp_button.update_state("--", "Nhấn để đo", subtitle='Đưa cảm biến gần trán')

            systolic = sensor_data.get('blood_pressure_systolic')
            diastolic = sensor_data.get('blood_pressure_diastolic')
            if systolic and diastolic and systolic > 0 and diastolic > 0:
                value = f"{systolic:.0f}/{diastolic:.0f} mmHg"
                self.bp_button.update_state(value, "Đã đo", subtitle='Nhấn để xem chi tiết')
            else:
                self.bp_button.update_state("--", "Chờ phần cứng", subtitle='HX710B chưa sẵn sàng')

            summary_lines = []
            if hr and hr > 0:
                summary_lines.append(f"Nhịp tim: {hr:.0f} BPM")
            if spo2 and spo2 > 0:
                summary_lines.append(f"SpO2: {spo2:.0f}%")
            if temp and temp > 0:
                summary_lines.append(f"Nhiệt độ: {temp:.1f}°C")

            if summary_lines:
                self.summary_label.text = '\n'.join(summary_lines)
            else:
                self.summary_label.text = 'Chưa có dữ liệu mới.'

            if self.time_label:
                self.time_label.text = datetime.now().strftime('%H:%M:%S - %d/%m/%Y')

        except Exception as exc:
            self.logger.error(f"Error updating dashboard data: {exc}")

    def get_sensor_summary(self) -> Dict[str, Any]:
        return {
            'all_normal': True,
            'warnings': [],
            'critical': [],
            'sensor_count': 3,
            'active_sensors': 0
        }

    def on_enter(self):
        self.logger.info("Dashboard screen entered")

    def on_leave(self):
        self.logger.info("Dashboard screen left")