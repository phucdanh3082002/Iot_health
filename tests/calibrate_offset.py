#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OFFSET Calibration Tool
=======================
Tìm giá trị offset chính xác khi áp suất = 0 mmHg

Yêu cầu:
- Cuff KHÔNG được bơm (áp suất môi trường ~0 mmHg)
- Van MỞ hoàn toàn
- Đo 30 giây để lấy trung bình

Cách dùng:
1. Đảm bảo cuff xả hết khí
2. Chạy script này
3. Đợi 30 giây
4. Copy giá trị offset mới vào config
"""

import time
import sys
import pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sensors.hx710b_sensor import HX710BSensor

# Cấu hình tạm thời (chưa có offset)
TEMP_CONFIG = {
    'enabled': True,
    'gpio_dout': 6,
    'gpio_sck': 5,
    'mode': '10sps',
    'read_timeout_ms': 1000,
    'calibration': {
        'offset_counts': 0,  # Tạm thời = 0 để đọc raw
        'slope_mmhg_per_count': 3.5765743256e-05,
        'adc_inverted': False
    }
}

DURATION = 30  # giây
SAMPLES_EXPECTED = DURATION * 10  # 10 SPS


def main():
    print("\n" + "="*60)
    print("HX710B OFFSET CALIBRATION")
    print("="*60)
    print("\n⚠️  QUAN TRỌNG:")
    print("   1. Đảm bảo CUFF đã xả hết khí (áp suất = 0 mmHg)")
    print("   2. Van phải MỞ hoàn toàn")
    print("   3. Không chạm vào sensor trong quá trình đo")
    print(f"\n⏱️  Thời gian đo: {DURATION} giây (~{SAMPLES_EXPECTED} mẫu)")
    
    input("\nNhấn ENTER để bắt đầu...")
    
    # Tạo sensor
    sensor = HX710BSensor("OFFSET_CALIB", TEMP_CONFIG)
    
    try:
        # Khởi tạo
        if not sensor.initialize():
            print("❌ Không thể khởi tạo sensor!")
            return
        
        sensor.start()
        time.sleep(1.0)
        
        print(f"\n📊 Đang thu thập {SAMPLES_EXPECTED} mẫu...")
        print("Progress: ", end="", flush=True)
        
        counts_list = []
        t0 = time.time()
        last_progress = 0
        
        while (time.time() - t0) < DURATION:
            data = sensor.get_latest_data()
            
            if data and 'counts' in data:
                counts_list.append(data['counts'])
                
                # Hiển thị tiến trình
                progress = int((time.time() - t0) / DURATION * 100)
                if progress > last_progress:
                    print(f"\rProgress: {'█' * (progress//5)}{' ' * (20-progress//5)} {progress}%",
                          end="", flush=True)
                    last_progress = progress
            
            time.sleep(0.05)
        
        print("\n\n✓ Thu thập hoàn tất!")
        
        # Phân tích dữ liệu
        if len(counts_list) < 10:
            print(f"❌ Không đủ dữ liệu (chỉ có {len(counts_list)} mẫu)")
            return
        
        counts_array = np.array(counts_list)
        
        # Tính toán thống kê
        mean_counts = np.mean(counts_array)
        median_counts = np.median(counts_array)
        std_counts = np.std(counts_array)
        min_counts = np.min(counts_array)
        max_counts = np.max(counts_array)
        
        print("\n" + "="*60)
        print("KẾT QUẢ CALIBRATION")
        print("="*60)
        print(f"Số mẫu thu thập:    {len(counts_list)}")
        print(f"Giá trị trung bình: {mean_counts:,.0f} counts")
        print(f"Giá trị trung vị:   {median_counts:,.0f} counts")
        print(f"Độ lệch chuẩn:      {std_counts:,.1f} counts")
        print(f"Min - Max:          {min_counts:,} ~ {max_counts:,}")
        print("="*60)
        
        # Đề xuất offset (dùng median để tránh outliers)
        recommended_offset = int(median_counts)
        
        print("\n✅ OFFSET ĐỀ XUẤT:")
        print(f"   offset_counts: {recommended_offset}")
        
        print("\n📝 CẬP NHẬT CONFIG:")
        print(f"\n   sensors:")
        print(f"     hx710b:")
        print(f"       calibration:")
        print(f"         offset_counts: {recommended_offset}")
        print(f"         slope_mmhg_per_count: 3.5765743256e-05")
        
        # Kiểm tra noise level
        noise_mmhg = std_counts * 3.5765743256e-05
        print(f"\n📈 Noise level: ±{noise_mmhg:.2f} mmHg (±{std_counts:.0f} counts)")
        
        if noise_mmhg > 1.0:
            print("   ⚠️  Nhiễu cao! Kiểm tra:")
            print("      - Nguồn điện ổn định")
            print("      - Dây nối ngắn, tránh nhiễu EMI")
            print("      - Sensor gắn chắc chắn")
        else:
            print("   ✓ Noise level tốt")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Bị hủy bởi người dùng")
    
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")
    
    finally:
        sensor.stop()
        sensor.cleanup()
        print("\n✓ Cleanup hoàn tất\n")


if __name__ == "__main__":
    main()
