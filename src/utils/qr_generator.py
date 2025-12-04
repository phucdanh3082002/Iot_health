"""
QR Code Generator cho Device Pairing

Tạo QR code chứa thông tin pairing để Android app scan và ghép nối.
"""

import json
import logging
from io import BytesIO
from typing import Dict, Any, Optional

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False


logger = logging.getLogger(__name__)


def generate_pairing_qr(
    pairing_code: str,
    device_id: str,
    api_url: str,
    box_size: int = 8,
    border: int = 2,
) -> Optional[BytesIO]:
    """
    Tạo QR code cho device pairing.
    
    Args:
        pairing_code: Mã ghép nối cố định từ config
        device_id: ID thiết bị (vd: rpi_bp_001)
        api_url: URL của REST API server
        box_size: Kích thước mỗi box trong QR (pixel)
        border: Độ dày viền QR
        
    Returns:
        BytesIO: PNG image buffer, hoặc None nếu lỗi
        
    QR Data Format:
        {
            "pairing_code": "ABC123XY",
            "device_id": "rpi_bp_001", 
            "api_url": "http://47.130.193.237:8000"
        }
    """
    if not QR_AVAILABLE:
        logger.error("qrcode library not installed. Run: pip install qrcode[pil]")
        return None
    
    try:
        # Build pairing data
        pairing_data: Dict[str, Any] = {
            "pairing_code": pairing_code,
            "device_id": device_id,
            "api_url": api_url,
        }
        
        # Convert to JSON string
        data_string = json.dumps(pairing_data, separators=(',', ':'))
        
        logger.info(f"Generating QR code for device: {device_id}")
        logger.debug(f"QR data: {data_string}")
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,  # Auto-size
            error_correction=ERROR_CORRECT_M,  # 15% error correction
            box_size=box_size,
            border=border,
        )
        qr.add_data(data_string)
        qr.make(fit=True)
        
        # Generate image (black on white)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to BytesIO buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)  # Reset buffer position
        
        logger.info(f"QR code generated successfully ({buffer.getbuffer().nbytes} bytes)")
        return buffer
        
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}", exc_info=True)
        return None


def get_qr_data_string(pairing_code: str, device_id: str, api_url: str) -> str:
    """
    Trả về JSON string của QR data (để debug hoặc hiển thị).
    
    Args:
        pairing_code: Mã ghép nối
        device_id: ID thiết bị
        api_url: URL API
        
    Returns:
        str: JSON string
    """
    data = {
        "pairing_code": pairing_code,
        "device_id": device_id,
        "api_url": api_url,
    }
    return json.dumps(data, indent=2)


# =============================================================================
# Module check
# =============================================================================

def check_qr_dependencies() -> bool:
    """Kiểm tra xem thư viện qrcode đã được cài đặt chưa."""
    if not QR_AVAILABLE:
        logger.warning(
            "QR code dependencies missing. Install with: pip install qrcode[pil]"
        )
        return False
    return True
