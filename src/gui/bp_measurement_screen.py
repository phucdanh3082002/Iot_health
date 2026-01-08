"""
Blood Pressure Measurement Screen
Màn hình đo chi tiết cho huyết áp (oscillometric method)

Thiết kế cho người già:
- Chữ to, màu sắc rõ ràng (SYS/DIA lớn)
- Nút bấm lớn, dễ bấm
- Màu động theo ngưỡng AHA
- Sync style với temperature_screen.py
"""
import logging
import time
from typing import Optional

from kivy.uix.screenmanager import Screen
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDFillRoundFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.progressbar import MDProgressBar

from src.sensors.blood_pressure_sensor import BPState, BloodPressureMeasurement
from src.utils.tts_manager import ScenarioID


# ============================================================
# THEME COLORS - Màu sắc giao diện y tế (sync với temperature_screen)
# ============================================================
MED_BG_COLOR = (0.02, 0.18, 0.27, 1)       # Nền chính (xanh đậm)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)     # Nền card
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)     # Màu nhấn (xanh lục)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)        # Màu chính (xanh dương)
MED_WARNING = (0.96, 0.4, 0.3, 1)          # Cảnh báo (đỏ cam)
TEXT_PRIMARY = (1, 1, 1, 1)                # Chữ chính (trắng)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)         # Chữ phụ (xám nhạt)

# ============================================================
# HEALTH STATUS COLORS - Màu theo ngưỡng AHA (cho người già)
# ============================================================
COLOR_NORMAL = (0.3, 0.85, 0.4, 1)         # Xanh lá - Bình thường (<120/<80)
COLOR_ELEVATED = (1.0, 0.85, 0.2, 1)       # Vàng - Tăng cao (120-129/<80)
COLOR_STAGE1 = (1.0, 0.6, 0.2, 1)          # Cam - Tăng HA giai đoạn 1 (130-139/80-89)
COLOR_STAGE2 = (1.0, 0.4, 0.2, 1)          # Đỏ cam - Giai đoạn 2 (≥140/≥90)
COLOR_CRISIS = (1.0, 0.2, 0.2, 1)          # Đỏ đậm - Khủng hoảng (>180/>120)
COLOR_LOW = (0.3, 0.6, 0.95, 1)            # Xanh dương - Huyết áp thấp

# ============================================================
# BUTTON COLORS - Màu nút bấm nổi bật (sync với temperature_screen)
# ============================================================
BTN_START_COLOR = (0.1, 0.5, 0.7, 1)       # Xanh đậm - Bắt đầu
BTN_STOP_COLOR = (0.9, 0.35, 0.25, 1)      # Đỏ - Dừng/Xả khẩn
BTN_SAVE_COLOR = (0.2, 0.7, 0.4, 1)        # Xanh lá - Lưu
BTN_DISABLED_COLOR = (0.4, 0.4, 0.4, 1)    # Xám - Vô hiệu


class BPMeasurementScreen(Screen):
    """
    Màn hình đo chi tiết huyết áp theo phương pháp oscillometric
    
    Thiết kế tối ưu cho người già:
    - Giá trị SYS/DIA lớn, rõ ràng
    - Màu sắc thay đổi theo ngưỡng AHA
    - Nút bấm lớn, dễ thao tác
    - Layout đồng bộ với temperature_screen
    """
    
    # ------------------------------------------------------------------
    # Initialization & Lifecycle
    # ------------------------------------------------------------------
    
    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # Measurement state
        self.measuring = False
        self.current_state = BPState.IDLE
        self.current_pressure = 0.0
        self.last_result: Optional[BloodPressureMeasurement] = None
        
        # UI update scheduler
        self.update_event = None
        
        # TTS state tracking (announce only once per state transition)
        self._inflate_announced = False
        self._deflate_announced = False
        self._tts_on_enter_announced = False  # Tránh TTS lặp khi on_enter
        
        self._build_layout()
    
    # ------------------------------------------------------------------
    # UI Construction & Layout
    # ------------------------------------------------------------------
    
    def _build_layout(self):
        """Build BP measurement screen - sync với temperature_screen."""
        main_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(4),
            padding=(dp(6), dp(0), dp(6), dp(4)),
        )

        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)

        self._create_header(main_layout)
        self._create_measurement_panel(main_layout)
        self._create_secondary_results(main_layout)
        self._create_status_display(main_layout)
        self._create_controls(main_layout)

        self.add_widget(main_layout)
    
    def _update_bg(self, instance, value):
        self.bg_rect.size = instance.size
        self.bg_rect.pos = instance.pos
    
    def _create_header(self, parent):
        """Create header card - giống temperature_screen."""
        header_card = MDCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(54),
            padding=(dp(4), dp(6), dp(8), dp(6)),
            radius=[dp(14)],
            md_bg_color=MED_PRIMARY,
        )

        # Back button
        back_btn = MDIconButton(
            icon="arrow-left",
            theme_icon_color="Custom",
            icon_color=TEXT_PRIMARY,
            size_hint=(None, None),
            pos_hint={"center_y": 0.5},
        )
        back_btn.bind(on_release=self._on_back_pressed)
        header_card.add_widget(back_btn)

        # Title box
        title_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(0),
            size_hint_x=1,
            pos_hint={"center_y": 0.5},
        )

        title_label = MDLabel(
            text="HUYẾT ÁP",
            font_style="Subtitle1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="center",
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(title_label)

        subtitle_label = MDLabel(
            text="Quấn còng cách khuỷu tay 2cm",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="center",
        )
        subtitle_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(subtitle_label)

        header_card.add_widget(title_box)
        parent.add_widget(header_card)

    def _create_measurement_panel(self, parent):
        """
        Create measurement panel - 2 cột: Áp suất/Trạng thái (trái) + SYS/DIA lớn (phải).
        """
        panel_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(115),
            padding=(dp(4), dp(2), dp(4), dp(2)),
        )

        # ============================================================
        # LEFT: Pressure & State (cột trái - readings nhỏ)
        # ============================================================
        left_card = MDCard(
            orientation="vertical",
            size_hint_x=0.38,
            padding=(dp(6), dp(4), dp(6), dp(4)),
            spacing=dp(2),
            radius=[dp(12)],
            md_bg_color=MED_CARD_BG,
        )

        # Current Pressure Row
        pressure_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(48),
        )
        pressure_icon = MDIcon(
            icon="gauge-full",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(24), dp(24)),
        )
        pressure_icon.icon_size = dp(20)
        pressure_row.add_widget(pressure_icon)

        pressure_box = MDBoxLayout(orientation="vertical", spacing=dp(0), size_hint_x=1)
        pressure_label = MDLabel(
            text="Áp suất",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        pressure_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        pressure_box.add_widget(pressure_label)

        self.pressure_label = MDLabel(
            text="0 mmHg",
            font_style="H6",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            halign="left",
            valign="middle",
            bold=True,
        )
        self.pressure_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        pressure_box.add_widget(self.pressure_label)
        pressure_row.add_widget(pressure_box)
        left_card.add_widget(pressure_row)

        # State Row
        state_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(48),
        )
        state_icon = MDIcon(
            icon="pulse",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(24), dp(24)),
        )
        state_icon.icon_size = dp(20)
        state_row.add_widget(state_icon)

        state_box = MDBoxLayout(orientation="vertical", spacing=dp(0), size_hint_x=1)
        state_title = MDLabel(
            text="Trạng thái",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        state_title.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        state_box.add_widget(state_title)

        self.state_label = MDLabel(
            text="Chờ đo",
            font_style="Subtitle2",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
        )
        self.state_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        state_box.add_widget(self.state_label)
        state_row.add_widget(state_box)
        left_card.add_widget(state_row)

        panel_layout.add_widget(left_card)

        # ============================================================
        # RIGHT: Main Result Display - SYS/DIA (cột phải - giá trị LỚN)
        # ============================================================
        result_card = MDCard(
            orientation="vertical",
            size_hint_x=0.62,
            padding=(dp(8), dp(4), dp(8), dp(4)),
            spacing=dp(1),
            radius=[dp(12)],
            md_bg_color=MED_CARD_BG,
        )

        # Header với icon
        result_header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(18),
            spacing=dp(4),
        )
        result_icon = MDIcon(
            icon="heart",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(16), dp(16)),
        )
        result_icon.icon_size = dp(14)
        result_header.add_widget(result_icon)

        result_title = MDLabel(
            text="Kết quả",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        result_title.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        result_header.add_widget(result_title)
        result_card.add_widget(result_header)

        # Main BP value - SYS/DIA LỚN cho người già
        bp_value_box = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=1,
        )
        
        # SYS value
        self.sys_label = MDLabel(
            text="---",
            font_style="H4",
            halign="right",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            bold=True,
            size_hint_x=0.45,
        )
        self.sys_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        bp_value_box.add_widget(self.sys_label)
        
        # Separator "/"
        separator = MDLabel(
            text="/",
            font_style="H4",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            size_hint_x=0.1,
        )
        separator.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        bp_value_box.add_widget(separator)
        
        # DIA value
        self.dia_label = MDLabel(
            text="---",
            font_style="H4",
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            bold=True,
            size_hint_x=0.45,
        )
        self.dia_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        bp_value_box.add_widget(self.dia_label)
        
        result_card.add_widget(bp_value_box)

        # Unit label
        unit_label = MDLabel(
            text="mmHg",
            font_style="Caption",
            halign="center",
            valign="top",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            size_hint_y=None,
            height=dp(14),
        )
        unit_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        result_card.add_widget(unit_label)

        # Status label (Bình thường / Tăng cao / Cao...)
        self.bp_status_label = MDLabel(
            text="Chờ đo",
            font_style="Caption",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            size_hint_y=None,
            height=dp(16),
        )
        self.bp_status_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        result_card.add_widget(self.bp_status_label)

        panel_layout.add_widget(result_card)
        parent.add_widget(panel_layout)

    def _create_secondary_results(self, parent):
        """Create secondary results row: MAP + HR (compact)."""
        secondary_card = MDCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            padding=(dp(8), dp(4), dp(8), dp(4)),
            spacing=dp(12),
            radius=[dp(10)],
            md_bg_color=MED_CARD_BG,
        )

        # MAP
        map_box = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_x=0.5,
        )
        map_icon = MDIcon(
            icon="trending-up",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(20), dp(20)),
        )
        map_icon.icon_size = dp(16)
        map_box.add_widget(map_icon)

        map_text_box = MDBoxLayout(orientation="vertical", spacing=dp(0))
        map_title = MDLabel(
            text="MAP",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
        )
        map_title.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        map_text_box.add_widget(map_title)

        self.map_label = MDLabel(
            text="-- mmHg",
            font_style="Subtitle2",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            bold=True,
        )
        self.map_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        map_text_box.add_widget(self.map_label)
        map_box.add_widget(map_text_box)
        secondary_card.add_widget(map_box)

        # HR
        hr_box = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_x=0.5,
        )
        hr_icon = MDIcon(
            icon="heart-multiple",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(18), dp(20)),
        )
        hr_icon.icon_size = dp(16)
        hr_box.add_widget(hr_icon)

        hr_text_box = MDBoxLayout(orientation="vertical", spacing=dp(0))
        hr_title = MDLabel(
            text="Nhịp tim",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
        )
        hr_title.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        hr_text_box.add_widget(hr_title)

        self.hr_label = MDLabel(
            text="-- BPM",
            font_style="Subtitle2",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            bold=True,
        )
        self.hr_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        hr_text_box.add_widget(self.hr_label)
        hr_box.add_widget(hr_text_box)
        secondary_card.add_widget(hr_box)

        parent.add_widget(secondary_card)

    def _create_status_display(self, parent):
        """Create compact status display - giống temperature_screen."""
        status_card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(32),
            padding=(dp(6), dp(4), dp(6), dp(4)),
            spacing=dp(1),
            radius=[dp(10)],
            md_bg_color=MED_CARD_BG,
        )

        self.info_label = MDLabel(
            text="Sẵn sàng đo",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
        )
        self.info_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        status_card.add_widget(self.info_label)

        parent.add_widget(status_card)

    def _create_controls(self, parent):
        """
        Create control buttons - nút đặc màu sắc nổi bật cho người già.
        Sync style với temperature_screen (MDFillRoundFlatIconButton).
        """
        control_layout = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            spacing=dp(6),
            padding=(dp(4), dp(2), dp(4), dp(2)),
        )

        # Nút Bắt đầu - Màu xanh đậm nổi bật
        self.start_btn = MDFillRoundFlatIconButton(
            text="BẮT ĐẦU",
            icon="play-circle",
            md_bg_color=BTN_START_COLOR,
            text_color=TEXT_PRIMARY,
            icon_color=TEXT_PRIMARY,
            size_hint_x=0.4,
            font_size="14sp",
            icon_size="20sp",
        )
        self.start_btn.bind(on_press=self._start_measurement)
        control_layout.add_widget(self.start_btn)

        # Nút Xả khẩn - Màu đỏ
        self.stop_btn = MDFillRoundFlatIconButton(
            text="XẢ KHẨN",
            icon="alert-octagon",
            disabled=True,
            md_bg_color=BTN_DISABLED_COLOR,
            text_color=(1, 1, 1, 0.5),
            icon_color=(1, 1, 1, 0.5),
            size_hint_x=0.3,
            font_size="14sp",
            icon_size="20sp",
        )
        self.stop_btn.bind(on_press=self._stop_measurement)
        control_layout.add_widget(self.stop_btn)

        # Nút Lưu - Xám khi disabled, xanh lá khi enabled
        self.save_btn = MDFillRoundFlatIconButton(
            text="LƯU",
            icon="content-save",
            disabled=True,
            md_bg_color=BTN_DISABLED_COLOR,
            text_color=(1, 1, 1, 0.5),
            icon_color=(1, 1, 1, 0.5),
            size_hint_x=0.3,
            font_size="14sp",
            icon_size="20sp",
        )
        self.save_btn.bind(on_press=self._save_measurement)
        control_layout.add_widget(self.save_btn)

        parent.add_widget(control_layout)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_back_pressed(self, instance=None):
        """Handle back button press"""
        if self.measuring:
            self._stop_measurement()
        self.app_instance.navigate_to_screen('dashboard')
    
    # ------------------------------------------------------------------
    # Button Styling - Sync với temperature_screen
    # ------------------------------------------------------------------

    def _style_start_button(self, active: bool) -> None:
        """Style nút Bắt đầu với màu sắc nổi bật."""
        if active:
            self.start_btn.text = "ĐANG ĐO..."
            self.start_btn.icon = "loading"
            self.start_btn.md_bg_color = BTN_DISABLED_COLOR
            self.start_btn.text_color = (1, 1, 1, 0.5)
            self.start_btn.icon_color = (1, 1, 1, 0.5)
            self.start_btn.disabled = True
        else:
            self.start_btn.text = "BẮT ĐẦU"
            self.start_btn.icon = "play-circle"
            self.start_btn.md_bg_color = BTN_START_COLOR
            self.start_btn.text_color = TEXT_PRIMARY
            self.start_btn.icon_color = TEXT_PRIMARY
            self.start_btn.disabled = False

    def _style_stop_button(self, enabled: bool) -> None:
        """Style nút Xả khẩn - Đỏ khi enabled, xám khi disabled."""
        self.stop_btn.disabled = not enabled
        if enabled:
            self.stop_btn.md_bg_color = BTN_STOP_COLOR
            self.stop_btn.text_color = TEXT_PRIMARY
            self.stop_btn.icon_color = TEXT_PRIMARY
        else:
            self.stop_btn.md_bg_color = BTN_DISABLED_COLOR
            self.stop_btn.text_color = (1, 1, 1, 0.5)
            self.stop_btn.icon_color = (1, 1, 1, 0.5)

    def _style_save_button(self, enabled: bool) -> None:
        """Style nút Lưu - Xanh lá khi enabled, xám khi disabled."""
        self.save_btn.disabled = not enabled
        if enabled:
            self.save_btn.md_bg_color = BTN_SAVE_COLOR
            self.save_btn.text_color = TEXT_PRIMARY
            self.save_btn.icon_color = TEXT_PRIMARY
        else:
            self.save_btn.md_bg_color = BTN_DISABLED_COLOR
            self.save_btn.text_color = (1, 1, 1, 0.5)
            self.save_btn.icon_color = (1, 1, 1, 0.5)

    # ------------------------------------------------------------------
    # Dynamic Colors - Màu theo ngưỡng AHA
    # ------------------------------------------------------------------
    
    def _get_bp_color(self, sys: float, dia: float) -> tuple:
        """
        Lấy màu cho huyết áp theo ngưỡng AHA.
        
        Ngưỡng (theo AHA 2017):
        - SYS < 90 hoặc DIA < 60: Huyết áp thấp → Xanh dương
        - SYS < 120 và DIA < 80: Bình thường → Xanh lá
        - SYS 120-129 và DIA < 80: Tăng cao → Vàng
        - SYS 130-139 hoặc DIA 80-89: Giai đoạn 1 → Cam
        - SYS 140-179 hoặc DIA 90-119: Giai đoạn 2 → Đỏ cam
        - SYS ≥ 180 hoặc DIA ≥ 120: Khủng hoảng → Đỏ đậm
        """
        if sys < 90 or dia < 60:
            return COLOR_LOW
        elif sys < 120 and dia < 80:
            return COLOR_NORMAL
        elif sys < 130 and dia < 80:
            return COLOR_ELEVATED
        elif sys < 140 or dia < 90:
            return COLOR_STAGE1
        elif sys < 180 and dia < 120:
            return COLOR_STAGE2
        else:
            return COLOR_CRISIS
    
    def _get_bp_status_text(self, sys: float, dia: float) -> str:
        """Lấy text status cho huyết áp theo ngưỡng AHA."""
        if sys < 90 or dia < 60:
            return "Huyết áp thấp"
        elif sys < 120 and dia < 80:
            return "Bình thường"
        elif sys < 130 and dia < 80:
            return "Tăng cao"
        elif sys < 140 or dia < 90:
            return "Cao - Giai đoạn 1"
        elif sys < 180 and dia < 120:
            return "Cao - Giai đoạn 2"
        else:
            return "Khủng hoảng HA"

    # ------------------------------------------------------------------
    # Measurement Control
    # ------------------------------------------------------------------
    
    def _start_measurement(self, *args):
        """Start BP measurement"""
        try:
            bp_sensor = self.app_instance.sensors.get('BloodPressure')
            if not bp_sensor:
                self.logger.error("BloodPressure sensor not available")
                self._speak_scenario(ScenarioID.SENSOR_FAILURE, sensor="huyết áp")
                return
            
            if not self.app_instance.ensure_sensor_started('BloodPressure'):
                self.logger.error("Failed to start sensor")
                return
            
            self.measuring = True
            self.last_result = None
            
            # Update UI với styling mới
            self._style_start_button(active=True)
            self._style_stop_button(enabled=True)
            self._style_save_button(enabled=False)
            self.state_label.text = "Đang chuẩn bị..."
            
            # Clear results
            self.sys_label.text = "---"
            self.sys_label.text_color = TEXT_PRIMARY
            self.dia_label.text = "---"
            self.dia_label.text_color = TEXT_PRIMARY
            self.map_label.text = "-- mmHg"
            self.hr_label.text = "-- BPM"
            self.bp_status_label.text = "Đang đo..."
            self.bp_status_label.text_color = TEXT_MUTED
            
            # Reset TTS announce flags
            self._inflate_announced = False
            self._deflate_announced = False
            
            # Start measurement
            bp_sensor.start_measurement(callback=self._on_measurement_complete)
            
            # Start UI updates (5Hz)
            self.update_event = Clock.schedule_interval(self._update_ui, 0.2)
            
            # TTS will be announced when sensor enters INFLATING state (in _update_ui)
            
            self.logger.info("BP measurement started")
            
        except Exception as e:
            self.logger.error(f"Error starting: {e}")
            self._reset_ui()
    
    def _stop_measurement(self, *args):
        """Emergency stop - Xả khẩn cấp"""
        try:
            bp_sensor = self.app_instance.sensors.get('BloodPressure')
            if bp_sensor and hasattr(bp_sensor, 'stop_measurement'):
                bp_sensor.stop_measurement(emergency=True)
            
            self._reset_ui()
            self._speak_scenario(ScenarioID.SAFETY_EMERGENCY_RELEASE)
            self.info_label.text = "Đã xả khẩn cấp"
            self.logger.info("BP measurement stopped (emergency)")
            
        except Exception as e:
            self.logger.error(f"Error stopping: {e}")
    
    def _update_ui(self, dt):
        """Update UI with real-time data (called at 5Hz)"""
        try:
            bp_sensor = self.app_instance.sensors.get('BloodPressure')
            if not bp_sensor:
                return
            
            # Get current state from sensor (use method, not property)
            self.current_state = bp_sensor.get_state()
            
            # Get current pressure from sensor buffer (fallback if property doesn't exist)
            try:
                # Try to get pressure from buffer (last reading)
                if hasattr(bp_sensor, 'pressure_buffer') and len(bp_sensor.pressure_buffer) > 0:
                    self.current_pressure = bp_sensor.pressure_buffer[-1]
                else:
                    self.current_pressure = 0.0
            except (AttributeError, IndexError):
                self.current_pressure = 0.0
            
            # Update pressure display với đơn vị
            self.pressure_label.text = f"{self.current_pressure:.0f} mmHg"
            
            # Update state and progress
            state_map = {
                BPState.IDLE: ("Chờ đo", 0),
                BPState.INITIALIZING: ("Khởi động", 5),
                BPState.INFLATING: ("Đang bơm", 30),
                BPState.DEFLATING: ("Đang đo", 65),
                BPState.ANALYZING: ("Phân tích", 90),
                BPState.COMPLETED: ("Hoàn thành", 100),
                BPState.ERROR: ("Lỗi", 0),
                BPState.EMERGENCY_DEFLATE: ("Xả khẩn", 0)
            }
            
            state_text, progress_value = state_map.get(self.current_state, ("Không rõ", 0))
            self.state_label.text = state_text
            


            # Update info_label with instructions/safety messages based on state
            if self.current_state == BPState.IDLE:
                self.info_label.text = 'Nhấn "BẮT ĐẦU" để đo. Giữ yên tĩnh.'
            elif self.current_state == BPState.INITIALIZING:
                self.info_label.text = "Đang khởi động bơm và van..."
            elif self.current_state == BPState.INFLATING:
                self.info_label.text = "Đang bơm căng còng. Giữ tay yên."
            elif self.current_state == BPState.DEFLATING:
                self.info_label.text = "Đang xả áp và ghi nhận dao động..."
            elif self.current_state == BPState.ANALYZING:
                self.info_label.text = "Đang phân tích kết quả..."
            elif self.current_state == BPState.COMPLETED:
                self.info_label.text = "Đo hoàn tất. Xem kết quả bên dưới."
            elif self.current_state == BPState.ERROR:
                self.info_label.text = "Lỗi trong quá trình đo. Thử lại."
            elif self.current_state == BPState.EMERGENCY_DEFLATE:
                self.info_label.text = "Xả áp khẩn cấp đã kích hoạt."
            
            # TTS feedback at state transitions (announce only once per state)
            if self.current_state == BPState.INFLATING:
                if not self._inflate_announced:
                    self._speak_scenario(ScenarioID.BP_INFLATE)
                    self._inflate_announced = True
                    self.logger.debug("TTS: BP_INFLATE announced")
            
            if self.current_state == BPState.DEFLATING:
                if not self._deflate_announced:
                    self._speak_scenario(ScenarioID.BP_DEFLATE)
                    self._deflate_announced = True
                    self.logger.debug("TTS: BP_DEFLATE announced")
            
        except Exception as e:
            self.logger.error(f"Error updating UI: {e}", exc_info=True)
    
    def _on_measurement_complete(self, result: BloodPressureMeasurement):
        """
        Callback when measurement completes (called from sensor thread)
        
        IMPORTANT: This is called from the sensor's worker thread,
        so we MUST schedule UI updates on the main Kivy thread using Clock.schedule_once
        """
        self.logger.info(
            f"Measurement complete: SYS={result.systolic:.0f} DIA={result.diastolic:.0f} "
            f"MAP={result.map_value:.0f} HR={result.heart_rate:.0f} "
            f"Quality={result.quality} Confidence={result.confidence:.2f}"
        )
        
        # Schedule UI update on main thread
        Clock.schedule_once(lambda dt: self._handle_result_on_main_thread(result), 0)
    
    def _handle_result_on_main_thread(self, result: BloodPressureMeasurement):
        """
        Handle measurement result on main Kivy thread (safe for UI updates)
        
        This is called via Clock.schedule_once from _on_measurement_complete
        """
        try:
            # Stop UI update loop
            if self.update_event:
                self.update_event.cancel()
                self.update_event = None
            
            self.measuring = False
            self.last_result = result
            
            # Display results với màu động
            self._display_results(result)
            
            # TTS announcement với health warnings
            sys_int = int(round(result.systolic))
            dia_int = int(round(result.diastolic))
            map_int = int(round(result.map_value))
            
            # Determine appropriate TTS based on BP category
            if sys_int >= 180 or dia_int >= 120:
                # Hypertensive crisis - CRITICAL
                self._speak_scenario(ScenarioID.BP_HYPERTENSIVE_CRISIS, sys=sys_int, dia=dia_int)
            elif sys_int >= 140 or dia_int >= 90:
                # Stage 2 Hypertension - WARNING
                self._speak_scenario(ScenarioID.BP_HYPERTENSION, sys=sys_int, dia=dia_int)
            elif sys_int < 90 or dia_int < 60:
                # Hypotension - WARNING
                self._speak_scenario(ScenarioID.BP_HYPOTENSION, sys=sys_int, dia=dia_int)
            else:
                # Normal result with MAP
                self._speak_scenario(ScenarioID.BP_RESULT, sys=sys_int, dia=dia_int, map=map_int)
            
            # Update UI state với styling mới
            self.start_btn.text = "ĐO LẠI"
            self.start_btn.icon = "reload"
            self.start_btn.md_bg_color = BTN_START_COLOR
            self.start_btn.text_color = TEXT_PRIMARY
            self.start_btn.icon_color = TEXT_PRIMARY
            self.start_btn.disabled = False
            
            self._style_stop_button(enabled=False)
            self._style_save_button(enabled=True)
            
            self.state_label.text = "Hoàn thành"
            self.pressure_label.text = "0 mmHg"
            
        except Exception as e:
            self.logger.error(f"Error handling result on main thread: {e}", exc_info=True)
            # TTS: Thông báo lỗi
            self._speak_scenario(ScenarioID.SENSOR_FAILURE, sensor="huyết áp")
            # Schedule reset on main thread too
            Clock.schedule_once(lambda dt: self._reset_ui(), 0)
    
    def _display_results(self, result: BloodPressureMeasurement):
        """Display results with AHA color coding - màu động theo ngưỡng."""
        try:
            sys_val = result.systolic
            dia_val = result.diastolic
            
            # Lấy màu và status text theo ngưỡng AHA
            color = self._get_bp_color(sys_val, dia_val)
            status_text = self._get_bp_status_text(sys_val, dia_val)
            
            # Update SYS/DIA với màu động
            self.sys_label.text = f"{sys_val:.0f}"
            self.sys_label.text_color = color
            
            self.dia_label.text = f"{dia_val:.0f}"
            self.dia_label.text_color = color
            
            # Update MAP/HR
            self.map_label.text = f"{result.map_value:.0f} mmHg"
            self.hr_label.text = f"{result.heart_rate:.0f} BPM" if result.heart_rate else "-- BPM"
            
            # Update status label với màu
            self.bp_status_label.text = status_text
            self.bp_status_label.text_color = color
            
            self.logger.info(f"Displayed BP: {sys_val:.0f}/{dia_val:.0f} - {status_text}")
            
        except Exception as e:
            self.logger.error(f"Error displaying results: {e}")
    
    def _save_measurement(self, *args):
        """Save measurement to database"""
        try:
            if not self.last_result:
                self.logger.warning("No measurement to save")
                return
            
            measurement_data = {
                'timestamp': time.time(),
                'systolic': self.last_result.systolic,
                'diastolic': self.last_result.diastolic,
                'map_value': self.last_result.map_value,
                'heart_rate': self.last_result.heart_rate,
                'measurement_type': 'blood_pressure',
                'quality': self.last_result.quality,
                'confidence': self.last_result.confidence,
                # Add metadata for MQTT publishing
                'pulse_pressure': self.last_result.systolic - self.last_result.diastolic,
                'valid': True if self.last_result.quality in ['good', 'excellent'] else False
            }
            
            self.app_instance.save_measurement_to_database(measurement_data)
            
            self.app_instance.current_data['blood_pressure_systolic'] = self.last_result.systolic
            self.app_instance.current_data['blood_pressure_diastolic'] = self.last_result.diastolic
            
            # TTS: Announce measurement complete
            self._speak_scenario(ScenarioID.MEASUREMENT_COMPLETE)
            
            # Disable save button sau khi lưu
            self._style_save_button(enabled=False)
            self.info_label.text = "Đã lưu kết quả"
            self.logger.info("Measurement saved")
            
        except Exception as e:
            self.logger.error(f"Error saving: {e}")
    
    def _reset_ui(self):
        """Reset UI to idle state"""
        self.measuring = False
        self.current_state = BPState.IDLE
        self.current_pressure = 0.0
        
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None
        
        # Reset buttons với styling mới
        self._style_start_button(active=False)
        self._style_stop_button(enabled=False)
        self._style_save_button(enabled=False)
        
        self.state_label.text = "Chờ đo"
        self.pressure_label.text = "0 mmHg"
        self.info_label.text = 'Nhấn "BẮT ĐẦU" để đo huyết áp'
        
        # Clear results
        self.sys_label.text = "---"
        self.sys_label.text_color = TEXT_PRIMARY
        self.dia_label.text = "---"
        self.dia_label.text_color = TEXT_PRIMARY
        self.map_label.text = "-- mmHg"
        self.hr_label.text = "-- BPM"
        self.bp_status_label.text = "Chờ đo"
        self.bp_status_label.text_color = TEXT_MUTED
        
        # Reset TTS announce flags
        self._inflate_announced = False
        self._deflate_announced = False
        # Note: Không reset _tts_on_enter_announced ở đây vì nó được quản lý bởi on_enter/on_leave
    
    def _speak_scenario(self, scenario: ScenarioID, **kwargs):
        """Speak TTS scenario"""
        try:
            if hasattr(self.app_instance, '_speak_scenario'):
                self.app_instance._speak_scenario(scenario, **kwargs)
        except Exception as e:
            self.logger.debug(f"TTS not available: {e}")
    
    def on_enter(self):
        """Called when screen entered"""
        self._reset_ui()
        
        # TTS: Hướng dẫn chuẩn bị đo huyết áp (chỉ announce 1 lần)
        if not self._tts_on_enter_announced:
            Clock.schedule_once(lambda dt: self._speak_scenario(ScenarioID.MEASUREMENT_TIPS), 0.5)
            self._tts_on_enter_announced = True
            self.logger.debug("TTS announced: MEASUREMENT_TIPS")
        
        self.logger.info("Entered BP measurement screen")
    
    def on_leave(self):
        """Called when screen left"""
        if self.measuring:
            self._stop_measurement()
        
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None
        
        # Reset TTS flag để cho phép announce lại khi vào lần sau
        self._tts_on_enter_announced = False
        
        self.logger.info("Left BP measurement screen")
