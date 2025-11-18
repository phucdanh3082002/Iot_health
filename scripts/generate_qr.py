#!/usr/bin/env python3
"""
Script tạo QR Code cho device pairing
Chạy trên máy tính cá nhân, sau đó copy ảnh vào Raspberry Pi
"""

import qrcode
import json
import sys

def generate_device_qr(device_id, pairing_code, api_url, output_file="device_qr_code.png"):
    """
    Tạo QR code cho device pairing
    
    Args:
        device_id: ID của thiết bị (e.g., rpi_bp_001)
        pairing_code: Mã pairing từ MySQL (e.g., ABC123XY)
        api_url: URL của Flask API (e.g., http://47.130.193.237:8000)
        output_file: Tên file output
    """
    
    # QR code chỉ chứa thông tin tối thiểu
    # Device name sẽ do user tự đặt trên Android app
    qr_data = {
        "pairing_code": pairing_code,
        "device_id": device_id,
        "api_url": api_url
    }
    
    # Chuyển thành JSON string
    qr_content = json.dumps(qr_data)
    
    # Tạo QR code
    qr = qrcode.QRCode(
        version=1,  # Kích thước (1-40, auto nếu None)
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
        box_size=10,  # Kích thước mỗi ô
        border=4,  # Độ rộng viền
    )
    
    qr.add_data(qr_content)
    qr.make(fit=True)
    
    # Tạo ảnh
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Lưu file
    img.save(output_file)
    
    print("=" * 60)
    print("✅ QR Code đã được tạo thành công!")
    print("=" * 60)
    print(f"📁 File: {output_file}")
    print(f"📦 Nội dung QR:")
    print(json.dumps(qr_data, indent=2, ensure_ascii=False))
    print("=" * 60)
    print("\n📋 Bước tiếp theo:")
    print("1. Copy file này vào Raspberry Pi:")
    print(f"   scp {output_file} pi@<PI_IP>:/home/pi/Desktop/IoT_health/asset/images/")
    print("\n2. Android app sẽ scan QR và yêu cầu user nhập tên thiết bị")
    print("   (Ví dụ: 'Máy đo của bố', 'Phòng khách', v.v.)")
    print("=" * 60)
    
    return qr_content


if __name__ == "__main__":
    # Cấu hình mặc định
    DEFAULT_DEVICE_ID = "rpi_bp_001"
    DEFAULT_PAIRING_CODE = "ABC123XY"
    DEFAULT_API_URL = "http://47.130.193.237:8000"
    
    # Parse command line arguments
    if len(sys.argv) == 4:
        device_id = sys.argv[1]
        pairing_code = sys.argv[2]
        api_url = sys.argv[3]
    else:
        print("⚠️  Không có tham số, sử dụng giá trị mặc định")
        print(f"   Device ID: {DEFAULT_DEVICE_ID}")
        print(f"   Pairing Code: {DEFAULT_PAIRING_CODE}")
        print(f"   API URL: {DEFAULT_API_URL}")
        print("\n💡 Để tùy chỉnh, chạy:")
        print("   python generate_qr.py <device_id> <pairing_code> <api_url>")
        print()
        
        device_id = DEFAULT_DEVICE_ID
        pairing_code = DEFAULT_PAIRING_CODE
        api_url = DEFAULT_API_URL
    
    # Tạo QR code
    output_file = f"{device_id}_qr.png"
    generate_device_qr(device_id, pairing_code, api_url, output_file)
