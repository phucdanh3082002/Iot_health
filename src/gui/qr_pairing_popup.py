"""
QR Code Pairing Popup

Popup hiển thị QR code để ghép nối với Android app.
Bao gồm:
- QR Image
- Text box hiển thị Pairing Code
- Hướng dẫn sử dụng
- Nút đóng
"""

import logging
from io import BytesIO
from typing import Optional

from kivy.metrics import dp, sp
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, RoundedRectangle
from kivymd.uix.dialog import MDDialog
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivy.uix.image import Image

logger = logging.getLogger(__name__)

# Theme colors (sync với dashboard_screen)
MED_BG_COLOR = (0.02, 0.18, 0.27, 1)          # Nền chính tối
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)        # Card background
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)        # Accent xanh lục
MED_PRIMARY = (0.12, 0.55, 0.76, 1)           # Primary xanh dương
TEXT_PRIMARY = (1, 1, 1, 1)                   # Trắng
TEXT_MUTED = (0.78, 0.88, 0.95, 1)            # Trắng nhạt
ACCENT_COLOR = (0.0, 0.68, 0.57, 1)           # Xanh lục accent


class QRPairingContent(MDBoxLayout):
    """
    Nội dung bên trong popup QR pairing.
    
    Layout:
    ┌────────────────────────┐
    │  Quét mã QR bằng app   │  ← Instruction
    │                        │
    │      ┌──────────┐      │
    │      │  QR IMG  │      │  ← QR Image
    │      └──────────┘      │
    │                        │
    │   Mã ghép nối:         │  ← Label
    │   ┌──────────────┐     │
    │   │  ABC123XY    │     │  ← Pairing Code Box
    │   └──────────────┘     │
    │                        │
    │  Device: rpi_bp_001    │  ← Device ID
    └────────────────────────┘
    """
    
    def __init__(
        self,
        qr_buffer: Optional[BytesIO],
        pairing_code: str,
        device_id: str,
        **kwargs
    ):
        super().__init__(**kwargs)
        
        self.orientation = "vertical"
        self.spacing = dp(4)
        self.padding = (dp(8), dp(6), dp(8), dp(6))
        self.size_hint = (1, None)  # Chiều rộng 100%, chiều cao tự động
        self.height = self.minimum_height  # Sẽ được tính toán từ children
        self.md_bg_color = MED_BG_COLOR  # Nền tối sync với dashboard
        
        self._build_content(qr_buffer, pairing_code, device_id)
        
        # Bind để update height khi children thay đổi
        self.bind(minimum_height=self.setter('height'))
    
    def _build_content(
        self,
        qr_buffer: Optional[BytesIO],
        pairing_code: str,
        device_id: str
    ):
        """Build nội dung popup."""
        
        # ------------------------------------------------------------------
        # 1. Instruction Label (auto size)
        # ------------------------------------------------------------------
        instruction = MDLabel(
            text="Quét mã QR bằng app Android",
            font_style="Body1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="center",
            size_hint_y=None,
        )
        instruction.bind(texture_size=instruction.setter('size'))
        self.add_widget(instruction)
        
        # ------------------------------------------------------------------
        # 2. QR Code Image (auto size)
        # ------------------------------------------------------------------
        qr_container = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            padding=(dp(8), dp(4), dp(8), dp(4)),
        )
        qr_container.bind(minimum_height=qr_container.setter('height'))
        
        # Spacer trái
        qr_container.add_widget(MDBoxLayout(size_hint_x=0.15))
        
        if qr_buffer is not None:
            try:
                # Load QR image from buffer (nhỏ hơn)
                qr_image = Image(
                    size_hint=(None, None),
                    size=(dp(160), dp(110)),  # Giảm từ 160 → 110
                    allow_stretch=True,
                    keep_ratio=True,
                )
                # Load texture từ BytesIO
                qr_buffer.seek(0)
                core_img = CoreImage(qr_buffer, ext='png')
                qr_image.texture = core_img.texture
                qr_container.add_widget(qr_image)
            except Exception as e:
                logger.error(f"Failed to load QR image: {e}")
                error_label = MDLabel(
                    text="[Không thể tải QR]",
                    halign="center",
                    theme_text_color="Custom",
                    text_color=(0.9, 0.3, 0.3, 1),
                )
                qr_container.add_widget(error_label)
        else:
            # QR generation failed
            error_label = MDLabel(
                text="[Lỗi tạo QR Code]\nCài đặt: pip install qrcode[pil]",
                halign="center",
                theme_text_color="Custom", 
                text_color=(0.9, 0.3, 0.3, 1),
            )
            error_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", (lbl.width, None)))
            qr_container.add_widget(error_label)
        
        # Spacer phải
        qr_container.add_widget(MDBoxLayout(size_hint_x=0.15))
        
        self.add_widget(qr_container)
        
        # ------------------------------------------------------------------
        # 3. Pairing Code Section (auto size)
        # ------------------------------------------------------------------
        code_section = MDBoxLayout(
            orientation="vertical",
            spacing=dp(4),
            size_hint_y=None,
        )
        code_section.bind(minimum_height=code_section.setter('height'))
        
        # Label "Mã ghép nối:" (auto size)
        code_title = MDLabel(
            text="Mã ghép nối:",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=None,
        )
        code_title.bind(texture_size=code_title.setter('size'))
        code_section.add_widget(code_title)
        
        # Pairing Code Box (fixed size)
        code_box = MDBoxLayout(
            orientation="horizontal",
            size_hint=(None, None),
            size=(dp(140), dp(32)),
            pos_hint={"center_x": 0.5},
        )
        
        # Background cho code box
        with code_box.canvas.before:
            Color(0.12, 0.55, 0.76, 0.3)  # MED_PRIMARY với opacity
            self._code_bg = RoundedRectangle(
                pos=code_box.pos,
                size=code_box.size,
                radius=[dp(6)]  # Giảm từ 8 → 6
            )
        code_box.bind(
            pos=lambda inst, val: setattr(self._code_bg, 'pos', val),
            size=lambda inst, val: setattr(self._code_bg, 'size', val)
        )
        
        # Pairing code text (FONT NHỎ HƠN)
        code_label = MDLabel(
            text=pairing_code,
            font_style="H5",  # Giảm từ H5 → Subtitle1
            theme_text_color="Custom",
            text_color=ACCENT_COLOR,  # Màu xanh lục accent
            halign="center",
            valign="center",
            bold=True,
        )
        code_label.bind(size=lambda lbl, _: setattr(lbl, "text_size", lbl.size))
        code_box.add_widget(code_label)
        
        code_section.add_widget(code_box)
        self.add_widget(code_section)
        
        # ------------------------------------------------------------------
        # 4. Device ID Info (auto size)
        # ------------------------------------------------------------------
        device_label = MDLabel(
            text=f"Thiết bị: {device_id}",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=None,
        )
        device_label.bind(texture_size=device_label.setter('size'))
        self.add_widget(device_label)


class QRPairingPopup:
    """
    Manager class để hiển thị QR Pairing popup.
    
    Usage:
        popup = QRPairingPopup(qr_buffer, pairing_code, device_id)
        popup.open()
    """
    
    def __init__(
        self,
        qr_buffer: Optional[BytesIO],
        pairing_code: str,
        device_id: str,
    ):
        self.qr_buffer = qr_buffer
        self.pairing_code = pairing_code
        self.device_id = device_id
        self.dialog: Optional[MDDialog] = None
        
    def open(self):
        """Hiển thị popup."""
        if self.dialog is None:
            self.dialog = MDDialog(
                title="Ghép nối thiết bị",
                type="custom",
                content_cls=QRPairingContent(
                    qr_buffer=self.qr_buffer,
                    pairing_code=self.pairing_code,
                    device_id=self.device_id,
                ),
                md_bg_color=MED_CARD_BG,  # Sync background với dashboard card
                buttons=[
                    MDFlatButton(
                        text="ĐÓNG",
                        font_style="Button",
                        theme_text_color="Custom",
                        text_color=MED_PRIMARY,
                        on_release=lambda *_: self.dismiss()
                    ),
                ],
            )
        
        self.dialog.open()
        logger.info(f"QR Pairing popup opened for device: {self.device_id}")
    
    def dismiss(self):
        """Đóng popup."""
        if self.dialog:
            self.dialog.dismiss()
            logger.info("QR Pairing popup closed")
