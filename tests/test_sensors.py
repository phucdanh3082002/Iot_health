#!/usr/bin/env python3
"""
Test script for IoT Health Monitoring System Sensors
Test cảm biến MAX30102 và MLX90614 (GY-906)
"""

import time
import sys
import os
import json
from pathlib import Path

# Try to import yaml, fallback to basic dict if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("⚠️  PyYAML không có, sẽ sử dụng config cơ bản")

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load config directly from YAML file
def load_config():
    """Load configuration from app_config.yaml"""
    config_file = project_root / "config" / "app_config.yaml"
    
    if HAS_YAML:
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ Không thể load config từ YAML: {e}")
    
    # Fallback to hardcoded config if YAML not available
    print("🔄 Sử dụng config mặc định...")
    return {
        'sensors': {
            'max30102': {
                'enabled': True,
                'sample_rate': 50,
                'led_mode': 3,  # SpO2 mode (RED + IR LEDs active)
                'pulse_amplitude_red': 0x7F,  # High brightness for visibility
                'pulse_amplitude_ir': 0x7F,   # High brightness for visibility
                'adc_range': 4096,
                'sample_average': 8,
                'buffer_size': 100,
                'ir_threshold': 50000,
                'min_readings_for_calc': 50
            },
            'mlx90614': {
                'enabled': True,
                'sensor_type': 'MLX90614',
                'i2c_bus': 1,
                'i2c_address': 0x5A,
                'sample_rate': 1,
                'use_object_temp': True,
                'temperature_offset': 0.0,
                'smooth_factor': 0.1
            }
        }
    }

# Import our sensor classes
try:
    from src.sensors.max30102_sensor import MAX30102Sensor
    from src.sensors.mlx90614_sensor import MLX90614Sensor
except ImportError as e:
    print(f"Không thể import sensor classes: {e}")
    sys.exit(1)

# Import thư viện phụ thuộc
try:
    import max30102
    import hrcalc
except ImportError:
    print("Không tìm thấy max30102 hoặc hrcalc! Hãy chắc chắn đã copy vào lib hoặc PYTHONPATH.")
    max30102 = None
    hrcalc = None

try:
    from smbus2 import SMBus
except ImportError:
    print("Chưa cài đặt thư viện smbus2! Hãy chạy: pip install smbus2")
    SMBus = None

def test_max30102_led():
    """Test MAX30102 LED visibility specifically"""
    print("\n--- Test LED MAX30102 ---")
    
    if max30102 is None:
        print("❌ Thiếu thư viện max30102")
        return
    
    try:
        print("🔧 Initializing MAX30102 with maximum LED brightness...")
        sensor = max30102.MAX30102(channel=1, address=0x57)
        
        # Set maximum brightness
        sensor.set_config(max30102.REG_LED1_PA, [0xFF])  # RED maximum
        sensor.set_config(max30102.REG_LED2_PA, [0xFF])  # IR maximum
        sensor.set_config(max30102.REG_MODE_CONFIG, [0x03])  # SpO2 mode
        
        print("💡 LEDs are now at MAXIMUM brightness!")
        print("🔍 Look at your MAX30102 sensor - you should see:")
        print("   • RED LED glowing (visible to naked eye)")
        print("   • IR LED glowing (may need phone camera to see)")
        print("\nReading data for 15 seconds to keep LEDs active...")
        
        led_active_count = 0
        for i in range(30):
            try:
                available = sensor.get_data_present()
                if available > 0:
                    red, ir = sensor.read_fifo()
                    led_active_count += 1
                    if i % 5 == 0:  # Print every 5th reading
                        print(f"[{i+1:2d}s] LEDs ACTIVE - RED: {red:6d}, IR: {ir:6d}")
                else:
                    if i % 5 == 0:
                        print(f"[{i+1:2d}s] LEDs should be glowing...")
            except Exception as e:
                print(f"[{i+1:2d}s] Error: {e}")
            time.sleep(0.5)
        
        sensor.shutdown()
        print(f"\n✅ Test completed. LED was active {led_active_count}/30 readings")
        if led_active_count > 0:
            print("💡 LEDs are working! If you can't see them, check:")
            print("   • Sensor orientation (LEDs face up)")
            print("   • Room lighting (dim room helps see LEDs)")
            print("   • Use phone camera to see IR LED")
        else:
            print("❌ No LED activity detected - hardware issue?")
            
    except Exception as e:
        print(f"❌ Error testing LEDs: {e}")

def test_max30102():
    """Test MAX30102 sensor using our sensor class"""
    print("\n--- Test cảm biến MAX30102 với sensor class ---")
    
    if max30102 is None or hrcalc is None:
        print("❌ Thiếu thư viện max30102 hoặc hrcalc")
        print("💡 Để test MAX30102, cần:")
        print("   1. Thư viện max30102.py và hrcalc.py (✅ Đã có)")
        print("   2. Kết nối hardware MAX30102 với I2C bus 1, address 0x57")
        print("   3. Đảm bảo I2C được enable trên Raspberry Pi")
        return
    
    print("✅ Thư viện max30102 và hrcalc đã sẵn sàng")
    
    # First test LEDs
    led_test = input("\n❓ Bạn có muốn test LED trước không? (y/n): ").strip().lower()
    if led_test == 'y':
        test_max30102_led()
        input("\nNhấn Enter để tiếp tục với full sensor test...")
    
    try:
        # Load config
        config = load_config()
        max30102_config = config.get('sensors', {}).get('max30102', {})
        
        if not max30102_config.get('enabled', False):
            print("❌ MAX30102 không được enable trong config")
            return
            
        # Create sensor instance
        sensor = MAX30102Sensor(max30102_config)
        
        def data_callback(sensor_name, data):
            """Callback để hiển thị data mới"""
            timestamp = data.get('timestamp', '')[-8:]  # Last 8 chars (time part)
            print(f"\n📊 [{timestamp}] {sensor_name} Data:")
            
            if data.get('finger_detected', False):
                hr_status = "✅" if data.get('hr_valid', False) else "❌"
                spo2_status = "✅" if data.get('spo2_valid', False) else "❌"
                
                print(f"  ❤️  Nhịp tim: {data.get('heart_rate', 0)} BPM {hr_status}")
                print(f"  🫁 SpO2: {data.get('spo2', 0):.1f}% {spo2_status}")
                print(f"  📈 Signal Quality IR: {data.get('signal_quality_ir', 0):.1f}%")
                print(f"  📈 Signal Quality RED: {data.get('signal_quality_red', 0):.1f}%")
                print(f"  📊 Buffer Fill: {data.get('buffer_fill', 0)}/{data.get('readings_count', 0)}")
                print(f"  🔹 Status: {data.get('status', 'unknown')}")
            else:
                ir_mean = data.get('ir_mean', 0)
                print(f"  ⚠️  Không phát hiện ngón tay (IR mean: {ir_mean:.0f})")
                print(f"  💡 Threshold cần: {50000} (hiện tại: {ir_mean:.0f})")
        
        # Set callback
        sensor.set_data_callback(data_callback)
        
        # Start sensor
        if not sensor.start():
            print("❌ Không thể khởi động MAX30102 sensor")
            return
            
        print("✅ MAX30102 sensor đã khởi động. Đặt ngón tay lên cảm biến...")
        print("Nhấn Ctrl+C để dừng test")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🔄 Dừng test MAX30102...")
            
    except Exception as e:
        print(f"❌ Lỗi test MAX30102: {e}")
    finally:
        try:
            sensor.stop()
            print("✅ MAX30102 sensor đã dừng")
        except:
            pass

def test_mlx90614():
    """Test MLX90614 sensor using our sensor class"""
    print("\n--- Test cảm biến MLX90614 (GY-906) với sensor class ---")
    
    if SMBus is None:
        print("❌ Thiếu thư viện smbus2")
        return
    
    try:
        # Load config
        config = load_config()
        mlx90614_config = config.get('sensors', {}).get('mlx90614', {})
        
        if not mlx90614_config.get('enabled', False):
            print("❌ MLX90614 không được enable trong config")
            return
            
        # Create sensor instance
        sensor = MLX90614Sensor(mlx90614_config)
        
        def data_callback(sensor_name, data):
            """Callback để hiển thị data mới"""
            print(f"\n🌡️  {sensor_name} Temperature:")
            print(f"  🎯 Nhiệt độ cơ thể: {data['object_temperature']:.2f}°C")
            print(f"  🌍 Nhiệt độ môi trường: {data['ambient_temperature']:.2f}°C")
            print(f"  📊 Primary: {data['temperature']:.2f}°C ({data['measurement_type']})")
            print(f"  ⚕️  Status: {data['status']}")
        
        # Set callback
        sensor.set_data_callback(data_callback)
        
        # Start sensor
        if not sensor.start():
            print("❌ Không thể khởi động MLX90614 sensor")
            return
            
        print("✅ MLX90614 sensor đã khởi động. Đang đo nhiệt độ...")
        print("Nhấn Ctrl+C để dừng test")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🔄 Dừng test MLX90614...")
            
    except Exception as e:
        print(f"❌ Lỗi test MLX90614: {e}")
    finally:
        try:
            sensor.stop()
            print("✅ MLX90614 sensor đã dừng")
        except:
            pass

def test_gy906_raw():
    """Test raw GY-906 communication (fallback method)"""
    print("\n--- Test raw GY-906 (MLX90614) communication ---")
    
    if SMBus is None:
        print("❌ Thiếu thư viện smbus2")
        return
        
    address = 0x5A
    temp_reg = 0x07
    print("Bắt đầu test liên tục GY-906. Nhấn Ctrl+C để dừng.")
    
    try:
        with SMBus(1) as bus:
            while True:
                try:
                    data = bus.read_word_data(address, temp_reg)
                    temp = (data * 0.02) - 273.15
                    print(f"🌡️  Nhiệt độ = {temp:.2f}°C")
                except Exception as e:
                    print(f"❌ Lỗi khi đọc GY-906: {e}")
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n🔄 Dừng test GY-906.")
    except Exception as e:
        print(f"❌ Lỗi khi giao tiếp với GY-906: {e}")
    print("✅ Hoàn thành test GY-906.")

def test_i2c_devices():
    """Test I2C device detection"""
    print("\n--- Test I2C Device Detection ---")
    
    if SMBus is None:
        print("❌ smbus2 không có")
        return
    
    try:
        with SMBus(1) as bus:
            print("🔍 Scanning I2C bus 1...")
            detected_devices = []
            
            for addr in range(0x03, 0x78):  # Standard I2C address range
                try:
                    bus.read_byte(addr)
                    detected_devices.append(addr)
                    print(f"  ✅ Device found at 0x{addr:02X}")
                except:
                    pass
            
            if not detected_devices:
                print("  ❌ No I2C devices found")
            else:
                print(f"\n📋 Total devices found: {len(detected_devices)}")
                
                # Check for known devices
                if 0x5A in detected_devices:
                    print("  🌡️  MLX90614 (0x5A) detected")
                if 0x57 in detected_devices:
                    print("  ❤️  MAX30102 (0x57) detected")
                    
    except Exception as e:
        print(f"❌ I2C scan error: {e}")
    
    input("\nNhấn Enter để tiếp tục...")

def test_config():
    """Test configuration loading"""
    print("\n--- Test Configuration Loading ---")
    
    config = load_config()
    
    print(f"📋 Config loaded: {'✅' if config else '❌'}")
    
    if config:
        sensors = config.get('sensors', {})
        print(f"\n🔧 Available sensors:")
        
        for sensor_name, sensor_config in sensors.items():
            enabled = sensor_config.get('enabled', False)
            status = "✅ Enabled" if enabled else "❌ Disabled"
            print(f"  • {sensor_name}: {status}")
            
        print(f"\n📊 MAX30102 Config:")
        max30102_config = sensors.get('max30102', {})
        for key, value in max30102_config.items():
            print(f"  • {key}: {value}")
            
        print(f"\n🌡️  MLX90614 Config:")
        mlx90614_config = sensors.get('mlx90614', {})
        for key, value in mlx90614_config.items():
            print(f"  • {key}: {value}")
    
    input("\nNhấn Enter để tiếp tục...")

def main_menu():
    """Main test menu"""
    while True:
        print("\n========== MENU TEST CẢM BIẾN ==========")
        print("1. Test cảm biến MAX30102 (nhịp tim & SpO2)")
        print("2. Test LED MAX30102 (kiểm tra LED có sáng)")
        print("3. Test cảm biến MLX90614 (nhiệt độ hồng ngoại)")
        print("4. Test raw GY-906 communication")
        print("5. Test cả hai cảm biến")
        print("6. Test system integration")
        print("7. Test configuration loading")
        print("8. Test I2C device detection")
        print("0. Thoát")
        print("=" * 40)
        
        choice = input("Chọn chức năng (0-8): ").strip()
        
        if choice == '1':
            test_max30102()
        elif choice == '2':
            test_max30102_led()
        elif choice == '3':
            test_mlx90614()
        elif choice == '4':
            test_gy906_raw()
        elif choice == '5':
            print("🔄 Testing cả hai cảm biến...")
            test_max30102()
            test_mlx90614()
        elif choice == '6':
            test_system_integration()
        elif choice == '7':
            test_config()
        elif choice == '8':
            test_i2c_devices()
        elif choice == '0':
            print("👋 Thoát chương trình.")
            break
        else:
            print("❌ Lựa chọn không hợp lệ. Vui lòng chọn lại.")

def test_system_integration():
    """Test both sensors running simultaneously"""
    print("\n--- Test tích hợp hệ thống (cả 2 sensor) ---")
    
    try:
        # Load config
        config = load_config()
        sensor_config = config.get('sensors', {})
        
        sensors = {}
        
        # Initialize MAX30102 if enabled
        if sensor_config.get('max30102', {}).get('enabled', False) and max30102 and hrcalc:
            sensors['max30102'] = MAX30102Sensor(sensor_config['max30102'])
            
        # Initialize MLX90614 if enabled  
        if sensor_config.get('mlx90614', {}).get('enabled', False) and SMBus:
            sensors['mlx90614'] = MLX90614Sensor(sensor_config['mlx90614'])
        
        if not sensors:
            print("❌ Không có sensor nào được enable hoặc thiếu thư viện")
            return
            
        def integrated_callback(sensor_name, data):
            """Callback hiển thị data từ tất cả sensors"""
            timestamp = data.get('timestamp', 'N/A')
            print(f"\n📊 [{timestamp[-8:-3]}] {sensor_name}:")
            
            if sensor_name == 'MAX30102':
                if data['finger_detected']:
                    hr_status = "✅" if data['hr_valid'] else "❌"
                    spo2_status = "✅" if data['spo2_valid'] else "❌"
                    print(f"  ❤️  HR: {data['heart_rate']} BPM {hr_status}")
                    print(f"  🫁 SpO2: {data['spo2']:.1f}% {spo2_status}")
                    print(f"  📊 Status: {data['status']}")
                else:
                    print("  ⚠️  Đặt ngón tay lên cảm biến")
                    
            elif sensor_name == 'MLX90614':
                print(f"  🌡️  Temp: {data['temperature']:.2f}°C ({data['status']})")
                print(f"  🎯 Object: {data['object_temperature']:.2f}°C")
                print(f"  🌍 Ambient: {data['ambient_temperature']:.2f}°C")
        
        # Set callbacks and start sensors
        for name, sensor in sensors.items():
            sensor.set_data_callback(integrated_callback)
            if not sensor.start():
                print(f"❌ Không thể khởi động {name}")
                continue
            print(f"✅ {name} đã khởi động")
            
        print(f"\n🚀 Đang chạy {len(sensors)} sensor(s). Nhấn Ctrl+C để dừng...")
        
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n🔄 Dừng test tích hợp...")
            
    except Exception as e:
        print(f"❌ Lỗi test tích hợp: {e}")
    finally:
        # Stop all sensors
        for name, sensor in sensors.items():
            try:
                sensor.stop()
                print(f"✅ {name} đã dừng")
            except:
                pass


if __name__ == "__main__":
    main_menu()