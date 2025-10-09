"""
Dashboard Screen - KivyMD layout đồng bộ với TemperatureScreen
"""

from __future__ import annotations
from typing import Dict, Any
import logging
from datetime import datetime
from kivy.uix.screenmanager import Screen
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.button import MDRectangleFlatIconButton, MDIconButton

MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class FeatureCard(MDCard):
    """Thẻ chức năng đồng bộ màu sắc với TemperatureScreen."""

    def __init__(self, title: str, subtitle: str, icon: str, card_color: tuple[float, ...], **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.subtitle = subtitle
        self.card_color = card_color
        self.value_text = "--"
        self.status_text = "Nhấn để đo"

        self.orientation = "vertical"
        self.size_hint = (0.5, None)
        self.height = dp(96)
        self.padding = (dp(12), dp(10), dp(12), dp(10))
        self.spacing = dp(2)
        self.radius = [dp(18)]
        self.md_bg_color = self.card_color
        self.ripple_behavior = True

        content = MDBoxLayout(orientation="vertical", spacing=dp(4))

        icon_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(24),
            spacing=dp(6),
        )
        icon_widget = MDIcon(
            icon=icon,
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        icon_widget.icon_size = dp(20)
        icon_row.add_widget(icon_widget)

        title_label = MDLabel(
            text=title,
            font_style="Subtitle2",
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        icon_row.add_widget(title_label)
        content.add_widget(icon_row)

        self.value_label = MDLabel(
            text="--",
            font_style="H5",
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
        )
        self.value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        content.add_widget(self.value_label)

        self.status_label = MDLabel(
            text="Nhấn để đo",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
        )
        self.status_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        content.add_widget(self.status_label)

        self.subtitle_label = MDLabel(
            text=subtitle,
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
        )
        self.subtitle_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        content.add_widget(self.subtitle_label)

        self.add_widget(content)

    def update_state(self, value_text: str, status_text: str, subtitle: str | None = None):
        self.value_text = value_text
        self.status_text = status_text
        self.value_label.text = value_text
        self.status_label.text = status_text
        if subtitle is not None:
            self.subtitle_label.text = subtitle


class DashboardScreen(Screen):
    """Dashboard chính với các chức năng đo và lịch sử."""

    # ------------------------------------------------------------------
    # Initialization & Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)

        self._build_layout()

    # ------------------------------------------------------------------
    # UI Construction & Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        main_layout = MDBoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=(dp(8), dp(6), dp(8), dp(8)),
        )

        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self._bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)

        self._create_info_banner(main_layout)
        self._create_measurement_grid(main_layout)

        self.add_widget(main_layout)

    def _update_bg(self, instance, value):
        self._bg_rect.size = instance.size
        self._bg_rect.pos = instance.pos

    def _create_info_banner(self, parent):
        info_card = MDCard(
            orientation="vertical",
            md_bg_color=MED_CARD_BG,
            radius=[dp(16)],
            padding=(dp(12), dp(8), dp(12), dp(10)),
            spacing=dp(2),
            size_hint_y=None,
            height=dp(100),
        )

        top_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(10),
            size_hint_y=None,
            height=dp(38),
        )

        text_column = MDBoxLayout(
            orientation="vertical",
            spacing=dp(2),
            size_hint_x=1,
        )

        self.title_label = MDLabel(
            text="IoT Health Monitor",
            font_style="Subtitle1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
        )
        self.title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        text_column.add_widget(self.title_label)

        self.time_label = MDLabel(
            text=datetime.now().strftime("%H:%M:%S - %d/%m/%Y"),
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
        )
        self.time_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        text_column.add_widget(self.time_label)

        top_row.add_widget(text_column)

        settings_btn = MDIconButton(
            icon="cog",
            theme_icon_color="Custom",
            icon_color=TEXT_PRIMARY,
            size_hint=(None, None),
            pos_hint={"center_y": 0.5},
        )
        settings_btn.bind(on_release=lambda *_: self.app_instance.navigate_to_screen("settings"))
        top_row.add_widget(settings_btn)

        info_card.add_widget(top_row)

        button_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(40),
        )

        button_row.add_widget(MDBoxLayout(size_hint_x=1))

        self.history_btn = MDRectangleFlatIconButton(
            text="Lịch sử",
            icon="book-open",
            text_color=TEXT_PRIMARY,
            line_color=TEXT_PRIMARY,
            size_hint=(None, None),
            height=dp(36),
            width=dp(110),
        )
        self.history_btn.bind(on_release=lambda *_: self.app_instance.navigate_to_screen("history"))
        button_row.add_widget(self.history_btn)

        self.emergency_btn = MDRectangleFlatIconButton(
            text="Khẩn cấp",
            icon="alert",
            text_color=MED_WARNING,
            line_color=MED_WARNING,
            size_hint=(None, None),
            height=dp(36),
            width=dp(120),
        )
        self.emergency_btn.bind(on_release=self._on_emergency_pressed)
        button_row.add_widget(self.emergency_btn)

        info_card.add_widget(button_row)

        parent.add_widget(info_card)

    def _create_measurement_grid(self, parent):
        grid = MDGridLayout(
            cols=2,
            spacing=dp(8),
            size_hint_y=None,
            row_default_height=dp(96),
            row_force_default=True,
            adaptive_height=True,
        )

        self.cardio_button = FeatureCard(
            title="Đo nhịp tim + SpO2",
            subtitle="Nhấn để đo trực tiếp",
            icon="heart-pulse",
            card_color=(0.47, 0.2, 0.4, 1),
        )
        self.cardio_button.bind(on_release=self._on_cardio_pressed)
        grid.add_widget(self.cardio_button)

        self.temp_button = FeatureCard(
            title="Đo nhiệt độ",
            subtitle="Đưa cảm biến gần trán",
            icon="thermometer",
            card_color=(0.16, 0.45, 0.4, 1),
        )
        self.temp_button.bind(on_release=self._on_temperature_pressed)
        grid.add_widget(self.temp_button)

        self.auto_button = FeatureCard(
            title="Chế độ tự động",
            subtitle="HR → SpO2 → Temp",
            icon="repeat",
            card_color=(0.24, 0.32, 0.52, 1),
        )
        self.auto_button.bind(on_release=self._on_auto_sequence_pressed)
        grid.add_widget(self.auto_button)

        self.bp_button = FeatureCard(
            title="Đo huyết áp",
            subtitle="Chờ phần cứng HX710B",
            icon="stethoscope",
            card_color=(0.45, 0.28, 0.18, 1),
        )
        self.bp_button.bind(on_release=self._on_bp_pressed)
        grid.add_widget(self.bp_button)

        parent.add_widget(grid)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_cardio_pressed(self, *_):
        self.logger.info("Cardio button pressed, navigating to heart rate screen")
        self.app_instance.navigate_to_screen("heart_rate")

    def _on_temperature_pressed(self, *_):
        self.app_instance.navigate_to_screen("temperature")

    def _on_auto_sequence_pressed(self, *_):
        self.logger.info("Auto-measure sequence requested")
        self.auto_button.update_state("--", "Đang chuẩn bị", subtitle="Giữ bệnh nhân ổn định")

    def _on_emergency_pressed(self, *_):
        self.logger.warning("Emergency button pressed from dashboard")

    def _on_bp_pressed(self, *_):
        self.logger.info("Blood pressure button pressed, navigating to BP measurement screen")
        self.app_instance.navigate_to_screen("bp_measurement")

    # ------------------------------------------------------------------
    # Data Management
    # ------------------------------------------------------------------

    def update_data(self, sensor_data: Dict[str, Any]):
        try:
            hr = sensor_data.get("heart_rate")
            spo2 = sensor_data.get("spo2")
            temp = sensor_data.get("object_temperature")

            cardio_values = []
            if hr and hr > 0:
                cardio_values.append(f"{hr:.0f} BPM")
            if spo2 and spo2 > 0:
                cardio_values.append(f"{spo2:.0f}% SpO2")

            if cardio_values:
                self.cardio_button.update_state("\n".join(cardio_values), "Đã đo", subtitle="Nhấn để xem chi tiết")
            else:
                self.cardio_button.update_state("--", "Nhấn để đo", subtitle="Nhấn để đo trực tiếp")

            # Luôn giữ ô nhiệt độ ở trạng thái chờ đo, không hiển thị giá trị
            self.temp_button.update_state("--", "Nhấn để đo", subtitle="Đưa cảm biến gần trán")

            systolic = sensor_data.get("blood_pressure_systolic")
            diastolic = sensor_data.get("blood_pressure_diastolic")
            if systolic and diastolic and systolic > 0 and diastolic > 0:
                value = f"{systolic:.0f}/{diastolic:.0f} mmHg"
                self.bp_button.update_state(value, "Đã đo", subtitle="Nhấn để xem chi tiết")
            else:
                self.bp_button.update_state("--", "Chờ phần cứng", subtitle="HX710B chưa sẵn sàng")

            if self.time_label:
                self.time_label.text = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")

        except Exception as exc:
            self.logger.error(f"Error updating dashboard data: {exc}")

    def get_sensor_summary(self) -> Dict[str, Any]:
        return {
            "all_normal": True,
            "warnings": [],
            "critical": [],
            "sensor_count": 3,
            "active_sensors": 0,
        }

    # ------------------------------------------------------------------
    # Screen Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self):
        self.logger.info("Dashboard screen entered")

    def on_leave(self):
        self.logger.info("Dashboard screen left")