#!/usr/bin/env python3
"""
Test Suite for IoT Health Monitoring Sensors
Comprehensive testing program for MAX30102, MLX90614, and other sensors
"""
import sys
import os
import time
import threading
import signal
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import sensor modules
from src.sensors.max30102_sensor import MAX30102Sensor
from src.sensors.mlx90614_sensor import MLX90614Sensor
from src.sensors.blood_pressure_sensor import BloodPressureSensor
from src.utils.logger import setup_logger

class SensorTestSuite:
    """
    Comprehensive test suite for all IoT health monitoring sensors
    """
    
    def __init__(self):
        """Initialize test suite"""
        self.logger = logging.getLogger("TestSuite")
        self.logger.setLevel(logging.INFO)
        
        # Create console handler if not exists
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self.config = self.load_config()
        self.sensors = {}
        self.test_running = False
        self.test_threads = []
        
        # Register signal handler for clean shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from app_config.yaml"""
        try:
            config_path = project_root / "config" / "app_config.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.logger.info(f"Configuration loaded from {config_path}")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return {}
    
    def signal_handler(self, signum, frame):
        """Handle interrupt signals for clean shutdown"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop_all_tests()
        sys.exit(0)
    
    def stop_all_tests(self):
        """Stop all running tests and sensors"""
        self.test_running = False
        
        # Stop all sensors
        for sensor_name, sensor in self.sensors.items():
            try:
                if sensor and hasattr(sensor, 'stop'):
                    sensor.stop()
                    self.logger.info(f"Stopped {sensor_name} sensor")
            except Exception as e:
                self.logger.error(f"Error stopping {sensor_name}: {e}")
        
        # Wait for test threads to complete
        for thread in self.test_threads:
            if thread.is_alive():
                thread.join(timeout=2)
    
    def print_menu(self):
        """Print main test menu"""
        print("\n" + "="*60)
        print("🏥 IoT HEALTH MONITORING - SENSOR TEST SUITE")
        print("="*60)
        print("1. 🫀 Test MAX30102 (Heart Rate & SpO2)")
        print("2. 🌡️  Test MLX90614 (Temperature)")
        print("3. 🩸 Test Blood Pressure System")
        print("4. 🔍 I2C Device Scan")
        print("5. 📊 Real-time Monitoring Dashboard")
        print("6. 🧪 Hardware Validation Tests")
        print("7. 📈 Sensor Performance Analysis")
        print("8. 🔧 Sensor Configuration Test")
        print("9. 💾 Data Logging Test")
        print("0. ❌ Exit")
        print("="*60)
    
    def test_max30102_comprehensive(self):
        """Comprehensive MAX30102 sensor test"""
        print("\n🫀 MAX30102 COMPREHENSIVE TEST")
        print("-" * 40)
        
        try:
            # Initialize sensor
            max30102_config = self.config.get('sensors', {}).get('max30102', {})
            sensor = MAX30102Sensor(max30102_config)
            self.sensors['max30102'] = sensor
            
            # Test 1: Hardware initialization
            print("🔧 Testing hardware initialization...")
            if not sensor.initialize():
                print("❌ Hardware initialization failed!")
                return False
            print("✅ Hardware initialized successfully")
            
            # Test 2: Start sensor
            print("🚀 Starting sensor...")
            if not sensor.start():
                print("❌ Sensor start failed!")
                return False
            print("✅ Sensor started successfully")
            
            # Test 3: LED configuration test
            print("💡 Testing LED configuration...")
            led_test_passed = self.test_max30102_leds(sensor)
            
            # Test 4: Real-time data collection
            print("📊 Starting real-time data collection...")
            print("📌 Place your finger on the sensor and keep it steady")
            print("⏱️  Data collection will run for 30 seconds")
            print("🛑 Press Ctrl+C to stop early")
            
            self.test_running = True
            data_collection_thread = threading.Thread(
                target=self.max30102_data_collection,
                args=(sensor, 30)
            )
            data_collection_thread.start()
            self.test_threads.append(data_collection_thread)
            
            # Wait for data collection to complete
            data_collection_thread.join()
            
            # Test 5: Signal quality assessment
            print("📈 Assessing signal quality...")
            self.assess_max30102_signal_quality(sensor)
            
            # Test 6: Measurement validation
            print("🔍 Validating measurements...")
            self.validate_max30102_measurements(sensor)
            
            print("✅ MAX30102 comprehensive test completed")
            return True
            
        except Exception as e:
            self.logger.error(f"MAX30102 test failed: {e}")
            print(f"❌ Test failed: {e}")
            return False
        finally:
            if 'max30102' in self.sensors and self.sensors['max30102']:
                self.sensors['max30102'].stop()
    
    def test_max30102_leds(self, sensor: MAX30102Sensor) -> bool:
        """Test MAX30102 LED functionality"""
        try:
            print("  🔴 Testing RED LED...")
            if sensor.set_led_amplitude(0x7F, 0x00):  # RED only
                time.sleep(2)
                print("  ✅ RED LED test passed")
            else:
                print("  ❌ RED LED test failed")
                return False
            
            print("  🔵 Testing IR LED...")
            if sensor.set_led_amplitude(0x00, 0x7F):  # IR only
                time.sleep(2)
                print("  ✅ IR LED test passed")
            else:
                print("  ❌ IR LED test failed")
                return False
            
            print("  🟣 Testing both LEDs...")
            if sensor.set_led_amplitude(0x7F, 0x7F):  # Both LEDs
                time.sleep(2)
                print("  ✅ Both LEDs test passed")
            else:
                print("  ❌ Both LEDs test failed")
                return False
            
            return True
            
        except Exception as e:
            print(f"  ❌ LED test failed: {e}")
            return False
    
    def max30102_data_collection(self, sensor: MAX30102Sensor, duration: int):
        """Collect and display MAX30102 data in real-time"""
        start_time = time.time()
        sample_count = 0
        valid_readings = 0
        
        print(f"\n{'Time':<8} {'HR':<6} {'SpO2':<6} {'Finger':<8} {'Status':<15} {'Quality':<8}")
        print("-" * 65)
        
        while self.test_running and (time.time() - start_time) < duration:
            try:
                # Get sensor data through callback mechanism
                if hasattr(sensor, 'heart_rate') and hasattr(sensor, 'spo2'):
                    elapsed = int(time.time() - start_time)
                    hr = sensor.heart_rate
                    spo2 = sensor.spo2
                    finger = "YES" if sensor.finger_detected else "NO"
                    status = getattr(sensor, 'status', 'Unknown')
                    quality = f"{sensor.signal_quality_ir:.1f}" if hasattr(sensor, 'signal_quality_ir') else "N/A"
                    
                    print(f"{elapsed:>3}s     {hr:>5.1f} {spo2:>5.1f}  {finger:<8} {status:<15} {quality:<8}")
                    
                    sample_count += 1
                    if sensor.hr_valid or sensor.spo2_valid:
                        valid_readings += 1
                
                time.sleep(1)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Data collection error: {e}")
                break
        
        self.test_running = False
        print(f"\n📊 Data Collection Summary:")
        print(f"   Total samples: {sample_count}")
        print(f"   Valid readings: {valid_readings}")
        print(f"   Success rate: {(valid_readings/max(sample_count,1)*100):.1f}%")
    
    def assess_max30102_signal_quality(self, sensor: MAX30102Sensor):
        """Assess MAX30102 signal quality"""
        try:
            stability = sensor.get_measurement_stability()
            
            print("  📈 Signal Quality Assessment:")
            print(f"     HR Stability: {stability.get('hr_stability', 0):.2f}")
            print(f"     SpO2 Stability: {stability.get('spo2_stability', 0):.2f}")
            print(f"     IR Signal Quality: {sensor.signal_quality_ir:.1f}")
            print(f"     RED Signal Quality: {sensor.signal_quality_red:.1f}")
            
            # Overall quality assessment
            avg_quality = (sensor.signal_quality_ir + sensor.signal_quality_red) / 2
            if avg_quality > 80:
                print("  ✅ Excellent signal quality")
            elif avg_quality > 60:
                print("  ⚠️  Good signal quality")
            elif avg_quality > 40:
                print("  ⚠️  Fair signal quality - consider repositioning finger")
            else:
                print("  ❌ Poor signal quality - check sensor placement")
                
        except Exception as e:
            print(f"  ❌ Signal quality assessment failed: {e}")
    
    def validate_max30102_measurements(self, sensor: MAX30102Sensor):
        """Validate MAX30102 measurements"""
        try:
            hr = sensor.heart_rate
            spo2 = sensor.spo2
            
            print("  🔍 Measurement Validation:")
            
            # Heart rate validation
            hr_status = sensor.get_heart_rate_status()
            hr_valid = sensor.validate_heart_rate(hr)
            print(f"     Heart Rate: {hr:.1f} BPM - {hr_status} ({'Valid' if hr_valid else 'Invalid'})")
            
            # SpO2 validation  
            spo2_status = sensor.get_spo2_status()
            spo2_valid = sensor.validate_spo2(spo2)
            print(f"     SpO2: {spo2:.1f}% - {spo2_status} ({'Valid' if spo2_valid else 'Invalid'})")
            
            # Overall assessment
            if hr_valid and spo2_valid:
                print("  ✅ All measurements are valid")
            elif hr_valid or spo2_valid:
                print("  ⚠️  Some measurements are valid")
            else:
                print("  ❌ Measurements need improvement")
                
        except Exception as e:
            print(f"  ❌ Measurement validation failed: {e}")
    
    def test_mlx90614(self):
        """Test MLX90614 temperature sensor"""
        print("\n🌡️ MLX90614 TEMPERATURE SENSOR TEST")
        print("-" * 40)
        
        try:
            # Initialize sensor
            mlx_config = self.config.get('sensors', {}).get('mlx90614', {})
            sensor = MLX90614Sensor(mlx_config)
            self.sensors['mlx90614'] = sensor
            
            # Test initialization
            print("🔧 Testing sensor initialization...")
            if not sensor.initialize():
                print("❌ Sensor initialization failed!")
                return False
            print("✅ Sensor initialized successfully")
            
            # Start sensor
            print("🚀 Starting sensor...")
            if not sensor.start():
                print("❌ Sensor start failed!")
                return False
            print("✅ Sensor started successfully")
            
            # Collect temperature data
            print("📊 Collecting temperature data for 15 seconds...")
            print("📌 Point sensor towards your forehead")
            
            self.test_running = True
            start_time = time.time()
            
            print(f"\n{'Time':<8} {'Object':<8} {'Ambient':<8} {'Status':<15}")
            print("-" * 45)
            
            while self.test_running and (time.time() - start_time) < 15:
                try:
                    elapsed = int(time.time() - start_time)
                    obj_temp = getattr(sensor, 'object_temperature', 0)
                    amb_temp = getattr(sensor, 'ambient_temperature', 0)
                    status = getattr(sensor, 'status', 'Unknown')
                    
                    print(f"{elapsed:>3}s     {obj_temp:>6.2f}°C {amb_temp:>6.2f}°C {status:<15}")
                    
                    time.sleep(1)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.logger.error(f"Temperature reading error: {e}")
                    break
            
            print("✅ MLX90614 test completed")
            return True
            
        except Exception as e:
            self.logger.error(f"MLX90614 test failed: {e}")
            print(f"❌ Test failed: {e}")
            return False
        finally:
            if 'mlx90614' in self.sensors and self.sensors['mlx90614']:
                self.sensors['mlx90614'].stop()
    
    def scan_i2c_devices(self):
        """Scan for I2C devices"""
        print("\n🔍 I2C DEVICE SCAN")
        print("-" * 30)
        
        try:
            import smbus
            bus = smbus.SMBus(1)  # I2C bus 1
            
            devices_found = []
            expected_devices = {
                0x57: "MAX30102 (Heart Rate/SpO2)",
                0x5A: "MLX90614 (Temperature)"
            }
            
            print("Scanning I2C addresses 0x03-0x77...")
            
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    devices_found.append(addr)
                    device_name = expected_devices.get(addr, "Unknown device")
                    print(f"✅ Found device at 0x{addr:02X}: {device_name}")
                except:
                    pass
            
            if not devices_found:
                print("❌ No I2C devices found!")
                print("   Check connections and ensure I2C is enabled")
            else:
                print(f"\n📊 Scan complete: {len(devices_found)} device(s) found")
                
                # Check for expected devices
                missing_devices = []
                for addr, name in expected_devices.items():
                    if addr not in devices_found:
                        missing_devices.append(f"0x{addr:02X} ({name})")
                
                if missing_devices:
                    print("⚠️  Missing expected devices:")
                    for device in missing_devices:
                        print(f"   - {device}")
            
            return len(devices_found) > 0
            
        except ImportError:
            print("❌ smbus library not available")
            return False
        except Exception as e:
            print(f"❌ I2C scan failed: {e}")
            return False
    
    def real_time_dashboard(self):
        """Real-time monitoring dashboard"""
        print("\n📊 REAL-TIME MONITORING DASHBOARD")
        print("-" * 45)
        print("🚀 Starting all sensors...")
        
        try:
            # Initialize all sensors
            sensors_to_start = []
            
            # MAX30102
            if self.config.get('sensors', {}).get('max30102', {}).get('enabled', False):
                max30102 = MAX30102Sensor(self.config['sensors']['max30102'])
                if max30102.initialize() and max30102.start():
                    self.sensors['max30102'] = max30102
                    sensors_to_start.append('MAX30102')
                    print("✅ MAX30102 started")
                else:
                    print("❌ MAX30102 failed to start")
            
            # MLX90614
            if self.config.get('sensors', {}).get('mlx90614', {}).get('enabled', False):
                mlx90614 = MLX90614Sensor(self.config['sensors']['mlx90614'])
                if mlx90614.initialize() and mlx90614.start():
                    self.sensors['mlx90614'] = mlx90614
                    sensors_to_start.append('MLX90614')
                    print("✅ MLX90614 started")
                else:
                    print("❌ MLX90614 failed to start")
            
            if not sensors_to_start:
                print("❌ No sensors available for monitoring")
                return
            
            # Start monitoring
            print(f"\n📈 Monitoring {len(sensors_to_start)} sensor(s)")
            print("📌 Place finger on MAX30102 and point MLX90614 to forehead")
            print("🛑 Press Ctrl+C to stop monitoring")
            
            self.test_running = True
            start_time = time.time()
            
            # Print header
            header = f"{'Time':<8}"
            if 'MAX30102' in sensors_to_start:
                header += f" {'HR':<6} {'SpO2':<6} {'Finger':<8}"
            if 'MLX90614' in sensors_to_start:
                header += f" {'Temp':<7}"
            print(f"\n{header}")
            print("-" * len(header))
            
            while self.test_running:
                try:
                    elapsed = int(time.time() - start_time)
                    row = f"{elapsed:>3}s    "
                    
                    # MAX30102 data
                    if 'max30102' in self.sensors:
                        sensor = self.sensors['max30102']
                        hr = getattr(sensor, 'heart_rate', 0)
                        spo2 = getattr(sensor, 'spo2', 0)
                        finger = "YES" if getattr(sensor, 'finger_detected', False) else "NO"
                        row += f" {hr:>5.1f} {spo2:>5.1f}  {finger:<8}"
                    
                    # MLX90614 data
                    if 'mlx90614' in self.sensors:
                        sensor = self.sensors['mlx90614']
                        temp = getattr(sensor, 'object_temperature', 0)
                        row += f" {temp:>6.2f}°C"
                    
                    print(row)
                    time.sleep(2)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.logger.error(f"Dashboard error: {e}")
                    break
            
            print("\n📊 Real-time monitoring stopped")
            
        except Exception as e:
            self.logger.error(f"Dashboard failed: {e}")
            print(f"❌ Dashboard failed: {e}")
        finally:
            self.test_running = False
    
    def hardware_validation(self):
        """Hardware validation tests"""
        print("\n🧪 HARDWARE VALIDATION TESTS")
        print("-" * 35)
        
        validation_results = {}
        
        # Test 1: I2C bus functionality
        print("1️⃣ Testing I2C bus functionality...")
        i2c_result = self.scan_i2c_devices()
        validation_results['i2c'] = i2c_result
        
        # Test 2: GPIO availability (if needed for future sensors)
        print("\n2️⃣ Testing GPIO availability...")
        gpio_result = self.test_gpio_availability()
        validation_results['gpio'] = gpio_result
        
        # Test 3: System resources
        print("\n3️⃣ Testing system resources...")
        resource_result = self.test_system_resources()
        validation_results['resources'] = resource_result
        
        # Summary
        print(f"\n📊 VALIDATION SUMMARY")
        print("-" * 25)
        passed = sum(1 for result in validation_results.values() if result)
        total = len(validation_results)
        
        for test, result in validation_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {test.upper()}: {status}")
        
        print(f"\n🎯 Overall: {passed}/{total} tests passed")
        
        if passed == total:
            print("✅ All hardware validation tests passed!")
        else:
            print("⚠️  Some hardware validation tests failed")
            print("   Please check hardware connections and system configuration")
    
    def test_gpio_availability(self) -> bool:
        """Test GPIO availability"""
        try:
            # Check if GPIO is available
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            print("   ✅ GPIO library available")
            GPIO.cleanup()
            return True
        except ImportError:
            print("   ❌ RPi.GPIO library not available")
            return False
        except Exception as e:
            print(f"   ❌ GPIO test failed: {e}")
            return False
    
    def test_system_resources(self) -> bool:
        """Test system resources"""
        try:
            import psutil
            
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            print(f"   📊 CPU Usage: {cpu_percent:.1f}%")
            
            # Check memory usage
            memory = psutil.virtual_memory()
            print(f"   💾 Memory Usage: {memory.percent:.1f}%")
            
            # Check available space
            disk = psutil.disk_usage('/')
            print(f"   💿 Disk Usage: {disk.percent:.1f}%")
            
            # All good if CPU < 80%, Memory < 80%, Disk < 90%
            if cpu_percent < 80 and memory.percent < 80 and disk.percent < 90:
                print("   ✅ System resources OK")
                return True
            else:
                print("   ⚠️  High system resource usage detected")
                return False
                
        except ImportError:
            print("   ⚠️  psutil not available, skipping resource check")
            return True
        except Exception as e:
            print(f"   ❌ Resource test failed: {e}")
            return False
    
    def run_tests(self):
        """Main test runner"""
        print("🏥 IoT Health Monitoring - Sensor Test Suite")
        print("=" * 50)
        
        while True:
            try:
                self.print_menu()
                choice = input("\n👉 Select test option (0-9): ").strip()
                
                if choice == '0':
                    print("\n👋 Exiting test suite...")
                    self.stop_all_tests()
                    break
                elif choice == '1':
                    self.test_max30102_comprehensive()
                elif choice == '2':
                    self.test_mlx90614()
                elif choice == '3':
                    print("\n🩸 Blood pressure test not yet implemented")
                elif choice == '4':
                    self.scan_i2c_devices()
                elif choice == '5':
                    self.real_time_dashboard()
                elif choice == '6':
                    self.hardware_validation()
                elif choice == '7':
                    print("\n📈 Performance analysis not yet implemented")
                elif choice == '8':
                    print("\n🔧 Configuration test not yet implemented")
                elif choice == '9':
                    print("\n💾 Data logging test not yet implemented")
                else:
                    print("❌ Invalid option. Please select 0-9.")
                
                if choice != '0':
                    input("\n📌 Press Enter to continue...")
                    
            except KeyboardInterrupt:
                print("\n\n🛑 Test interrupted by user")
                self.stop_all_tests()
                break
            except Exception as e:
                self.logger.error(f"Test runner error: {e}")
                print(f"❌ Error: {e}")
                input("\n📌 Press Enter to continue...")


def main():
    """Main function"""
    print("🚀 Starting IoT Health Sensor Test Suite...")
    
    test_suite = SensorTestSuite()
    test_suite.run_tests()
    
    print("👋 Test suite finished. Goodbye!")


if __name__ == "__main__":
    main()
