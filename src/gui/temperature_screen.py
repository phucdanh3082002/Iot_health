"""
Temperature Measurement Screen
Màn hình đo chi tiết cho MLX90614 (nhiệt độ)

Thiết kế cho người già:
- Chữ to, màu sắc rõ ràng
- Nút bấm lớn, dễ bấm
- Màu động theo ngưỡng sức khỏe
- Sync style với heart_rate_screen.py
"""
import logging
import statistics
import time
from kivy.uix.screenmanager import Screen
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDFillRoundFlatIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.progressbar import MDProgressBar

from src.utils.tts_manager import ScenarioID


# ============================================================
# THEME COLORS - Màu sắc giao diện y tế (sync với heart_rate_screen)
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
COLOR_CAUTION = (1.0, 0.8, 0.2, 1)         # Vàng - Sốt nhẹ
COLOR_DANGER = (1.0, 0.3, 0.3, 1)          # Đỏ - Sốt cao
COLOR_COLD = (0.3, 0.6, 0.95, 1)           # Xanh dương - Hạ thân nhiệt
COLOR_NORMAL = (0.4, 0.75, 0.95, 1)        # Xanh dương nhạt

# ============================================================
# BUTTON COLORS - Màu nút bấm nổi bật (sync với heart_rate_screen)
# ============================================================
BTN_START_COLOR = (0.1, 0.5, 0.7, 1)       # Xanh đậm - Bắt đầu
BTN_STOP_COLOR = (0.9, 0.35, 0.25, 1)      # Đỏ - Dừng
BTN_SAVE_COLOR = (0.2, 0.7, 0.4, 1)        # Xanh lá - Lưu
BTN_DISABLED_COLOR = (0.4, 0.4, 0.4, 1)    # Xám - Vô hiệu


class TemperatureScreen(Screen):
    """
    Màn hình đo chi tiết cho MLX90614.
    
    Thiết kế tối ưu cho người già:
    - Giá trị nhiệt độ lớn, rõ ràng
    - Màu sắc thay đổi theo ngưỡng sức khỏe
    - Nút bấm lớn, dễ thao tác
    - Layout đồng bộ với heart_rate_screen
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
        self.measurement_start_ts = None
        self.body_detected_ts = None  # Timestamp khi phát hiện nhiệt độ cơ thể
        
        # ============================================================
        # MEASUREMENT PARAMETERS - Theo chuẩn y tế (FDA/ISO 80601-2-56)
        # ============================================================
        # Thời gian đo tối ưu cho MLX90614: 5 giây sau khi ổn định
        # Datasheet: Thermal time constant ~10s, settling time 20-30s
        # Tổng thời gian: chờ phát hiện (không giới hạn) + đo ổn định (5s)
        self.measurement_duration = 5.0  # Thời gian đo SAU KHI phát hiện cơ thể (tăng từ 3s)
        self.sample_interval = 0.5  # 500ms = 2 samples/second (match sensor sample_rate)
        
        # Ngưỡng nhiệt độ cơ thể hợp lệ (35-42°C)
        # < 35°C: Nhiệt độ môi trường/sensor chưa warm up
        # > 42°C: Không hợp lý cho người sống
        # Note: Với offset +2.5°C, raw temp phải > 32.5°C → displayed > 35°C
        self.body_temp_min = 36.0  # °C - Ngưỡng dưới để phát hiện cơ thể (tăng từ 32°C)
        self.body_temp_max = 42.0  # °C - Ngưỡng trên hợp lệ
        
        # Warm-up period: Đợi sensor ổn định sau khi phát hiện cơ thể
        # MLX90614 thermal time constant τ ≈ 10s, cần ~5s để settling 63%
        self.warmup_delay = 2.0  # giây - Đợi sau khi detect trước khi thu samples
        
        # Outlier rejection: cho phép dao động ±2.5°C trong quá trình đo
        # Tăng từ 1.5°C để cho phép sensor settling từ cold start
        self.max_temp_deviation = 2.5  # °C
        
        self.samples = []

        # Current values
        self.current_temp = 0.0
        self.ambient_temp = 0.0
        
        self._build_layout()

    # ------------------------------------------------------------------
    # UI Construction & Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        """Build temperature measurement screen - sync với heart_rate_screen."""
        main_layout = MDBoxLayout(
            orientation='vertical',
            spacing=dp(6),
            padding=(dp(8), dp(6), dp(8), dp(8)),
        )

        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)

        self._create_header(main_layout)
        self._create_measurement_panel(main_layout)
        self._create_status_display(main_layout)
        self._create_controls(main_layout)

        self.add_widget(main_layout)
    
    def _update_bg(self, instance, value):
        self.bg_rect.size = instance.size
        self.bg_rect.pos = instance.pos
    
    def _create_header(self, parent):
        """Create header card - giống heart_rate_screen."""
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
            spacing=dp(2),
            size_hint_x=1,
        )

        title_label = MDLabel(
            text="NHIỆT ĐỘ CƠ THỂ",
            font_style="Subtitle1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(title_label)

        subtitle_label = MDLabel(
            text="Đưa cảm biến cách trán 2-5cm",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
        )
        subtitle_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        title_box.add_widget(subtitle_label)

        header_card.add_widget(title_box)
        parent.add_widget(header_card)

    def _create_measurement_panel(self, parent):
        """
        Create measurement panel - 2 cột: Metrics trái + Result phải.
        Bỏ card hướng dẫn, tận dụng không gian cho giá trị lớn.
        """
        panel_layout = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(130),
            padding=(dp(6), dp(6), dp(6), dp(6)),
        )

        # ============================================================
        # LEFT: Temperature Metrics (cột trái - readings nhỏ)
        # ============================================================
        metrics_card = MDCard(
            orientation="vertical",
            size_hint_x=0.45,
            padding=(dp(10), dp(10), dp(10), dp(10)),
            spacing=dp(8),
            radius=[dp(14)],
            md_bg_color=MED_CARD_BG,
        )

        # Object Temperature Row
        obj_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(42),
        )
        obj_icon = MDIcon(
            icon="thermometer",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(32), dp(32)),
        )
        obj_icon.icon_size = dp(28)
        obj_row.add_widget(obj_icon)

        obj_value_box = MDBoxLayout(orientation="vertical", spacing=dp(0), size_hint_x=1)
        obj_label = MDLabel(
            text="Cơ thể",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        obj_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        obj_value_box.add_widget(obj_label)

        self.obj_temp_label = MDLabel(
            text="-- °C",
            font_style="H6",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
            bold=True,
        )
        self.obj_temp_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        obj_value_box.add_widget(self.obj_temp_label)
        obj_row.add_widget(obj_value_box)
        metrics_card.add_widget(obj_row)

        # Ambient Temperature Row
        amb_row = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(6),
            size_hint_y=None,
            height=dp(42),
        )
        amb_icon = MDIcon(
            icon="home-thermometer",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(32), dp(32)),
        )
        amb_icon.icon_size = dp(28)
        amb_row.add_widget(amb_icon)

        amb_value_box = MDBoxLayout(orientation="vertical", spacing=dp(0), size_hint_x=1)
        amb_label = MDLabel(
            text="Môi trường",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        amb_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        amb_value_box.add_widget(amb_label)

        self.amb_temp_label = MDLabel(
            text="-- °C",
            font_style="Subtitle1",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        self.amb_temp_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        amb_value_box.add_widget(self.amb_temp_label)
        amb_row.add_widget(amb_value_box)
        metrics_card.add_widget(amb_row)

        panel_layout.add_widget(metrics_card)

        # ============================================================
        # RIGHT: Main Result Display (cột phải - giá trị LỚN)
        # ============================================================
        result_card = MDCard(
            orientation="vertical",
            size_hint_x=0.55,
            padding=(dp(12), dp(8), dp(12), dp(8)),
            spacing=dp(4),
            radius=[dp(14)],
            md_bg_color=MED_CARD_BG,
        )

        # Header với icon
        result_header = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(24),
            spacing=dp(6),
        )
        result_icon = MDIcon(
            icon="thermometer-check",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        result_icon.icon_size = dp(20)
        result_header.add_widget(result_icon)

        result_title = MDLabel(
            text="Kết quả",
            font_style="Subtitle2",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="left",
            valign="middle",
        )
        result_title.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        result_header.add_widget(result_title)
        result_card.add_widget(result_header)

        # Main temperature value - CHỮ TO cho người già
        self.temp_value_label = MDLabel(
            text="-- °C",
            font_style="H4",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            bold=True,
        )
        self.temp_value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        result_card.add_widget(self.temp_value_label)

        # Status label (Bình thường / Sốt nhẹ / Sốt cao)
        self.temp_state_label = MDLabel(
            text="Chờ đo",
            font_style="Body2",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
        )
        self.temp_state_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        result_card.add_widget(self.temp_state_label)

        panel_layout.add_widget(result_card)
        parent.add_widget(panel_layout)
    
    def _create_status_display(self, parent):
        """Create compact status bar - giống heart_rate_screen."""
        status_card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(48),
            padding=(dp(8), dp(6), dp(8), dp(6)),
            spacing=dp(2),
            radius=[dp(12)],
            md_bg_color=MED_CARD_BG,
        )

        self.status_label = MDLabel(
            text="Sẵn sàng đo",
            font_style="Body2",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="left",
            valign="middle",
        )
        self.status_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        status_card.add_widget(self.status_label)

        self.progress_bar = MDProgressBar(
            max=100,
            value=0,
            color=MED_CARD_ACCENT,
            size_hint_y=None,
            height=dp(3),
        )
        status_card.add_widget(self.progress_bar)

        parent.add_widget(status_card)
    
    def _create_controls(self, parent):
        """
        Create control buttons - nút đặc màu sắc nổi bật cho người già.
        Sync style với heart_rate_screen (MDFillRoundFlatIconButton).
        """
        control_layout = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            spacing=dp(10),
            padding=(dp(6), dp(4), dp(6), dp(4)),
        )

        # Nút Bắt đầu/Dừng - Màu xanh đậm nổi bật
        self.start_stop_btn = MDFillRoundFlatIconButton(
            text="BẮT ĐẦU",
            icon="play-circle",
            md_bg_color=BTN_START_COLOR,
            text_color=TEXT_PRIMARY,
            icon_color=TEXT_PRIMARY,
            size_hint_x=0.55,
            font_size="16sp",
            icon_size="24sp",
        )
        self.start_stop_btn.bind(on_press=self._on_start_stop_pressed)
        control_layout.add_widget(self.start_stop_btn)

        # Nút Lưu - Ban đầu xám (vô hiệu), chuyển xanh lá khi có kết quả
        self.save_btn = MDFillRoundFlatIconButton(
            text="LƯU",
            icon="content-save",
            disabled=True,
            md_bg_color=BTN_DISABLED_COLOR,
            text_color=(1, 1, 1, 0.5),
            icon_color=(1, 1, 1, 0.5),
            size_hint_x=0.45,
            font_size="16sp",
            icon_size="24sp",
        )
        self.save_btn.bind(on_press=self._on_save_pressed)
        control_layout.add_widget(self.save_btn)

        parent.add_widget(control_layout)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_back_pressed(self, instance):
        """Handle back button"""
        if self.measuring:
            self._stop_measurement()
        self.app_instance.navigate_to_screen('dashboard')
    
    def _on_start_stop_pressed(self, instance):
        """Handle start/stop button"""
        if self.measuring:
            self._stop_measurement()
        else:
            self._start_measurement()
    
    def _on_save_pressed(self, instance):
        """Handle save button"""
        if self.current_temp > 0:
            measurement_data = {
                'timestamp': time.time(),
                'temperature': self.current_temp,
                'ambient_temperature': self.ambient_temp,
                'measurement_type': 'temperature',
                # Add metadata for MQTT publishing
                'read_count': len(self.samples),
                'std_dev': 0.0,  # Calculate if needed
                'measurement_duration': self.measurement_duration
            }
            
            # Calculate standard deviation if we have samples
            if len(self.samples) >= 2:
                temps = [s['object'] for s in self.samples]
                mean_temp = sum(temps) / len(temps)
                variance = sum((t - mean_temp) ** 2 for t in temps) / len(temps)
                measurement_data['std_dev'] = variance ** 0.5
            
            self.app_instance.save_measurement_to_database(measurement_data)
            self.logger.info(f"Saved temperature measurement: {self.current_temp}°C")
            
            # TTS: Announce measurement complete
            self._speak_temp_scenario(ScenarioID.MEASUREMENT_COMPLETE)
            
            # Reset for next measurement
            self._style_save_button(enabled=False)

    # ------------------------------------------------------------------
    # Button Styling - Sync với heart_rate_screen
    # ------------------------------------------------------------------

    def _style_start_button(self, active: bool) -> None:
        """Style nút Bắt đầu/Dừng với màu sắc nổi bật."""
        if active:
            self.start_stop_btn.text = "DỪNG"
            self.start_stop_btn.icon = "stop-circle"
            self.start_stop_btn.md_bg_color = BTN_STOP_COLOR  # Đỏ
            self.start_stop_btn.text_color = TEXT_PRIMARY
            self.start_stop_btn.icon_color = TEXT_PRIMARY
        else:
            self.start_stop_btn.text = "BẮT ĐẦU"
            self.start_stop_btn.icon = "play-circle"
            self.start_stop_btn.md_bg_color = BTN_START_COLOR  # Xanh đậm
            self.start_stop_btn.text_color = TEXT_PRIMARY
            self.start_stop_btn.icon_color = TEXT_PRIMARY

    def _style_save_button(self, enabled: bool) -> None:
        """Style nút Lưu - Xanh lá khi enabled, xám khi disabled."""
        self.save_btn.disabled = not enabled
        if enabled:
            self.save_btn.md_bg_color = BTN_SAVE_COLOR  # Xanh lá
            self.save_btn.text_color = TEXT_PRIMARY
            self.save_btn.icon_color = TEXT_PRIMARY
        else:
            self.save_btn.md_bg_color = BTN_DISABLED_COLOR  # Xám
            self.save_btn.text_color = (1, 1, 1, 0.5)
            self.save_btn.icon_color = (1, 1, 1, 0.5)
    
    # ------------------------------------------------------------------
    # Dynamic Colors - Màu theo ngưỡng sức khỏe
    # ------------------------------------------------------------------
    
    def _get_temp_color(self, value: float) -> tuple:
        """
        Lấy màu cho nhiệt độ theo ngưỡng sức khỏe.
        
        Ngưỡng (theo WHO):
        - < 35°C: Hạ thân nhiệt nghiêm trọng → Xanh dương đậm
        - 35-36°C: Hơi thấp → Xanh dương nhạt
        - 36-37.5°C: Bình thường → Xanh lá
        - 37.5-38.5°C: Sốt nhẹ → Vàng
        - > 38.5°C: Sốt cao → Đỏ
        """
        if value < 35.0:
            return COLOR_COLD  # Xanh dương - hạ thân nhiệt
        elif value < 36.0:
            return COLOR_NORMAL  # Xanh dương nhạt - hơi thấp
        elif value <= 37.5:
            return COLOR_HEALTHY  # Xanh lá - bình thường
        elif value <= 38.5:
            return COLOR_CAUTION  # Vàng - sốt nhẹ
        else:
            return COLOR_DANGER  # Đỏ - sốt cao
    
    def _get_temp_status_text(self, value: float) -> str:
        """Lấy text status cho nhiệt độ."""
        if value < 35.0:
            return "⚠️ Hạ thân nhiệt"
        elif value < 36.0:
            return "Hơi thấp"
        elif value <= 37.5:
            return "✓ Bình thường"
        elif value <= 38.5:
            return "⚠️ Sốt nhẹ"
        elif value <= 40.0:
            return "🔴 Sốt cao"
        else:
            return "🔴 Nguy hiểm!"

    # ------------------------------------------------------------------
    # Measurement Control
    # ------------------------------------------------------------------

    def _start_measurement(self):
        """Start temperature measurement."""
        try:
            if not self.app_instance.ensure_sensor_started('MLX90614'):
                self.status_label.text = "Không thể khởi động cảm biến"
                self.logger.error("Failed to start MLX90614 sensor on demand")
                return

            self.measuring = True
            self.measurement_start_ts = time.time()
            self.body_detected_ts = None  # Reset - chờ phát hiện cơ thể
            self.samples.clear()
            self._display_object_temp(None)
            self._display_ambient_temp(None)
            self.temp_state_label.text = "Đưa cảm biến lại gần trán..."
            self.temp_state_label.text_color = COLOR_CAUTION
            
            # Update UI
            self._style_start_button(active=True)
            self._style_save_button(enabled=False)
            
            self.status_label.text = "Chờ phát hiện nhiệt độ cơ thể..."
            self.progress_bar.value = 0
            
            # Schedule updates
            Clock.schedule_interval(self._update_measurement, self.sample_interval)
            
            self._speak_temp_scenario(ScenarioID.TEMP_MEASURING)
            self.logger.info("Temperature measurement started - waiting for body detection")
            
        except Exception as e:
            self.logger.error(f"Error starting measurement: {e}")
            self.status_label.text = "Lỗi khi khởi động đo"
    
    def _stop_measurement(self, final_message: str | None = None, reset_progress: bool = True, keep_save_state: bool = False):
        """Stop temperature measurement."""
        try:
            if self.measuring:
                self.measuring = False
            
            # Update UI
            self._style_start_button(active=False)
            if reset_progress:
                self.progress_bar.value = 0

            if final_message:
                self.status_label.text = final_message
            elif reset_progress:
                self.status_label.text = "Đã dừng đo"

            if not keep_save_state:
                self._style_save_button(enabled=False)
                self.temp_state_label.text = "Chờ đo"
                self.temp_state_label.text_color = TEXT_MUTED
            elif final_message:
                self.temp_state_label.text = "Sẵn sàng đo tiếp"
                self.temp_state_label.text_color = TEXT_MUTED
            
            # Stop updates & reset state
            Clock.unschedule(self._update_measurement)
            self.measurement_start_ts = None
            self.body_detected_ts = None  # Reset body detection
            self.samples.clear()
            
            self.logger.info("Temperature measurement stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping measurement: {e}")
        finally:
            try:
                self.app_instance.stop_sensor('MLX90614')
            except Exception as sensor_error:
                self.logger.error(f"Error stopping MLX90614 sensor: {sensor_error}")
    
    def _update_measurement(self, dt):
        """
        Update measurement progress với 2-phase logic:
        1. Phase 1: Chờ phát hiện nhiệt độ cơ thể (32-42°C)
        2. Phase 2: Thu thập samples trong 3 giây
        """
        try:
            if not self.measuring or not self.measurement_start_ts:
                return False

            now = time.time()
            
            # Get current sensor data
            sensor_data = self.app_instance.get_sensor_data()
            object_temp = sensor_data.get('temperature')
            ambient_temp = sensor_data.get('ambient_temperature')
            
            # Hiển thị ambient temperature
            ambient_validated = self._validate_ambient_temp(ambient_temp)
            self._display_ambient_temp(ambient_validated)

            # ============================================================
            # PHASE 1: Chờ phát hiện nhiệt độ cơ thể
            # ============================================================
            if self.body_detected_ts is None:
                if self._is_body_temperature(object_temp):
                    # Phát hiện nhiệt độ cơ thể!
                    self.body_detected_ts = now
                    self.samples.clear()  # Reset samples
                    self.temp_state_label.text = "Đang ổn định cảm biến..."
                    self.temp_state_label.text_color = COLOR_CAUTION
                    self.logger.info(f"[Body temperature detected] {object_temp:.2f}°C - starting measurement")
                else:
                    # Chưa phát hiện - hiển thị hướng dẫn
                    if object_temp is not None:
                        self.status_label.text = f"Nhiệt độ: {object_temp:.1f}°C - Đưa gần trán hơn"
                        # Hiển thị giá trị hiện tại (màu xám vì chưa hợp lệ)
                        self.temp_value_label.text = f"{object_temp:.1f} °C"
                        self.temp_value_label.text_color = TEXT_MUTED
                    else:
                        self.status_label.text = "Chờ tín hiệu từ cảm biến..."
                    return True  # Tiếp tục chờ

            # ============================================================
            # PHASE 2: Warm-up period + Thu thập samples
            # ============================================================
            elapsed = max(0.0, now - self.body_detected_ts)
            
            # Sub-phase 2A: Warm-up delay (cho phép sensor ổn định)
            if elapsed < self.warmup_delay:
                warmup_remaining = self.warmup_delay - elapsed
                self.status_label.text = f"Đang ổn định... {warmup_remaining:.1f}s"
                self.progress_bar.value = 0
                # Hiển thị giá trị hiện tại (màu cam = đang warm up)
                if object_temp is not None:
                    self.temp_value_label.text = f"{object_temp:.1f} °C"
                    self.temp_value_label.text_color = COLOR_CAUTION
                return True  # Tiếp tục warm-up
            
            # Sub-phase 2B: Thu thập samples (sau warm-up)
            measurement_elapsed = elapsed - self.warmup_delay
            progress_ratio = min(measurement_elapsed / self.measurement_duration, 1.0)
            self.progress_bar.value = progress_ratio * 100
            remaining = max(0.0, self.measurement_duration - measurement_elapsed)
            self.status_label.text = f"Giữ yên... {remaining:.1f}s"
            
            # Update UI state khi bắt đầu thu samples
            if len(self.samples) == 0:
                self.temp_state_label.text = "Đang đo..."
                self.temp_state_label.text_color = COLOR_HEALTHY

            # Validate và collect samples
            if self._is_body_temperature(object_temp):
                if self._accept_sample(object_temp):
                    sample = {
                        'timestamp': now,
                        'object': float(object_temp),
                        'ambient': ambient_validated,
                    }
                    self.samples.append(sample)

                    # Hiển thị giá trị realtime với màu sắc
                    running_avg, _ = self._compute_average()
                    if running_avg is not None:
                        self._display_object_temp(running_avg)
                else:
                    self.logger.debug(
                        "Rejected temperature sample %.2f°C as outlier (baseline %.2f°C)",
                        object_temp,
                        statistics.median([s['object'] for s in self.samples]) if self.samples else object_temp,
                    )
            else:
                # Mất tín hiệu cơ thể - cảnh báo
                self.temp_state_label.text = "⚠️ Giữ cảm biến ổn định!"
                self.temp_state_label.text_color = COLOR_CAUTION
                self.logger.warning(f"Lost body contact: {object_temp}°C")

            # ============================================================
            # Finalise sau khi đủ thời gian (measurement_duration KHÔNG bao gồm warmup)
            # ============================================================
            if measurement_elapsed >= self.measurement_duration:
                average_temp, average_ambient = self._compute_average()

                if average_temp is None:
                    self.logger.warning("Temperature measurement finished without valid samples")
                    self._stop_measurement(
                        final_message="Không đủ mẫu hợp lệ, vui lòng đo lại",
                        reset_progress=True,
                        keep_save_state=False,
                    )
                    return False

                self._display_object_temp(average_temp)
                self._display_ambient_temp(average_ambient)

                scenario_id, result_message = self._determine_result_scenario(average_temp)
                
                # Cập nhật status label với màu và text phù hợp
                status_text = self._get_temp_status_text(average_temp)
                self.temp_state_label.text = status_text
                self.temp_state_label.text_color = self._get_temp_color(average_temp)
                
                self._style_save_button(enabled=True)
                self.progress_bar.value = 100
                self.logger.info(
                    "Temperature measurement completed with %d samples, average %.2f°C",
                    len(self.samples),
                    average_temp,
                )

                if scenario_id is not None:
                    self._speak_temp_scenario(scenario_id, temp=average_temp)

                self._stop_measurement(
                    final_message=result_message,
                    reset_progress=False,
                    keep_save_state=True,
                )
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error updating measurement: {e}")
            self._stop_measurement(
                final_message="Xảy ra lỗi trong quá trình đo",
                reset_progress=True,
                keep_save_state=False,
            )
            return False

    # ------------------------------------------------------------------
    # Data Processing & Validation
    # ------------------------------------------------------------------

    def _is_valid_object_temp(self, value: float | None) -> bool:
        """Kiểm tra giá trị nhiệt độ có hợp lệ không (trong range sensor)."""
        if value is None:
            return False
        return value > 0 and -70 <= value <= 380
    
    def _is_body_temperature(self, value: float | None) -> bool:
        """
        Kiểm tra xem nhiệt độ có nằm trong khoảng nhiệt độ cơ thể không.
        
        Ngưỡng 32-42°C:
        - < 32°C: Nhiệt độ môi trường hoặc không tiếp xúc đúng
        - > 42°C: Không hợp lý cho người sống (hyperthermia extreme)
        
        Returns:
            True nếu là nhiệt độ cơ thể hợp lệ
        """
        if value is None:
            return False
        return self.body_temp_min <= value <= self.body_temp_max

    def _validate_ambient_temp(self, value: float | None) -> float | None:
        """Validate nhiệt độ môi trường."""
        if value is None:
            return None
        return float(value) if -40 <= value <= 85 else None

    def _accept_sample(self, temp_value: float) -> bool:
        """
        Quyết định có chấp nhận sample này không (outlier rejection).
        
        Logic mới:
        - Luôn chấp nhận nếu chưa có sample nào
        - So sánh với median của các samples đã có
        - Cho phép dao động ±1.5°C (tăng từ 0.7°C)
        """
        # Luôn chấp nhận sample đầu tiên
        if len(self.samples) == 0:
            return True
        
        # Tính baseline từ samples hiện có
        baseline = statistics.median(s['object'] for s in self.samples)
        deviation = abs(temp_value - baseline)
        
        # Chấp nhận nếu trong ngưỡng deviation
        return deviation <= self.max_temp_deviation

    def _compute_average(self) -> tuple[float | None, float | None]:
        if not self.samples:
            return None, None

        temps = [sample['object'] for sample in self.samples]
        median_temp = statistics.median(temps)
        filtered_temps = [temp for temp in temps if abs(temp - median_temp) <= self.max_temp_deviation]
        if not filtered_temps:
            filtered_temps = temps

        avg_temp = sum(filtered_temps) / len(filtered_temps)

        ambient_values = [sample['ambient'] for sample in self.samples if sample['ambient'] is not None]
        avg_ambient = None
        if ambient_values:
            median_ambient = statistics.median(ambient_values)
            filtered_ambient = [val for val in ambient_values if abs(val - median_ambient) <= 1.5]
            if not filtered_ambient:
                filtered_ambient = ambient_values
            avg_ambient = sum(filtered_ambient) / len(filtered_ambient)

        return avg_temp, avg_ambient

    def _determine_result_scenario(self, avg_temp: float) -> tuple[ScenarioID | None, str]:
        if avg_temp < 35.0:
            return (
                ScenarioID.TEMP_RESULT_CRITICAL_LOW,
                f'Hoàn thành - Nhiệt độ rất thấp ({avg_temp:.1f}°C)',
            )
        if avg_temp < 36.0:
            return (
                ScenarioID.TEMP_RESULT_LOW,
                f'Hoàn thành - Nhiệt độ hơi thấp ({avg_temp:.1f}°C)',
            )
        if avg_temp <= 37.5:
            return (
                ScenarioID.TEMP_RESULT_NORMAL,
                f'Hoàn thành - Nhiệt độ bình thường ({avg_temp:.1f}°C)',
            )
        if avg_temp <= 38.5:
            return (
                ScenarioID.TEMP_RESULT_FEVER,
                f'Hoàn thành - Cảnh báo sốt nhẹ ({avg_temp:.1f}°C)',
            )
        if avg_temp <= 40.0:
            return (
                ScenarioID.TEMP_RESULT_HIGH_FEVER,
                f'Hoàn thành - Cảnh báo sốt cao ({avg_temp:.1f}°C)',
            )
        return (
            ScenarioID.TEMP_RESULT_CRITICAL_HIGH,
            f'Hoàn thành - Nguy hiểm: sốt rất cao ({avg_temp:.1f}°C)',
        )

    def _speak_temp_scenario(self, scenario_id: ScenarioID, **kwargs) -> None:
        if not scenario_id:
            return

        speak_fn = getattr(self.app_instance, '_speak_scenario', None)
        if callable(speak_fn):
            try:
                speak_fn(scenario_id, **kwargs)
            except Exception as exc:  # pragma: no cover - defensive logging
                self.logger.error("Không thể phát TTS cho kịch bản %s: %s", scenario_id, exc)

    # ------------------------------------------------------------------
    # Display Helpers - Cập nhật UI với màu động
    # ------------------------------------------------------------------

    def _display_object_temp(self, value: float | None) -> None:
        """Hiển thị nhiệt độ cơ thể với màu theo ngưỡng."""
        if value is None:
            self.current_temp = 0.0
            self.obj_temp_label.text = "-- °C"
            self.obj_temp_label.text_color = TEXT_PRIMARY
            self.temp_value_label.text = "-- °C"
            self.temp_value_label.text_color = TEXT_PRIMARY
            return

        self.current_temp = value
        color = self._get_temp_color(value)
        
        # Cập nhật cả 2 label
        self.obj_temp_label.text = f"{value:.1f} °C"
        self.obj_temp_label.text_color = color
        
        self.temp_value_label.text = f"{value:.1f} °C"
        self.temp_value_label.text_color = color

    def _display_ambient_temp(self, value: float | None) -> None:
        """Hiển thị nhiệt độ môi trường."""
        if value is None:
            self.ambient_temp = 0.0
            self.amb_temp_label.text = "-- °C"
            return

        self.ambient_temp = value
        self.amb_temp_label.text = f"{value:.1f} °C"

    def _format_measurement_status(self, elapsed_seconds: float) -> str:
        """Format status text khi đang đo."""
        elapsed_clamped = max(0.0, min(elapsed_seconds, self.measurement_duration))
        return f"Đang đo... {elapsed_clamped:.1f}/{self.measurement_duration:.1f}s"
    
    def on_enter(self):
        """Called when screen is entered."""
        self.logger.info("Temperature measurement screen entered")
        
        # Reset displays
        self._display_object_temp(None)
        self._display_ambient_temp(None)
        self.progress_bar.value = 0
        self.status_label.text = 'Nhấn "BẮT ĐẦU" để đo nhiệt độ'
        self.temp_state_label.text = "Chờ đo"
        self.temp_state_label.text_color = TEXT_MUTED
        self.measuring = False
        self.measurement_start_ts = None
        self.body_detected_ts = None
        self.samples.clear()

        # Reset control buttons
        self._style_start_button(active=False)
        self._style_save_button(enabled=False)
    
    def on_leave(self):
        """Called when screen is left."""
        self.logger.info("Temperature measurement screen left")
        
        # Stop any ongoing measurement
        if self.measuring:
            self._stop_measurement()
        else:
            self.measurement_start_ts = None
            self.samples.clear()
            self._style_start_button(active=False)
            self._style_save_button(enabled=False)