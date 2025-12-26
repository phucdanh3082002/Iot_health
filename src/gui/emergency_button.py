"""
Emergency Button Component
Nút khẩn cấp cho người cao tuổi - thiết kế lớn, đỏ, dễ nhận biết

Chức năng:
- TTS cảnh báo khẩn cấp
- Gửi MQTT alert đến cloud
- Hiển thị popup xác nhận
- Có thể hủy trong 5 giây
"""
import logging
from typing import Optional, Callable

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton

from src.utils.tts_manager import ScenarioID


# Theme colors
EMERGENCY_COLOR = (0.95, 0.2, 0.15, 1)      # Đỏ đậm
EMERGENCY_PRESSED = (0.8, 0.1, 0.05, 1)     # Đỏ đậm hơn khi nhấn
EMERGENCY_GLOW = (1.0, 0.3, 0.2, 0.3)       # Glow effect


class EmergencyButton(FloatLayout):
    """
    Nút khẩn cấp compact (44dp) với countdown 5 giây để hủy
    
    Features:
    - Kích thước 44dp phù hợp với header bar
    - Màu đỏ nổi bật với icon cảnh báo
    - Popup xác nhận với countdown 5s
    - TTS thông báo + MQTT alert
    """
    
    def __init__(
        self, 
        app_instance,
        on_emergency_confirmed: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # Callback khi emergency được confirm (sau 5s hoặc nhấn "XÁC NHẬN")
        self.on_emergency_confirmed = on_emergency_confirmed
        
        # Dialog và countdown state
        self.emergency_dialog: Optional[MDDialog] = None
        self.countdown_event = None
        self.countdown_remaining = 0
        
        self._build_button()
    
    def _build_button(self):
        """Tạo nút khẩn cấp compact với glow effect nhẹ."""
        # Glow background (circle behind) - nhỏ hơn
        with self.canvas.before:
            Color(*EMERGENCY_GLOW)
            self.glow_ellipse = Ellipse(
                size=(dp(42), dp(42)),
                pos=(self.width / 2 - dp(21), self.height / 2 - dp(21))
            )
        
        self.bind(size=self._update_glow, pos=self._update_glow)
        
        # Main emergency button - compact 40dp
        self.btn = MDIconButton(
            icon="alert-octagon",
            icon_size=dp(20),
            theme_icon_color="Custom",
            icon_color=(1, 1, 1, 1),
            md_bg_color=EMERGENCY_COLOR,
            size_hint=(None, None),
            size=(dp(38), dp(38)),
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        self.btn.bind(on_press=self._on_emergency_pressed)
        self.add_widget(self.btn)
    
    def _update_glow(self, *args):
        """Update glow position khi layout thay đổi."""
        self.glow_ellipse.pos = (
            self.x + self.width / 2 - dp(21),
            self.y + self.height / 2 - dp(21)
        )
    
    def _on_emergency_pressed(self, instance):
        """
        Xử lý khi nút khẩn cấp được nhấn.
        
        Flow:
        1. TTS cảnh báo
        2. Hiển thị dialog countdown 5s
        3. Nếu không hủy sau 5s → trigger emergency
        4. MQTT alert được gửi khi confirmed
        """
        self.logger.warning("[EMERGENCY] Emergency button pressed")
        
        # TTS warning
        self._speak_scenario(ScenarioID.EMERGENCY_BUTTON_PRESSED)
        
        # Show countdown dialog
        self._show_emergency_dialog()
    
    def _show_emergency_dialog(self):
        """Hiển thị dialog xác nhận với countdown 5 giây."""
        self.countdown_remaining = 5
        
        self.emergency_dialog = MDDialog(
            title="CẢNH BÁO KHẨN CẤP",
            text=f"Đang gửi cảnh báo khẩn cấp...\nHủy trong {self.countdown_remaining} giây",
            size_hint=(0.85, None),
            buttons=[
                MDFlatButton(
                    text="HỦY",
                    theme_text_color="Custom",
                    text_color=(0.15, 0.65, 0.25, 1),  # Xanh lá
                    on_release=self._cancel_emergency
                ),
                MDFlatButton(
                    text="XÁC NHẬN NGAY",
                    theme_text_color="Custom",
                    text_color=(0.95, 0.25, 0.2, 1),  # Đỏ
                    on_release=self._confirm_emergency_now
                ),
            ],
        )
        self.emergency_dialog.open()
        
        # Start countdown
        self.countdown_event = Clock.schedule_interval(self._update_countdown, 1.0)
    
    def _update_countdown(self, dt):
        """Update countdown text mỗi giây."""
        self.countdown_remaining -= 1
        
        if self.countdown_remaining > 0:
            self.emergency_dialog.text = (
                f"Đang gửi cảnh báo khẩn cấp...\n"
                f"Hủy trong {self.countdown_remaining} giây"
            )
        else:
            # Countdown hết → trigger emergency
            self._confirm_emergency()
    
    def _confirm_emergency_now(self, instance):
        """User nhấn "XÁC NHẬN NGAY" → trigger ngay không đợi countdown."""
        if self.countdown_event:
            self.countdown_event.cancel()
            self.countdown_event = None
        
        self._confirm_emergency()
    
    def _confirm_emergency(self):
        """
        Kích hoạt emergency chính thức.
        
        Actions:
        1. Đóng dialog
        2. TTS thông báo đang gửi
        3. Gửi MQTT alert
        4. Callback đến app (nếu có)
        5. Log emergency event
        """
        # Close dialog
        if self.emergency_dialog:
            self.emergency_dialog.dismiss()
            self.emergency_dialog = None
        
        # Stop countdown
        if self.countdown_event:
            self.countdown_event.cancel()
            self.countdown_event = None
        
        self.logger.critical("[EMERGENCY] Emergency confirmed - Sending alerts")
        
        # TTS: Đang kết nối khẩn cấp
        self._speak_scenario(ScenarioID.EMERGENCY_CALL_INITIATED)
        
        # Publish MQTT emergency alert
        self._send_emergency_alert()
        
        # Callback to app (để app có thể xử lý thêm)
        if self.on_emergency_confirmed:
            try:
                self.on_emergency_confirmed()
            except Exception as e:
                self.logger.error(f"Emergency callback error: {e}")
        
        # Show confirmation
        self._show_emergency_sent_dialog()
    
    def _cancel_emergency(self, instance):
        """User nhấn "HỦY" → hủy emergency."""
        # Close dialog
        if self.emergency_dialog:
            self.emergency_dialog.dismiss()
            self.emergency_dialog = None
        
        # Stop countdown
        if self.countdown_event:
            self.countdown_event.cancel()
            self.countdown_event = None
        
        # TTS: Đã hủy
        self._speak_scenario(ScenarioID.EMERGENCY_CANCELLED)
        
        self.logger.info("Emergency alert cancelled by user")
    
    def _send_emergency_alert(self):
        """
        Gửi MQTT emergency alert đến cloud.
        
        Payload format:
        {
            "timestamp": 1699518000.123,
            "device_id": "rpi_bp_001",
            "patient_id": "patient_001",
            "alert_type": "emergency_button",
            "severity": "critical",
            "message": "Emergency button pressed - immediate assistance required",
            "vital_sign": null,
            "current_value": null,
            "threshold_value": null
        }
        """
        try:
            # Get MQTT client
            mqtt_client = getattr(self.app_instance, 'mqtt_client', None)
            if not mqtt_client:
                self.logger.error("MQTT client not available")
                return
            
            import time
            from src.communication.mqtt_payloads import AlertPayload
            
            # Build emergency alert payload using AlertPayload dataclass
            alert_payload = AlertPayload(
                timestamp=time.time(),
                device_id=getattr(self.app_instance, 'device_id', 'unknown'),
                patient_id=getattr(self.app_instance, 'patient_id', None),
                alert_type="emergency_button",
                severity="critical",
                priority=1,  # Highest priority
                current_measurement={
                    "source": "emergency_button",
                    "trigger": "manual"
                },
                thresholds={},
                trend={},
                actions={
                    "notification_sent": True,
                    "alert_type": "emergency"
                },
                recommendations=[
                    "Contact emergency services immediately",
                    "Check patient status",
                    "Notify family members"
                ],
                metadata={
                    "message": "Emergency button pressed - immediate assistance required"
                }
            )
            
            # Publish emergency alert (QoS 2 - exactly once)
            mqtt_client.publish_alert(alert_payload)
            
            self.logger.info("Emergency alert sent via MQTT")
            
        except Exception as e:
            self.logger.error(f"Failed to send emergency alert: {e}", exc_info=True)
    
    def _show_emergency_sent_dialog(self):
        """Hiển thị dialog xác nhận đã gửi thành công."""
        sent_dialog = MDDialog(
            title="ĐÃ GỬI CẢNH BÁO",
            text="Đã gửi thông báo khẩn cấp đến người thân và trung tâm y tế.",
            size_hint=(0.85, None),
            buttons=[
                MDFlatButton(
                    text="ĐÓNG",
                    theme_text_color="Custom",
                    text_color=(0.12, 0.55, 0.76, 1),  # MED_PRIMARY
                    on_release=lambda x: sent_dialog.dismiss()
                ),
            ],
        )
        sent_dialog.open()
        
        # Auto close sau 5 giây
        Clock.schedule_once(lambda dt: sent_dialog.dismiss(), 5.0)
    
    def _speak_scenario(self, scenario: ScenarioID, **kwargs):
        """Wrapper để gọi TTS."""
        try:
            if hasattr(self.app_instance, '_speak_scenario'):
                self.app_instance._speak_scenario(scenario, **kwargs)
        except Exception as e:
            self.logger.debug(f"TTS not available: {e}")
