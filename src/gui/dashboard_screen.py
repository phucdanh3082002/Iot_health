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
from kivymd.uix.button import MDRectangleFlatIconButton, MDIconButton, MDFillRoundFlatIconButton
from src.gui.emergency_button import EmergencyButton
from src.utils.qr_generator import generate_pairing_qr, check_qr_dependencies
from src.gui.qr_pairing_popup import QRPairingPopup

MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class FeatureCard(MDCard):
    """Thẻ chức năng với màu nền tối, sync với theme y tế."""

    def __init__(self, title: str, subtitle: str, icon: str, card_color: tuple[float, ...], **kwargs):
        super().__init__(**kwargs)
        self.title = title
        self.subtitle = subtitle
        self.card_color = card_color
        self.value_text = "--"
        self.status_text = "Nhấn để đo"

        self.orientation = "vertical"
        self.size_hint = (0.5, None)
        self.height = dp(115)  # Tăng height để tận dụng không gian
        self.padding = (dp(12), dp(10), dp(12), dp(10))
        self.spacing = dp(4)
        self.radius = [dp(16)]
        self.md_bg_color = self.card_color  # Màu nền tối
        self.ripple_behavior = True

        content = MDBoxLayout(orientation="vertical", spacing=dp(4))

        # Icon + Title row
        icon_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(24),
            spacing=dp(6),
        )
        icon_widget = MDIcon(
            icon=icon,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.9),  # Trắng
            size_hint=(None, None),
            size=(dp(22), dp(22)),
        )
        icon_widget.icon_size = dp(20)
        icon_row.add_widget(icon_widget)

        title_label = MDLabel(
            text=title,
            font_style="Caption",
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.85),  # Trắng nhạt
        )
        title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        icon_row.add_widget(title_label)
        content.add_widget(icon_row)

        # Value (lớn, nổi bật, TRẮNG)
        self.value_label = MDLabel(
            text="--",
            font_style="H5",
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),  # Trắng sáng
            bold=True,
        )
        self.value_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        content.add_widget(self.value_label)

        # Status (màu accent - xanh lục nhạt)
        self.status_label = MDLabel(
            text="Nhấn để đo",
            font_style="Body2",
            theme_text_color="Custom",
            text_color=(0.4, 0.9, 0.7, 1),  # Xanh lục accent
        )
        self.status_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        content.add_widget(self.status_label)

        # Subtitle (trắng mờ)
        self.subtitle_label = MDLabel(
            text=subtitle,
            font_style="Caption",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.6),  # Trắng mờ
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
        """Build layout tối ưu cho màn hình 3.5 inch (480×320)."""
        main_layout = MDBoxLayout(
            orientation="vertical",
            spacing=dp(4),
            padding=(dp(6), dp(4), dp(6), dp(6)),
        )

        with main_layout.canvas.before:
            Color(*MED_BG_COLOR)
            self._bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg, pos=self._update_bg)

        self._create_header_row(main_layout)
        self._create_measurement_grid(main_layout)

        self.add_widget(main_layout)

    def _update_bg(self, instance, value):
        self._bg_rect.size = instance.size
        self._bg_rect.pos = instance.pos

    def _create_header_row(self, parent):
        """
        Header compact: Title + Time | Action Buttons
        """
        header_card = MDCard(
            orientation="horizontal",
            md_bg_color=MED_CARD_BG,
            radius=[dp(12)],
            padding=(dp(6), dp(8), dp(4), dp(8)),
            spacing=dp(4),
            size_hint_y=None,
            height=dp(64),
        )

        # ------------------------------------------------------------------
        # LEFT: Title + DateTime (vertical layout)
        # ------------------------------------------------------------------
        text_box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(2),
            size_hint_x=0.55,  # Chiếm 55% width
        )

        self.title_label = MDLabel(
            text="HỆ THỐNG GIÁM SÁT SỨC KHOẺ",
            font_style="Body2",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            bold=True,
            size_hint_y=None,
            height=dp(30),
            halign="left",
            valign="center",
        )
        self.title_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        text_box.add_widget(self.title_label)

        self.time_label = MDLabel(
            text=datetime.now().strftime("%d/%m/%Y - %H:%M"),
            font_style="Body2",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            size_hint_y=None,
            height=dp(18),
            halign="left",
            valign="center",
        )
        self.time_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        text_box.add_widget(self.time_label)

        header_card.add_widget(text_box)

        # ------------------------------------------------------------------
        # RIGHT: Action Buttons (icon-only for compact) + Emergency Button
        # ------------------------------------------------------------------
        action_box = MDBoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_x=0.45,  # Chiếm 45% width
            size_hint_y=None,
            height=dp(40),
        )

        # Settings Button
        self.settings_btn = MDIconButton(
            icon="cog-outline",
            theme_icon_color="Custom",
            icon_color=TEXT_PRIMARY,
            md_bg_color=(0.2, 0.35, 0.5, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        self.settings_btn.bind(on_release=lambda *_: self.app_instance.navigate_to_screen("settings"))
        action_box.add_widget(self.settings_btn)

        # History Button
        self.history_btn = MDIconButton(
            icon="history",
            theme_icon_color="Custom",
            icon_color=TEXT_PRIMARY,
            md_bg_color=(0.15, 0.45, 0.35, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        self.history_btn.bind(on_release=lambda *_: self.app_instance.navigate_to_screen("history"))
        action_box.add_widget(self.history_btn)

        # QR Code Button
        self.qr_btn = MDIconButton(
            icon="qrcode-scan",
            theme_icon_color="Custom",
            icon_color=TEXT_PRIMARY,
            md_bg_color=(0.45, 0.28, 0.5, 1),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        self.qr_btn.bind(on_release=self._on_qr_pressed)
        action_box.add_widget(self.qr_btn)

        # Emergency Button (4th button in action_box)
        self.emergency_button = EmergencyButton(
            app_instance=self.app_instance,
            on_emergency_confirmed=self._on_emergency_confirmed,
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        action_box.add_widget(self.emergency_button)

        header_card.add_widget(action_box)

        parent.add_widget(header_card)

    def _create_measurement_grid(self, parent):
        """Grid 2x2 cho 4 chức năng đo - màu nền tối, sync theme."""
        grid = MDGridLayout(
            cols=2,
            spacing=dp(8),
            size_hint_y=None,
            row_default_height=dp(115),
            row_force_default=True,
            adaptive_height=True,
        )

        # Màu nền tối cho cards - sync với MED_CARD_BG
        self.cardio_button = FeatureCard(
            title="Nhịp tim + SpO2",
            subtitle="Đặt ngón tay lên cảm biến",
            icon="heart-pulse",
            card_color=(0.35, 0.15, 0.30, 1),  # Tím đậm
        )
        self.cardio_button.bind(on_release=self._on_cardio_pressed)
        grid.add_widget(self.cardio_button)

        self.temp_button = FeatureCard(
            title="Nhiệt độ cơ thể",
            subtitle="Đưa cảm biến gần trán",
            icon="thermometer",
            card_color=(0.12, 0.35, 0.32, 1),  # Xanh lục đậm
        )
        self.temp_button.bind(on_release=self._on_temperature_pressed)
        grid.add_widget(self.temp_button)

        self.auto_button = FeatureCard(
            title="Đo tự động",
            subtitle="HR → SpO2 → Temp",
            icon="autorenew",
            card_color=(0.18, 0.25, 0.42, 1),  # Xanh dương đậm
        )
        self.auto_button.bind(on_release=self._on_auto_sequence_pressed)
        grid.add_widget(self.auto_button)

        self.bp_button = FeatureCard(
            title="Huyết áp",
            subtitle="Quấn vòng bít vào cánh tay",
            icon="water",
            card_color=(0.38, 0.22, 0.15, 1),  # Nâu cam đậm
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

    def _on_qr_pressed(self, *_):
        """
        Handler cho QR Code button - hiển thị QR để pair với app mobile.
        
        Flow:
        1. Đọc pairing_code, device_id từ config (cố định)
        2. Đọc api_url từ config
        3. Generate QR code
        4. Hiển thị popup với QR + pairing code text
        """
        self.logger.info("QR Code button pressed")
        
        try:
            # Kiểm tra dependencies
            if not check_qr_dependencies():
                self._show_qr_error("Thiếu thư viện QR Code.\nChạy: pip install qrcode[pil]")
                return
            
            # Lấy config từ app_instance (config_data chứa YAML config)
            config = getattr(self.app_instance, 'config_data', {})
            if not config:
                # Fallback: thử đọc trực tiếp từ file
                config = self._load_yaml_config()
            
            cloud_config = config.get('cloud', {})
            device_config = cloud_config.get('device', {})
            comm_config = config.get('communication', {})
            rest_config = comm_config.get('rest_api', {})
            
            # Đọc pairing_code cố định từ config
            pairing_code = device_config.get('pairing_code', 'UNKNOWN')
            device_id = device_config.get('device_id', 'rpi_bp_001')
            api_url = rest_config.get('server_url', 'http://localhost:8000')
            
            self.logger.info(f"Generating QR for device={device_id}, code={pairing_code}")
            
            # Generate QR code
            qr_buffer = generate_pairing_qr(
                pairing_code=pairing_code,
                device_id=device_id,
                api_url=api_url,
            )
            
            # Hiển thị popup
            popup = QRPairingPopup(
                qr_buffer=qr_buffer,
                pairing_code=pairing_code,
                device_id=device_id,
            )
            popup.open()
            
        except Exception as e:
            self.logger.error(f"QR pairing error: {e}", exc_info=True)
            self._show_qr_error(f"Lỗi tạo QR Code: {str(e)}")
    
    def _load_yaml_config(self) -> dict:
        """
        Fallback: Đọc config trực tiếp từ file YAML.
        
        Returns:
            dict: Config data hoặc {} nếu lỗi
        """
        try:
            import yaml
            from pathlib import Path
            config_path = Path(__file__).parent.parent.parent / "config" / "app_config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.error(f"Failed to load YAML config: {e}")
        return {}
    
    def _show_qr_error(self, message: str):
        """Hiển thị thông báo lỗi QR."""
        from kivymd.uix.dialog import MDDialog
        from kivymd.uix.button import MDFlatButton
        
        dialog = MDDialog(
            title="Lỗi QR Code",
            text=message,
            buttons=[
                MDFlatButton(
                    text="ĐÓNG",
                    on_release=lambda *_: dialog.dismiss()
                ),
            ],
        )
        dialog.open()

    def _on_emergency_confirmed(self):
        """
        Callback khi emergency được confirm (sau countdown hoặc nhấn XÁC NHẬN).
        
        Additional actions có thể thêm ở đây:
        - Log to local database
        - Send SMS/email
        - Activate alarm sound
        """
        self.logger.critical("🚨 EMERGENCY CONFIRMED from dashboard")
        
        # Log emergency event to database
        try:
            import time
            from datetime import datetime
            
            emergency_data = {
                'timestamp': datetime.fromtimestamp(time.time()),  # Convert to datetime for SQLite
                'device_id': getattr(self.app_instance, 'device_id', 'unknown'),
                'patient_id': getattr(self.app_instance, 'patient_id', None),
                'alert_type': 'emergency_button',
                'severity': 'critical',
                'message': 'Emergency button pressed from dashboard',
                'vital_sign': None,
                'current_value': None,
                'threshold_value': None,
            }
            # Use database.save_alert() method
            if hasattr(self.app_instance, 'database'):
                self.app_instance.database.save_alert(emergency_data)
        except Exception as e:
            self.logger.error(f"Failed to log emergency to database: {e}")

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
                # Cập nhật trạng thái cho thẻ Cardio (MAX30102)
                hr_status_data = sensor_data.get('sensor_status', {}).get('MAX30102', {})
                finger_detected = hr_status_data.get('finger_detected', False)
                hr_status = hr_status_data.get('hr_status', 'idle')
                spo2_status = hr_status_data.get('spo2_status', 'idle')
                
                status_text = "Nhấn để đo"
                subtitle_text = "Nhấn để đo trực tiếp"

                if not hr_status_data: # Sensor unavailable
                    status_text = "Không khả dụng"
                    subtitle_text = "Cảm biến không kết nối"
                elif hr_status == 'error':
                    status_text = "Lỗi cảm biến"
                    subtitle_text = "Kiểm tra kết nối"
                elif hr_status_data.get('session_active', False):
                    if not finger_detected:
                        status_text = "Chờ ngón tay"
                        subtitle_text = "Đặt ngón tay lên cảm biến"
                    elif hr_status == 'poor_signal' or spo2_status == 'poor_signal':
                        status_text = "Tín hiệu yếu"
                        subtitle_text = "Giữ ngón tay ổn định"
                    elif hr_status_data.get('measurement_ready', False):
                        status_text = "Đang đo..."
                        subtitle_text = "Giữ ngón tay cố định"
                
                self.cardio_button.update_state("--", status_text, subtitle=subtitle_text)

            # Cập nhật trạng thái cho thẻ nhiệt độ (MLX90614)
            temp_status_data = sensor_data.get('sensor_status', {}).get('MLX90614', {})
            temp_status = temp_status_data.get('status', 'idle')
            object_temp = sensor_data.get('object_temperature')

            temp_value_display = "--"
            temp_status_text = "Nhấn để đo"
            temp_subtitle_text = "Đưa cảm biến gần trán"
            
            if not temp_status_data: # Sensor unavailable
                temp_status_text = "Không khả dụng"
                temp_subtitle_text = "Cảm biến không kết nối"
            elif temp_status == 'error':
                temp_status_text = "Lỗi cảm biến"
                temp_subtitle_text = "Kiểm tra kết nối"
            elif object_temp is not None and object_temp > 0 and self.app_instance.sensors.get('MLX90614', False):
                temp_value_display = f"{object_temp:.1f}°C"
                temp_status_text = "Đã đo" # Nếu đang hiển thị giá trị, coi như đã đo gần nhất
                temp_subtitle_text = "Nhấn để xem chi tiết"
                if temp_status in ('high', 'critical_high', 'low', 'critical_low'):
                    temp_status_text = "Bất thường" # Thêm cảnh báo nếu nhiệt độ không bình thường

            self.temp_button.update_state(temp_value_display, temp_status_text, subtitle=temp_subtitle_text)

            systolic = sensor_data.get("blood_pressure_systolic")
            diastolic = sensor_data.get("blood_pressure_diastolic")
            bp_sensor_status_data = sensor_data.get('sensor_status', {}).get('BloodPressure', {})
            bp_sensor_status = bp_sensor_status_data.get('status', 'unknown')

            if systolic and diastolic and systolic > 0 and diastolic > 0:
                value = f"{systolic:.0f}/{diastolic:.0f} mmHg"
                self.bp_button.update_state(value, "Đã đo", subtitle="Nhấn để xem chi tiết")
            else:
                bp_status_text = "Nhấn để đo"
                bp_subtitle_text = "HX710B chưa sẵn sàng"

                if not bp_sensor_status_data: # Sensor unavailable
                    bp_status_text = "Không khả dụng"
                    bp_subtitle_text = "Cảm biến không kết nối"
                elif bp_sensor_status == 'error':
                    bp_status_text = "Lỗi cảm biến"
                    bp_subtitle_text = "Kiểm tra kết nối"
                elif bp_sensor_status == 'inflating':
                    bp_status_text = "Đang bơm"
                    bp_subtitle_text = "Giữ yên tĩnh"
                elif bp_sensor_status == 'deflating':
                    bp_status_text = "Đang đo"
                    bp_subtitle_text = "Giữ yên tĩnh"
                elif bp_sensor_status == 'analyzing':
                    bp_status_text = "Phân tích"
                    bp_subtitle_text = "Đang xử lý kết quả"
                
                self.bp_button.update_state("--", bp_status_text, subtitle=bp_subtitle_text)

            if self.time_label:
                self.time_label.text = datetime.now().strftime("%d/%m/%Y - %H:%M")

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
