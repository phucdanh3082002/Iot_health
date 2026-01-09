"""
Continuous Monitoring Screen
Màn hình giám sát liên tục cho HR/SpO2 realtime + BP tự động theo chu kỳ

Thiết kế cho người già:
- Chữ to, màu sắc rõ ràng
- Hiển thị realtime HR/SpO2 giống thiết bị y tế
- BP đo tự động mỗi 20 phút (có thể tùy chỉnh)
- Sync style với temperature_screen.py và heart_rate_screen.py
"""
from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from kivy.clock import Clock
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFillRoundFlatIconButton, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.progressbar import MDProgressBar

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
# HEALTH STATUS COLORS - Màu theo ngưỡng sức khỏe (cho người già)
# ============================================================
COLOR_HEALTHY = (0.3, 0.85, 0.4, 1)        # Xanh lá - Bình thường
COLOR_CAUTION = (1.0, 0.8, 0.2, 1)         # Vàng - Cần chú ý
COLOR_DANGER = (1.0, 0.3, 0.3, 1)          # Đỏ - Nguy hiểm
COLOR_NORMAL = (0.4, 0.75, 0.95, 1)        # Xanh dương nhạt - Bình thường

# ============================================================
# BUTTON COLORS - Màu nút bấm nổi bật (sync với temperature_screen)
# ============================================================
BTN_START_COLOR = (0.1, 0.5, 0.7, 1)       # Xanh đậm - Bắt đầu
BTN_STOP_COLOR = (0.9, 0.35, 0.25, 1)      # Đỏ - Dừng
BTN_SAVE_COLOR = (0.2, 0.7, 0.4, 1)        # Xanh lá - Lưu
BTN_DISABLED_COLOR = (0.4, 0.4, 0.4, 1)    # Xám - Vô hiệu

# ============================================================
# MONITORING PARAMETERS
# ============================================================
BP_AUTO_INTERVAL_MINUTES = 20  # Đo BP tự động mỗi 20 phút (chuẩn NIBP)
HR_SPO2_POLL_INTERVAL = 0.2    # 5Hz polling cho HR/SpO2 realtime
WAVEFORM_UPDATE_INTERVAL = 0.05  # 20Hz cho waveform mượt


class CompactWaveformWidget(Widget):
    """
    Widget hiển thị waveform PPG compact cho màn hình giám sát.
    Tối ưu cho không gian nhỏ, hiển thị ~3 giây dữ liệu.
    """
    
    RAW_BUFFER_SIZE = 300  # ~3 giây @ 100 SPS
    DISPLAY_POINTS = 80    # Số điểm hiển thị
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_points = []
        
        with self.canvas.before:
            Color(0.05, 0.15, 0.22, 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            
            Color(0.3, 0.4, 0.5, 0.15)
            self.grid_lines = []
            for _ in range(8):
                self.grid_lines.append(Line(points=[], width=0.5))
        
        with self.canvas:
            self.line_color = Color(*COLOR_HEALTHY)
            self.signal_line = Line(points=[], width=1.5)
        
        self.bind(size=self._update_layout, pos=self._update_layout)
    
    def _update_layout(self, *args):
        """Cập nhật layout khi resize."""
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        
        # Vẽ lưới đơn giản
        grid_idx = 0
        # Đường ngang (2 đường)
        for i in [1, 2]:
            if grid_idx < len(self.grid_lines):
                y = self.y + (i / 3) * self.height
                self.grid_lines[grid_idx].points = [self.x, y, self.x + self.width, y]
                grid_idx += 1
        
        # Đường dọc (4 đường)
        for i in range(1, 5):
            if grid_idx < len(self.grid_lines):
                x = self.x + (i / 5) * self.width
                self.grid_lines[grid_idx].points = [x, self.y, x, self.y + self.height]
                grid_idx += 1
        
        self._update_signal_line()
    
    def set_color(self, color: tuple) -> None:
        """Đặt màu đường sóng."""
        self.line_color.rgba = color
    
    def clear(self) -> None:
        """Xóa dữ liệu."""
        self.data_points = []
        self.signal_line.points = []
    
    def update_data(self, new_values: list) -> None:
        """Thêm batch dữ liệu mới."""
        if not new_values:
            return
        
        self.data_points.extend(new_values)
        if len(self.data_points) > self.RAW_BUFFER_SIZE:
            self.data_points = self.data_points[-self.RAW_BUFFER_SIZE:]
        
        self._update_signal_line()
    
    def _update_signal_line(self) -> None:
        """Cập nhật đường sóng."""
        if len(self.data_points) < 2:
            self.signal_line.points = []
            return
        
        # Downsample
        data = self.data_points
        if len(data) > self.DISPLAY_POINTS:
            step = len(data) / self.DISPLAY_POINTS
            data = [data[int(i * step)] for i in range(self.DISPLAY_POINTS)]
        
        if len(data) < 2:
            self.signal_line.points = []
            return
        
        # Auto scale
        min_val = min(data)
        max_val = max(data)
        rng = max_val - min_val
        if rng < 500:
            rng = 500
            mid = (min_val + max_val) / 2
            min_val = mid - 250
        
        # Tính tọa độ
        pts = []
        n_points = len(data)
        step_x = self.width / (n_points - 1) if n_points > 1 else self.width
        margin_y = self.height * 0.1
        drawable_height = self.height * 0.8
        
        for i, val in enumerate(data):
            x = self.x + i * step_x
            norm = (val - min_val) / rng if rng > 0 else 0.5
            y = self.y + margin_y + (norm * drawable_height)
            pts.extend([x, y])
        
        self.signal_line.points = pts


class ContinuousMonitorScreen(Screen):
    """
    Màn hình giám sát liên tục HR/SpO2 và BP tự động.
    
    Features:
    - HR/SpO2 realtime (5Hz polling)
    - Waveform PPG liên tục
    - BP tự động mỗi 20 phút
    - Countdown đến lần đo BP tiếp theo
    - Alert khi vượt ngưỡng
    """
    
    # States
    STATE_IDLE = "idle"
    STATE_MONITORING = "monitoring"
    STATE_BP_MEASURING = "bp_measuring"
    STATE_PAUSED = "paused"
    
    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # State
        self.state = self.STATE_IDLE
        self.monitoring_start_time: Optional[float] = None
        self.last_bp_time: Optional[float] = None
        self.next_bp_time: Optional[float] = None
        
        # Polling events (ClockEvent objects)
        self.hr_poll_event = None
        self.waveform_event = None
        self.bp_check_event = None
        self.ui_update_event = None
        
        # Latest data
        self.current_hr: int = 0
        self.current_spo2: int = 0
        self.current_bp_sys: int = 0
        self.current_bp_dia: int = 0
        self.finger_detected: bool = False
        
        # TTS lifecycle tracking
        self._tts_announced = False
        
        # ============================================================
        # MEDICAL-STANDARD AVERAGING (Weighted Moving Average)
        # ============================================================
        # Time-based windows theo ISO 80601-2-61 standards
        self.hr_window_seconds = 5.0      # 5 giây average cho HR
        self.spo2_window_seconds = 8.0    # 8 giây average cho SpO2
        
        # History buffers với timestamps
        self.hr_history = deque(maxlen=30)       # Max 30 samples @ 5Hz = 6s
        self.hr_timestamps = deque(maxlen=30)
        self.spo2_history = deque(maxlen=40)     # Max 40 samples @ 5Hz = 8s
        self.spo2_timestamps = deque(maxlen=40)
        
        # Display smoothing (EMA layer for smooth transitions)
        self.displayed_hr = 0.0
        self.displayed_spo2 = 0.0
        self.ema_alpha = 0.15  # Giảm từ 0.3 → 0.15 để display smooth hơn
        
        # Display thresholds - chỉ update UI khi thay đổi đáng kể
        self.hr_display_threshold = 2    # Chỉ update khi thay đổi >= 2 BPM
        self.spo2_display_threshold = 1  # Chỉ update khi thay đổi >= 1%
        self.last_displayed_hr = 0       # Giá trị HR đang hiển thị
        self.last_displayed_spo2 = 0     # Giá trị SpO2 đang hiển thị
        
        # ============================================================
        # ALARM SYSTEM (Hysteresis + Debouncing)
        # ============================================================
        # Warm-up period - không check alarm trong N giây đầu
        self.monitoring_start_time = 0   # Thời điểm bắt đầu monitoring
        self.WARMUP_PERIOD = 15.0        # 15 giây warm-up trước khi check alarms
        
        # Alarm state tracking
        self.hr_alarm_active = False
        self.spo2_alarm_active = False
        self.alarm_pending_time = {'hr_low': 0, 'spo2_low': 0, 'hr_high': 0}
        
        # Hysteresis thresholds (medical standard)
        self.THRESHOLDS = {
            'spo2_trigger': 90,   # Bật alarm khi SpO2 < 90%
            'spo2_clear': 92,     # Tắt alarm khi SpO2 >= 92%
            'hr_low_trigger': 50, # Bật alarm khi HR < 50 BPM
            'hr_low_clear': 55,   # Tắt alarm khi HR >= 55 BPM
            'hr_high_trigger': 120, # Bật alarm khi HR > 120 BPM
            'hr_high_clear': 115,   # Tắt alarm khi HR <= 115 BPM
        }
        self.DEBOUNCE_DELAY = 10.0  # 10 seconds delay before alarm (medical standard)
        
        # Build UI
        self._build_layout()
    
    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    
    def _build_layout(self):
        """Build layout tối ưu cho màn hình 480x320 nằm ngang."""
        main_layout = MDBoxLayout(
            orientation="vertical",
            spacing=dp(3),
            padding=(dp(5), dp(3), dp(5), dp(3)),
        )
        
        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self._bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)
        
        # Header
        self._create_header(main_layout)
        
        # Main content: HR/SpO2 + Waveform + BP
        self._create_vitals_display(main_layout)
        
        self.add_widget(main_layout)
    
    def _update_bg(self, instance, value):
        self._bg_rect.size = instance.size
        self._bg_rect.pos = instance.pos
    
    def _create_header(self, parent):
        """Create header card - sync style với temperature_screen."""
        header_card = MDCard(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            padding=(dp(6), 0, dp(12), 0),
            radius=[dp(18)],
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
            spacing=dp(1),
            size_hint_x=1,
        )

        title_label = MDLabel(
            text="GIÁM SÁT LIÊN TỤC",
            font_style="Subtitle1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(title_label)

        subtitle_label = MDLabel(
            text="HR/SpO2 realtime • BP tự động mỗi 20 phút",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
        )
        subtitle_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(subtitle_label)

        header_card.add_widget(title_box)
        
        # Status indicator (bên phải)
        self.status_label = MDLabel(
            text="Sẵn sàng",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="right",
            valign="center",
            size_hint_x=None,
            width=dp(80),
        )
        self.status_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        header_card.add_widget(self.status_label)
        
        parent.add_widget(header_card)
    
    def _create_vitals_display(self, parent):
        """Tạo khu vực hiển thị vital signs - Layout 2 cột với kích thước lớn hơn."""
        vitals_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(5),
            size_hint_y=1,  # Fill remaining space
        )
        
        # Left column: HR + SpO2 cards (stack dọc)
        left_column = MDBoxLayout(
            orientation="vertical",
            spacing=dp(5),
            size_hint_x=0.45,
        )
        
        # HR Card
        self.hr_card = self._create_vital_card(
            icon="heart-pulse",
            title="Nhịp tim",
            unit="BPM",
            card_color=(0.35, 0.15, 0.30, 0.95),
        )
        left_column.add_widget(self.hr_card)
        
        # SpO2 Card
        self.spo2_card = self._create_vital_card(
            icon="water-percent",
            title="SpO2",
            unit="%",
            card_color=(0.12, 0.35, 0.45, 0.95),
        )
        left_column.add_widget(self.spo2_card)
        
        vitals_layout.add_widget(left_column)
        
        # Right column: Waveform + BP stack
        right_column = MDBoxLayout(
            orientation="vertical",
            spacing=dp(5),
            size_hint_x=0.55,
        )
        
        # Waveform Card
        waveform_card = MDCard(
            orientation="vertical",
            md_bg_color=MED_CARD_BG,
            radius=[dp(10)],
            padding=dp(5),
            size_hint_y=0.55,
        )
        
        # Waveform title row
        wf_header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(20),
            spacing=dp(4),
        )
        wf_icon = MDIcon(
            icon="pulse",
            theme_text_color="Custom",
            text_color=COLOR_HEALTHY,
        )
        wf_icon.font_size = dp(14)
        wf_header.add_widget(wf_icon)
        
        wf_label = MDLabel(
            text="PPG",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
        )
        wf_header.add_widget(wf_label)
        waveform_card.add_widget(wf_header)
        
        # Waveform widget
        self.waveform = CompactWaveformWidget()
        waveform_card.add_widget(self.waveform)
        
        right_column.add_widget(waveform_card)
        
        # BP Card
        self.bp_card = self._create_bp_card()
        right_column.add_widget(self.bp_card)
        
        vitals_layout.add_widget(right_column)
        
        parent.add_widget(vitals_layout)
    
    def _create_vital_card(self, icon: str, title: str, unit: str, card_color: tuple) -> MDCard:
        """Tạo card hiển thị vital sign - Kích thước lớn hơn."""
        card = MDCard(
            orientation="vertical",
            md_bg_color=card_color,
            radius=[dp(10)],
            padding=(dp(8), dp(6)),
            spacing=dp(3),
        )
        
        # Title row với icon
        title_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(20),
            spacing=dp(4),
        )
        
        icon_widget = MDIcon(
            icon=icon,
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
        )
        icon_widget.font_size = dp(18)
        title_row.add_widget(icon_widget)
        
        title_label = MDLabel(
            text=title,
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            valign="center",
        )
        title_row.add_widget(title_label)
        
        card.add_widget(title_row)
        
        # Value - to, rõ ràng (center vertically)
        value_container = MDBoxLayout(
            orientation="vertical",
            size_hint_y=1,
        )
        
        # Spacer để center value
        value_container.add_widget(Widget(size_hint_y=0.2))
        
        value_label = MDLabel(
            text="--",
            font_style="H3",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            bold=True,
            halign="center",
            size_hint_y=None,
            height=dp(70),
        )
        value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        value_container.add_widget(value_label)
        
        # Unit label
        unit_label = MDLabel(
            text=unit,
            font_style="Body1",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=None,
            height=dp(22),
        )
        value_container.add_widget(unit_label)
        
        # Spacer
        value_container.add_widget(Widget(size_hint_y=0.2))
        
        card.add_widget(value_container)
        
        # Status label ở bottom
        status_label = MDLabel(
            text="Chờ đo",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=COLOR_NORMAL,
            halign="center",
            size_hint_y=None,
            height=dp(18),
        )
        card.add_widget(status_label)
        
        # Store references
        card.value_label = value_label
        card.status_label = status_label
        
        return card
    
    def _create_bp_card(self) -> MDCard:
        """Tạo card hiển thị BP với countdown."""
        card = MDCard(
            orientation="vertical",
            md_bg_color=(0.38, 0.22, 0.15, 0.95),
            radius=[dp(10)],
            padding=(dp(8), dp(5)),
            spacing=dp(3),
            size_hint_y=0.55,
        )
        
        # Title row với countdown
        title_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(18),
            spacing=dp(4),
        )
        
        icon_widget = MDIcon(
            icon="gauge",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
        )
        icon_widget.font_size = dp(13)
        title_row.add_widget(icon_widget)
        
        title_label = MDLabel(
            text="Huyết áp",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
        )
        title_row.add_widget(title_label)
        
        # Countdown label (right aligned)
        self.bp_countdown_label = MDLabel(
            text="",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="right",
            size_hint_x=0.5,
        )
        self.bp_countdown_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_row.add_widget(self.bp_countdown_label)
        
        card.add_widget(title_row)
        
        # Value row
        value_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(3),
            size_hint_y=None,
            height=dp(80),
        )
        
        # Systolic
        sys_box = MDBoxLayout(orientation="vertical", size_hint_x=0.45)
        self.bp_sys_label = MDLabel(
            text="---",
            font_style="H5",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            bold=True,
            halign="center",
            valign="center",
        )
        self.bp_sys_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        sys_box.add_widget(self.bp_sys_label)
        sys_hint = MDLabel(
            text="Tâm thu",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=None,
            height=dp(16),
        )
        sys_box.add_widget(sys_hint)
        value_row.add_widget(sys_box)
        
        # Separator
        sep = MDLabel(
            text="/",
            font_style="H5",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            valign="center",
            size_hint_x=0.1,
        )
        sep.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        value_row.add_widget(sep)
        
        # Diastolic
        dia_box = MDBoxLayout(orientation="vertical", size_hint_x=0.45)
        self.bp_dia_label = MDLabel(
            text="---",
            font_style="H5",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            bold=True,
            halign="center",
            valign="center",
        )
        self.bp_dia_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        dia_box.add_widget(self.bp_dia_label)
        dia_hint = MDLabel(
            text="Tâm trương",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=None,
            height=dp(16),
        )
        dia_box.add_widget(dia_hint)
        value_row.add_widget(dia_box)
        
        card.add_widget(value_row)
        
        # Status
        self.bp_status_label = MDLabel(
            text="Tự động mỗi 20 phút",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=COLOR_NORMAL,
            halign="center",
            size_hint_y=None,
            height=dp(16),
        )
        card.add_widget(self.bp_status_label)
        
        return card
    
    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------
    
    def _on_back_pressed(self, *args):
        """Quay về dashboard."""
        self._stop_monitoring()
        self.app_instance.navigate_to_screen("dashboard")
    
    # ------------------------------------------------------------------
    # Monitoring Control
    # ------------------------------------------------------------------
    
    def _start_monitoring(self):
        """Bắt đầu giám sát liên tục (tự động khi vào màn hình)."""
        self.logger.info("Starting continuous monitoring (auto)")
        
        # CRITICAL: Ensure sensor hardware started FIRST (turn on LED)
        # Giống heart_rate_screen.py controller flow
        try:
            if not self.app_instance.ensure_sensor_started('MAX30102'):
                self.logger.error("Failed to start MAX30102 sensor hardware")
                self._update_status("Lỗi: Không thể khởi động cảm biến", COLOR_DANGER)
                return
            self.logger.info("✓ MAX30102 hardware started (LED should be ON)")
        except Exception as e:
            self.logger.error(f"Exception starting sensor: {e}", exc_info=True)
            self._update_status("Lỗi: Không thể khởi động cảm biến", COLOR_DANGER)
            return
        
        # Start MAX30102 measurement session
        sensor = self.app_instance.sensors.get('MAX30102')
        if sensor:
            try:
                sensor.begin_measurement_session()
                self.logger.info("✓ MAX30102 measurement session started")
            except Exception as e:
                self.logger.error(f"Failed to begin measurement session: {e}", exc_info=True)
                self._update_status("Lỗi: Không thể bắt đầu session", COLOR_DANGER)
                return
        else:
            self.logger.warning("MAX30102 sensor not available in sensors dict")
            self._update_status("Lỗi: Không có cảm biến", COLOR_DANGER)
            return
        
        # Update state
        self.state = self.STATE_MONITORING
        self.monitoring_start_time = time.time()
        self.next_bp_time = time.time() + (BP_AUTO_INTERVAL_MINUTES * 60)
        
        # Update UI
        self._update_status("Đặt ngón tay lên cảm biến", TEXT_MUTED)
        
        # Start polling
        self.hr_poll_event = Clock.schedule_interval(
            self._poll_hr_spo2, HR_SPO2_POLL_INTERVAL
        )
        self.waveform_event = Clock.schedule_interval(
            self._update_waveform, WAVEFORM_UPDATE_INTERVAL
        )
        self.bp_check_event = Clock.schedule_interval(
            self._check_bp_schedule, 1.0
        )
        self.ui_update_event = Clock.schedule_interval(
            self._update_ui, 0.5
        )
        
        self.logger.info(f"✓ Polling started: HR/SpO2@{1/HR_SPO2_POLL_INTERVAL:.0f}Hz, Waveform@{1/WAVEFORM_UPDATE_INTERVAL:.0f}Hz")
        
        # TTS - Chỉ announce 1 lần khi vào screen (flag được set trong on_enter)
        # Không check flag ở đây để tránh lặp nếu _start_monitoring được gọi nhiều lần
        if not self._tts_announced:
            self.app_instance._speak_scenario(ScenarioID.CONTINUOUS_MONITOR_START)
            self._tts_announced = True
            self.logger.debug("✓ TTS announced: CONTINUOUS_MONITOR_START")
    
    def _stop_monitoring(self):
        """Dừng giám sát."""
        self.logger.info("Stopping continuous monitoring")
        
        # Stop MAX30102 session
        sensor = self.app_instance.sensors.get('MAX30102')
        if sensor:
            sensor.end_measurement_session()
        
        # Cancel all events
        if self.hr_poll_event:
            self.hr_poll_event.cancel()
            self.hr_poll_event = None
        if self.waveform_event:
            self.waveform_event.cancel()
            self.waveform_event = None
        if self.bp_check_event:
            self.bp_check_event.cancel()
            self.bp_check_event = None
        if self.ui_update_event:
            self.ui_update_event.cancel()
            self.ui_update_event = None
        
        # Update state
        self.state = self.STATE_IDLE
        self.next_bp_time = None
        
        # Reset averaging buffers và alarm states
        self.hr_history.clear()
        self.hr_timestamps.clear()
        self.spo2_history.clear()
        self.spo2_timestamps.clear()
        self.displayed_hr = 0.0
        self.displayed_spo2 = 0.0
        self.last_displayed_hr = 0
        self.last_displayed_spo2 = 0
        self.monitoring_start_time = 0
        self.hr_alarm_active = False
        self.spo2_alarm_active = False
        self.alarm_pending_time = {'hr_low': 0, 'spo2_low': 0, 'hr_high': 0}
        
        # Update UI
        self._update_status("Đã dừng", TEXT_MUTED)
        self.bp_countdown_label.text = ""
    
    # ------------------------------------------------------------------
    # Polling & Data Update
    # ------------------------------------------------------------------
    
    def _calculate_weighted_average(self, values, timestamps, window_seconds):
        """
        Tính weighted average với recent values có trọng số cao hơn.
        
        Medical-standard weighting:
        - Exponential decay: recent values = high weight, old = low weight
        - Weight formula: w = e^(-age/tau) với tau = window/3
        - Values ngoài window_seconds bị loại bỏ
        
        Args:
            values: List giá trị (HR hoặc SpO2)
            timestamps: List timestamps tương ứng
            window_seconds: Time window (5s cho HR, 8s cho SpO2)
        
        Returns:
            Weighted average value hoặc None nếu không đủ data
        """
        if not values or not timestamps:
            return None
        
        now = time.time()
        cutoff = now - window_seconds
        
        # Filter only values within window
        valid_pairs = [(v, ts) for v, ts in zip(values, timestamps) 
                       if ts >= cutoff]
        
        if not valid_pairs:
            return None
        
        # Sort by time (oldest first)
        valid_pairs.sort(key=lambda x: x[1])
        
        # Calculate exponential decay weights
        weights = []
        tau = window_seconds / 3.0  # Time constant
        
        for _, ts in valid_pairs:
            age = now - ts  # Age of reading (seconds)
            # Exponential decay: w = e^(-age/tau)
            w = 2.71828 ** (-age / tau)
            weights.append(w)
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight == 0:
            # Fallback to simple average
            return sum(v for v, _ in valid_pairs) / len(valid_pairs)
        
        weights = [w / total_weight for w in weights]
        
        # Weighted average
        weighted_sum = sum(v * w for (v, _), w in zip(valid_pairs, weights))
        
        return weighted_sum
    
    def _poll_hr_spo2(self, dt):
        """
        Poll HR/SpO2 từ MAX30102 với medical-standard averaging.
        
        Implementation:
        - 5-second weighted average cho HR (ISO 80601-2-61)
        - 8-second weighted average cho SpO2
        - EMA smoothing cho display transitions
        - Hysteresis + debouncing cho alarms
        """
        if self.state not in (self.STATE_MONITORING, self.STATE_BP_MEASURING):
            return
        
        try:
            # Get sensor data từ app_instance
            sensor_data = self.app_instance.get_sensor_data()
            if not sensor_data:
                return
            
            # Extract MAX30102 status
            sensor_status = sensor_data.get('sensor_status', {})
            max_status = sensor_status.get('MAX30102', {})
            
            # RAW values từ sensor (chưa smooth)
            raw_hr = int(sensor_data.get('heart_rate', 0) or 0)
            raw_spo2 = int(sensor_data.get('spo2', 0) or 0)
            self.finger_detected = bool(
                max_status.get('finger_detected', False) or 
                sensor_data.get('finger_detected', False)
            )
            
            now = time.time()
            
            # ============================================================
            # HR: 5-SECOND WEIGHTED MOVING AVERAGE
            # ============================================================
            if raw_hr > 0 and self.finger_detected:
                # Add to time-stamped history
                self.hr_history.append(float(raw_hr))
                self.hr_timestamps.append(now)
                
                # Calculate 5-second weighted average
                avg_hr = self._calculate_weighted_average(
                    self.hr_history, 
                    self.hr_timestamps,
                    self.hr_window_seconds
                )
                
                if avg_hr is not None:
                    # Apply EMA for smooth display transition
                    if self.displayed_hr == 0:
                        self.displayed_hr = avg_hr
                    else:
                        self.displayed_hr = (
                            self.ema_alpha * avg_hr +
                            (1 - self.ema_alpha) * self.displayed_hr
                        )
                    
                    # Display threshold: chỉ update khi thay đổi đáng kể
                    new_hr = int(round(self.displayed_hr))
                    if abs(new_hr - self.last_displayed_hr) >= self.hr_display_threshold:
                        self.current_hr = new_hr
                        self.last_displayed_hr = new_hr
                    elif self.last_displayed_hr == 0:
                        # Lần đầu - luôn update
                        self.current_hr = new_hr
                        self.last_displayed_hr = new_hr
                    # Nếu thay đổi < threshold, giữ nguyên current_hr
                    
                    # Debug logging
                    n_samples = len([t for t in self.hr_timestamps if now - t <= self.hr_window_seconds])
                    self.logger.debug(
                        f"[HR] Raw={raw_hr}, 5s_WMA={avg_hr:.1f}, "
                        f"Display={self.current_hr}, Samples={n_samples}"
                    )
            else:
                # No finger or invalid reading
                self.current_hr = 0
                self.displayed_hr = 0.0
            
            # ============================================================
            # SPO2: 8-SECOND WEIGHTED MOVING AVERAGE
            # ============================================================
            if raw_spo2 > 0 and self.finger_detected:
                # Add to time-stamped history
                self.spo2_history.append(float(raw_spo2))
                self.spo2_timestamps.append(now)
                
                # Calculate 8-second weighted average
                avg_spo2 = self._calculate_weighted_average(
                    self.spo2_history,
                    self.spo2_timestamps,
                    self.spo2_window_seconds
                )
                
                if avg_spo2 is not None:
                    # Apply EMA for smooth display transition
                    if self.displayed_spo2 == 0:
                        self.displayed_spo2 = avg_spo2
                    else:
                        self.displayed_spo2 = (
                            self.ema_alpha * avg_spo2 +
                            (1 - self.ema_alpha) * self.displayed_spo2
                        )
                    
                    # Display threshold: chỉ update khi thay đổi đáng kể
                    new_spo2 = int(round(self.displayed_spo2))
                    if abs(new_spo2 - self.last_displayed_spo2) >= self.spo2_display_threshold:
                        self.current_spo2 = new_spo2
                        self.last_displayed_spo2 = new_spo2
                    elif self.last_displayed_spo2 == 0:
                        # Lần đầu - luôn update
                        self.current_spo2 = new_spo2
                        self.last_displayed_spo2 = new_spo2
                    # Nếu thay đổi < threshold, giữ nguyên current_spo2
                    
                    # Debug logging
                    n_samples = len([t for t in self.spo2_timestamps if now - t <= self.spo2_window_seconds])
                    self.logger.debug(
                        f"[SpO2] Raw={raw_spo2}, 8s_WMA={avg_spo2:.1f}, "
                        f"Display={self.current_spo2}, Samples={n_samples}"
                    )
            else:
                # No finger or invalid reading
                self.current_spo2 = 0
                self.displayed_spo2 = 0.0
            
            # Update displays
            self._update_hr_display()
            self._update_spo2_display()
            
            # Check alarms với hysteresis + debouncing
            self._check_alarms_with_hysteresis()
            
        except Exception as e:
            self.logger.error(f"Error polling HR/SpO2: {e}", exc_info=True)
    
    def _check_alarms_with_hysteresis(self):
        """
        Check và trigger alarms với hysteresis + time-based debouncing.
        
        Medical Standard (ISO 80601-2-61):
        - SpO2 < 90%: 10 seconds delay before alarm (hysteresis: clear at 92%)
        - HR < 50 or > 120: 10 seconds delay (hysteresis: clear at 55/115)
        - Hysteresis prevents alarm oscillation
        - Debouncing prevents false alarms from transient spikes
        - Warm-up period: không check alarm trong 15 giây đầu
        """
        if self.current_hr == 0 and self.current_spo2 == 0:
            # No valid data - skip alarm checking
            return
        
        now = time.time()
        
        # ============================================================
        # WARM-UP PERIOD CHECK
        # ============================================================
        # Không check alarms trong N giây đầu để giá trị ổn định
        if self.monitoring_start_time > 0:
            warmup_elapsed = now - self.monitoring_start_time
            if warmup_elapsed < self.WARMUP_PERIOD:
                # Vẫn trong warm-up period - skip alarm checking
                self.logger.debug(
                    f"[WARMUP] Còn {self.WARMUP_PERIOD - warmup_elapsed:.1f}s "
                    f"trước khi check alarms"
                )
                return
        
        # ============================================================
        # SPO2 LOW ALARM (với hysteresis + debouncing)
        # ============================================================
        if self.current_spo2 > 0:
            if self.current_spo2 < self.THRESHOLDS['spo2_trigger']:
                # SpO2 thấp - bắt đầu đếm thời gian
                if self.alarm_pending_time['spo2_low'] == 0:
                    self.alarm_pending_time['spo2_low'] = now
                    self.logger.info(
                        f"[ALARM PENDING] SpO2 low: {self.current_spo2}% < {self.THRESHOLDS['spo2_trigger']}%"
                    )
                
                # Kiểm tra xem đã đủ delay chưa
                elapsed = now - self.alarm_pending_time['spo2_low']
                if elapsed >= self.DEBOUNCE_DELAY and not self.spo2_alarm_active:
                    # Trigger alarm
                    self.spo2_alarm_active = True
                    self.logger.warning(
                        f"🚨 [ALARM TRIGGERED] SpO2 LOW: {self.current_spo2}% "
                        f"(sustained {elapsed:.1f}s)"
                    )
                    # TTS alert (TODO: Add ALERT_SPO2_LOW to ScenarioID)
                    # For now, use generic anomaly detection
                    try:
                        self.app_instance._speak_scenario(ScenarioID.ANOMALY_DETECTED)
                    except:
                        pass
            
            elif self.current_spo2 >= self.THRESHOLDS['spo2_clear']:
                # SpO2 đã hồi phục - clear alarm (hysteresis zone)
                self.alarm_pending_time['spo2_low'] = 0
                
                if self.spo2_alarm_active:
                    self.spo2_alarm_active = False
                    self.logger.info(
                        f"✅ [ALARM CLEARED] SpO2 recovered: {self.current_spo2}% >= {self.THRESHOLDS['spo2_clear']}%"
                    )
            
            # Nếu SpO2 dao động trong hysteresis zone (90-92%), giữ nguyên trạng thái
        
        # ============================================================
        # HR LOW ALARM (với hysteresis + debouncing)
        # ============================================================
        if self.current_hr > 0:
            if self.current_hr < self.THRESHOLDS['hr_low_trigger']:
                # HR thấp - bắt đầu đếm thời gian
                if self.alarm_pending_time['hr_low'] == 0:
                    self.alarm_pending_time['hr_low'] = now
                    self.logger.info(
                        f"[ALARM PENDING] HR low: {self.current_hr} BPM < {self.THRESHOLDS['hr_low_trigger']} BPM"
                    )
                
                # Kiểm tra delay
                elapsed = now - self.alarm_pending_time['hr_low']
                if elapsed >= self.DEBOUNCE_DELAY and not self.hr_alarm_active:
                    # Note: hr_alarm_active dùng chung cho cả low/high, cần refactor nếu muốn riêng
                    self.hr_alarm_active = True
                    self.logger.warning(
                        f"🚨 [ALARM TRIGGERED] HR LOW: {self.current_hr} BPM "
                        f"(sustained {elapsed:.1f}s)"
                    )
                    # TTS alert (TODO: Add ALERT_HR_ABNORMAL to ScenarioID)
                    try:
                        self.app_instance._speak_scenario(ScenarioID.ANOMALY_DETECTED)
                    except:
                        pass
            
            elif self.current_hr >= self.THRESHOLDS['hr_low_clear']:
                # HR hồi phục
                self.alarm_pending_time['hr_low'] = 0
                
                if self.hr_alarm_active and self.alarm_pending_time['hr_high'] == 0:
                    # Chỉ clear nếu không có HR high alarm pending
                    self.hr_alarm_active = False
                    self.logger.info(
                        f"✅ [ALARM CLEARED] HR recovered: {self.current_hr} BPM >= {self.THRESHOLDS['hr_low_clear']} BPM"
                    )
        
        # ============================================================
        # HR HIGH ALARM (với hysteresis + debouncing)
        # ============================================================
        if self.current_hr > 0:
            if self.current_hr > self.THRESHOLDS['hr_high_trigger']:
                # HR cao - bắt đầu đếm thời gian
                if self.alarm_pending_time['hr_high'] == 0:
                    self.alarm_pending_time['hr_high'] = now
                    self.logger.info(
                        f"[ALARM PENDING] HR high: {self.current_hr} BPM > {self.THRESHOLDS['hr_high_trigger']} BPM"
                    )
                
                # Kiểm tra delay
                elapsed = now - self.alarm_pending_time['hr_high']
                if elapsed >= self.DEBOUNCE_DELAY and not self.hr_alarm_active:
                    self.hr_alarm_active = True
                    self.logger.warning(
                        f"🚨 [ALARM TRIGGERED] HR HIGH: {self.current_hr} BPM "
                        f"(sustained {elapsed:.1f}s)"
                    )
                    # TTS alert (TODO: Add ALERT_HR_ABNORMAL to ScenarioID)
                    try:
                        self.app_instance._speak_scenario(ScenarioID.ANOMALY_DETECTED)
                    except:
                        pass
            
            elif self.current_hr <= self.THRESHOLDS['hr_high_clear']:
                # HR giảm về bình thường
                self.alarm_pending_time['hr_high'] = 0
                
                if self.hr_alarm_active and self.alarm_pending_time['hr_low'] == 0:
                    # Chỉ clear nếu không có HR low alarm pending
                    self.hr_alarm_active = False
                    self.logger.info(
                        f"✅ [ALARM CLEARED] HR recovered: {self.current_hr} BPM <= {self.THRESHOLDS['hr_high_clear']} BPM"
                    )
    
    def _update_waveform(self, dt):
        """Cập nhật waveform từ MAX30102 (20Hz)."""
        if self.state not in (self.STATE_MONITORING, self.STATE_BP_MEASURING):
            return
        
        sensor = self.app_instance.sensors.get('MAX30102')
        if not sensor:
            return
        
        try:
            # Get visual samples for waveform
            samples = sensor.pop_visual_samples()
            if samples:
                self.waveform.update_data(samples)
        except Exception as e:
            self.logger.error(f"Error updating waveform: {e}")
    
    def _check_bp_schedule(self, dt):
        """Kiểm tra xem đã đến lúc đo BP chưa (1Hz)."""
        if self.state != self.STATE_MONITORING:
            return
        
        if self.next_bp_time and time.time() >= self.next_bp_time:
            self._trigger_bp_measurement()
    
    def _update_ui(self, dt):
        """Cập nhật UI elements (0.5Hz)."""
        if self.state == self.STATE_IDLE:
            return
        
        # Update BP countdown
        if self.next_bp_time and self.state == self.STATE_MONITORING:
            remaining = self.next_bp_time - time.time()
            if remaining > 0:
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                self.bp_countdown_label.text = f"{mins:02d}:{secs:02d}"
            else:
                self.bp_countdown_label.text = "Đang đo..."
    
    # ------------------------------------------------------------------
    # Display Updates
    # ------------------------------------------------------------------
    
    def _update_hr_display(self):
        """Cập nhật hiển thị nhịp tim."""
        if not self.finger_detected:
            self.hr_card.value_label.text = "--"
            self.hr_card.status_label.text = "Đặt ngón tay"
            self.hr_card.status_label.text_color = TEXT_MUTED
            self._update_status("Đặt ngón tay lên cảm biến", TEXT_MUTED)
            return
        
        # Debug log khi phát hiện ngón tay
        if self.current_hr > 0:
            self.logger.debug(f"Finger detected: HR={self.current_hr}, SpO2={self.current_spo2}")
        
        if self.current_hr > 0:
            self.hr_card.value_label.text = str(int(self.current_hr))
            
            # Color by health status
            if 60 <= self.current_hr <= 100:
                color = COLOR_HEALTHY
                status = "Bình thường"
            elif 50 <= self.current_hr < 60 or 100 < self.current_hr <= 110:
                color = COLOR_CAUTION
                status = "Cần chú ý"
            else:
                color = COLOR_DANGER
                status = "Bất thường"
            
            self.hr_card.status_label.text = status
            self.hr_card.status_label.text_color = color
            self.waveform.set_color(color)
            self._update_status("Đang giám sát", COLOR_HEALTHY)
        else:
            self.hr_card.value_label.text = "--"
            self.hr_card.status_label.text = "Đang đo..."
            self.hr_card.status_label.text_color = COLOR_NORMAL
    
    def _update_spo2_display(self):
        """Cập nhật hiển thị SpO2."""
        if not self.finger_detected:
            self.spo2_card.value_label.text = "--"
            self.spo2_card.status_label.text = "Đặt ngón tay"
            self.spo2_card.status_label.text_color = TEXT_MUTED
            return
        
        if self.current_spo2 > 0:
            self.spo2_card.value_label.text = str(int(self.current_spo2))
            
            # Color by health status
            if self.current_spo2 >= 95:
                color = COLOR_HEALTHY
                status = "Bình thường"
            elif 90 <= self.current_spo2 < 95:
                color = COLOR_CAUTION
                status = "Hơi thấp"
            else:
                color = COLOR_DANGER
                status = "Nguy hiểm"
            
            self.spo2_card.status_label.text = status
            self.spo2_card.status_label.text_color = color
        else:
            self.spo2_card.value_label.text = "--"
            self.spo2_card.status_label.text = "Đang đo..."
            self.spo2_card.status_label.text_color = COLOR_NORMAL
    
    def _update_bp_display(self, systolic: int, diastolic: int):
        """Cập nhật hiển thị huyết áp."""
        self.current_bp_sys = systolic
        self.current_bp_dia = diastolic
        
        self.bp_sys_label.text = str(systolic) if systolic > 0 else "---"
        self.bp_dia_label.text = str(diastolic) if diastolic > 0 else "---"
        
        # Color by health status
        if systolic > 0 and diastolic > 0:
            if systolic < 120 and diastolic < 80:
                status = "Bình thường"
                color = COLOR_HEALTHY
            elif systolic < 140 and diastolic < 90:
                status = "Tăng nhẹ"
                color = COLOR_CAUTION
            else:
                status = "Tăng cao"
                color = COLOR_DANGER
            
            self.bp_status_label.text = status
            self.bp_status_label.text_color = color
    
    def _update_status(self, text: str, color: tuple = TEXT_MUTED):
        """Cập nhật status label."""
        self.status_label.text = text
        self.status_label.text_color = color
    
    # ------------------------------------------------------------------
    # BP Measurement
    # ------------------------------------------------------------------
    
    def _trigger_bp_measurement(self):
        """Kích hoạt đo huyết áp."""
        self.logger.info("Triggering BP measurement")
        
        self.state = self.STATE_BP_MEASURING
        self.bp_status_label.text = "Đang đo..."
        self.bp_status_label.text_color = MED_PRIMARY
        
        # TTS thông báo
        self.app_instance._speak_scenario(ScenarioID.BP_READY)
        
        # Start BP measurement via sensor
        bp_sensor = self.app_instance.sensors.get('BloodPressure')
        if bp_sensor:
            # Register callback for BP result
            bp_sensor.set_callback(self._on_bp_measurement_complete)
            bp_sensor.start_measurement()
        else:
            self.logger.warning("BP sensor not available")
            self._on_bp_measurement_complete({
                'success': False,
                'error': 'Không có cảm biến huyết áp'
            })
    
    def _on_bp_measurement_complete(self, result: Dict[str, Any]):
        """Callback khi đo BP hoàn tất."""
        self.logger.info(f"BP measurement complete: {result}")
        
        if result.get('success', False):
            systolic = result.get('systolic', 0)
            diastolic = result.get('diastolic', 0)
            self._update_bp_display(systolic, diastolic)
            
            # TTS result
            self.app_instance._speak_scenario(ScenarioID.BP_RESULT)
            
            # Auto-save BP data
            self._auto_save_data()
            
            # Schedule next BP
            self.last_bp_time = time.time()
            self.next_bp_time = time.time() + (BP_AUTO_INTERVAL_MINUTES * 60)
        else:
            error = result.get('error', 'Lỗi không xác định')
            self.bp_status_label.text = f"Lỗi: {error}"
            self.bp_status_label.text_color = COLOR_DANGER
            
            # Retry sooner on error (5 minutes)
            self.next_bp_time = time.time() + (5 * 60)
        
        # Return to monitoring state
        self.state = self.STATE_MONITORING
    
    # ------------------------------------------------------------------
    # Data Persistence (Auto-save)
    # ------------------------------------------------------------------
    
    def _auto_save_data(self):
        """Tự động lưu dữ liệu khi có kết quả tốt (gọi từ BP callback hoặc định kỳ)."""
        self.logger.debug("Auto-saving monitoring data")
        
        try:
            timestamp = datetime.now()
            
            # Save via app's database
            if self.app_instance.database:
                # Save HR/SpO2 nếu có giá trị hợp lệ
                if self.current_hr > 0 and self.current_spo2 > 0:
                    self.app_instance.database.save_cardio_reading(
                        heart_rate=self.current_hr,
                        spo2=self.current_spo2,
                        measurement_type='continuous_monitor',
                        timestamp=timestamp,
                    )
                    self.logger.info(f"Auto-saved HR/SpO2: {self.current_hr}/{self.current_spo2}")
                
                # Save BP nếu có giá trị hợp lệ
                if self.current_bp_sys > 0 and self.current_bp_dia > 0:
                    self.app_instance.database.save_blood_pressure_reading(
                        systolic=self.current_bp_sys,
                        diastolic=self.current_bp_dia,
                        measurement_type='continuous_monitor',
                        timestamp=timestamp,
                    )
                    self.logger.info(f"Auto-saved BP: {self.current_bp_sys}/{self.current_bp_dia}")
                
                self._update_status("Đã lưu tự động", COLOR_HEALTHY)
                
                # Reset status after 2 seconds
                Clock.schedule_once(
                    lambda dt: self._update_status("Đang giám sát", COLOR_HEALTHY) if self.finger_detected else self._update_status("Đặt ngón tay lên cảm biến", TEXT_MUTED),
                    2.0
                )
            else:
                self.logger.warning("Database not available")
                
        except Exception as e:
            self.logger.error(f"Error auto-saving data: {e}")
    
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    
    def on_enter(self):
        """Khi vào màn hình - Tự động bắt đầu giám sát."""
        self.logger.info("Entering ContinuousMonitorScreen")
        
        # CRITICAL: Reset TTS flag ở đây để announce khi vào screen
        # Flag sẽ được set True trong _start_monitoring sau khi TTS phát
        self._tts_announced = False
        
        # Reset displays
        self.waveform.clear()
        self.hr_card.value_label.text = "--"
        self.hr_card.status_label.text = "Đặt ngón tay"
        self.spo2_card.value_label.text = "--"
        self.spo2_card.status_label.text = "Đặt ngón tay"
        self.bp_sys_label.text = "---"
        self.bp_dia_label.text = "---"
        self.bp_status_label.text = "Tự động mỗi 20 phút"
        self.bp_countdown_label.text = ""
        self._update_status("Đặt ngón tay lên cảm biến", TEXT_MUTED)
        
        # Tự động bắt đầu giám sát
        self._start_monitoring()
    
    def on_leave(self):
        """Khi rời màn hình - Dừng giám sát, tắt sensor và LED."""
        self.logger.info("Leaving ContinuousMonitorScreen")
        
        # KHÔNG reset TTS flag ở đây - sẽ reset trong on_enter khi vào lại
        # Giữ flag = True để tránh TTS lặp nếu có sự kiện sau on_leave
        
        # Stop monitoring và cancel tất cả polling events
        self._stop_monitoring()
        
        # Stop MAX30102 sensor hardware (tắt LED)
        try:
            self.app_instance.stop_sensor("MAX30102")
            self.logger.info("✓ MAX30102 sensor stopped (LED OFF)")
        except Exception as e:
            self.logger.warning(f"Failed to stop MAX30102: {e}")
        
        # Clear waveform display
        self.waveform.clear()
