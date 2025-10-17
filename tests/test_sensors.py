"""
Test Sensors - Menu-driven interface for hardware validation and calibration.

Supports I²C scanning, sensor testing, and calibration data collection.
Follows BaseSensor pattern and non-blocking design.
"""

import sys
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import sensor classes
try:
    from src.sensors.max30102_sensor import MAX30102Sensor, HRCalculator
    from src.sensors.mlx90614_sensor import MLX90614Sensor
    from src.sensors.base_sensor import BaseSensor
    import numpy as np
except ImportError as e:
    logging.error(f"Could not import sensor classes: {e}")
    MAX30102Sensor = None
    HRCalculator = None
    MLX90614Sensor = None
    BaseSensor = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/home/pi/Desktop/IoT_health/logs/test_sensors.log')
    ]
)
logger = logging.getLogger(__name__)

class SensorTester:
    """
    Menu-driven tester for sensors with calibration support.
    
    Provides options for I²C scanning, sensor testing, and calibration data collection.
    """
    
    def __init__(self):
        # Sửa type hint để tránh lỗi "Variable not allowed in type expression"
        # Dùng Any vì BaseSensor có thể là None nếu import fail
        self.sensors: Dict[str, Any] = {}
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load sensor config from app_config.yaml."""
        try:
            import yaml
            config_path = project_root / 'config' / 'app_config.yaml'
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config.get('sensors', {})
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def scan_i2c(self) -> None:
        """Scan I²C bus for connected devices."""
        try:
            import smbus
            bus = smbus.SMBus(1)  # I²C bus 1 on Pi
            logger.info("Scanning I²C bus 1...")
            found = []
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    found.append(hex(addr))
                except:
                    pass
            if found:
                logger.info(f"Found I²C devices: {', '.join(found)}")
            else:
                logger.warning("No I²C devices found")
        except ImportError:
            logger.error("smbus not available - install with: pip install smbus2")
        except Exception as e:
            logger.error(f"I²C scan failed: {e}")
    
    def test_max30102(self) -> None:
        """Test MAX30102 sensor basic functionality."""
        if not MAX30102Sensor:
            logger.error("MAX30102Sensor not available")
            return
        
        try:
            sensor = MAX30102Sensor(self.config.get('max30102', {}))
            sensor.initialize()
            sensor.begin_measurement_session()
            
            logger.info("Testing MAX30102 for 10 seconds...")
            start_time = time.time()
            while time.time() - start_time < 10:
                data = sensor.read_raw_data()
                if data:
                    logger.info(f"MAX30102 data: {data}")
                time.sleep(1)
            
            sensor.end_measurement_session()  # Fix: Use correct method name
            logger.info("MAX30102 test completed")
        except Exception as e:
            logger.error(f"MAX30102 test failed: {e}")
    
    def calibrate_max30102(self) -> None:
        """
        Collect calibration data for MAX30102 SpO₂.
        
        Runs measurement and collects R-values for manual calibration.
        User should compare with reference SpO₂ device.
        
        IMPORTANT: Measure your actual SpO₂ with a reference pulse oximeter
        and note the value along with the R-value for calibration curve update.
        """
        if not MAX30102Sensor or not HRCalculator:
            logger.error("MAX30102Sensor or HRCalculator not available")
            return
        
        r_values: List[float] = []
        
        # Prompt for reference SpO2 value
        print("\n" + "="*60)
        print("MAX30102 SpO₂ Calibration Tool")
        print("="*60)
        print("Before starting, please:")
        print("1. Place finger on MAX30102 sensor")
        print("2. Measure SpO₂ with reference pulse oximeter")
        print("3. Enter the reference SpO₂ value below")
        print("="*60)
        
        try:
            ref_spo2_str = input("Enter reference SpO₂ (70-100%, or press Enter to skip): ").strip()
            ref_spo2 = None
            if ref_spo2_str:
                ref_spo2 = float(ref_spo2_str)
                if not (70 <= ref_spo2 <= 100):
                    logger.warning("Invalid SpO₂ value, proceeding without reference")
                    ref_spo2 = None
                else:
                    logger.info(f"Reference SpO₂: {ref_spo2:.1f}%")
        except (ValueError, EOFError):
            logger.warning("No reference SpO₂ provided, proceeding without reference")
            ref_spo2 = None
        
        try:
            sensor = MAX30102Sensor(self.config.get('max30102', {}))
            sensor.initialize()
            sensor.begin_measurement_session()
            
            logger.info("Collecting MAX30102 calibration data for 30 seconds...")
            logger.info("Keep finger STILL on sensor for accurate measurement")
            logger.info("R-values will be logged - note them for calibration curve update")
            
            # Accumulate data for HRCalculator (needs at least BUFFER_SIZE = 100 samples)
            accumulated_ir = []
            accumulated_red = []
            sample_rate = self.config.get('max30102', {}).get('sample_rate', 50)
            
            start_time = time.time()
            while time.time() - start_time < 30:
                data = sensor.read_raw_data()
                if data and 'ir' in data and 'red' in data:
                    ir_samples = data['ir']
                    red_samples = data['red']
                    
                    if ir_samples and red_samples:
                        accumulated_ir.extend(ir_samples)
                        accumulated_red.extend(red_samples)
                        
                        logger.debug(f"Accumulated samples: IR={len(accumulated_ir)}, RED={len(accumulated_red)}")
                        
                        # When we have enough samples, calculate HR and SpO2
                        if len(accumulated_ir) >= 100 and len(accumulated_red) >= 100:
                            # Use the last 100 samples for calculation
                            ir_data = np.array(accumulated_ir[-100:])
                            red_data = np.array(accumulated_red[-100:])
                            
                            # Calculate HR and SpO2 using the same algorithm as GUI
                            hr, hr_valid, spo2, spo2_valid, sqi, cv, peak_count, current_r_values = HRCalculator.calc_hr_and_spo2(
                                ir_data, red_data, sample_rate=sample_rate
                            )
                            
                            # Log measurement results
                            logger.info(f"Measurement: HR={hr:.1f} BPM (valid={hr_valid}), "
                                      f"SpO2={spo2:.1f}% (valid={spo2_valid}), "
                                      f"SQI={sqi:.1f}%, CV={cv:.1f}%, peaks={peak_count}")
                            
                            # Use R-values from HRCalculator for calibration
                            if current_r_values:
                                r_median = float(np.median(current_r_values))
                                for r_val in current_r_values:
                                    r_values.append(r_val)
                                logger.info(f"R-values: median={r_median:.3f}, count={len(current_r_values)}, "
                                          f"range=[{min(current_r_values):.3f}-{max(current_r_values):.3f}]")
                            
                            # Reset accumulation for next measurement window
                            accumulated_ir = accumulated_ir[-50:]  # Keep some overlap
                            accumulated_red = accumulated_red[-50:]
                
                time.sleep(1)
            
            sensor.end_measurement_session()
            
            if r_values:
                avg_r = sum(r_values) / len(r_values)
                median_r = sorted(r_values)[len(r_values) // 2]
                std_r = (sum((r - avg_r) ** 2 for r in r_values) / len(r_values)) ** 0.5
                cv_r = (std_r / avg_r * 100) if avg_r > 0 else 0
                
                print("\n" + "="*60)
                print("CALIBRATION RESULTS")
                print("="*60)
                logger.info(f"Collected {len(r_values)} R-values")
                logger.info(f"Average R-value: {avg_r:.3f}")
                logger.info(f"Median R-value: {median_r:.3f}")
                logger.info(f"Standard deviation: {std_r:.3f} (CV={cv_r:.1f}%)")
                logger.info(f"R-value range: {min(r_values):.3f} - {max(r_values):.3f}")
                
                if ref_spo2 is not None:
                    print("="*60)
                    logger.info(f"Reference SpO₂: {ref_spo2:.1f}%")
                    logger.info(f"R-value at SpO₂={ref_spo2:.1f}%: {median_r:.3f}")
                    print("="*60)
                    logger.info("ACTION REQUIRED: Update calibration curve in max30102_sensor.py")
                    logger.info(f"Add calibration point: R={median_r:.3f} → SpO₂={ref_spo2:.1f}%")
                else:
                    print("="*60)
                    logger.warning("No reference SpO₂ provided - cannot update calibration curve")
                    logger.info("Please re-run with reference pulse oximeter for accurate calibration")
                
                print("="*60)
            else:
                logger.warning("No R-values collected - check sensor connection or finger placement")
                
        except Exception as e:
            logger.error(f"MAX30102 calibration failed: {e}")
            import traceback
            traceback.print_exc()
    
    def collect_reference_spo2(self) -> None:
        """
        Collect SpO₂ reference data for calibration curve update.
        
        This creates calibration points (R-value, SpO₂) that can be used
        to update the calibration curve in max30102_sensor.py.
        
        Process:
        1. Measure SpO₂ with reference pulse oximeter
        2. Enter reference SpO₂ value
        3. Place finger on MAX30102 sensor
        4. Collect R-values for 30 seconds
        5. Save calibration point to file
        """
        if not MAX30102Sensor:
            logger.error("MAX30102Sensor not available")
            return
        
        # Check if calibration data file exists
        calib_file = project_root / 'data' / 'spo2_calibration_points.csv'
        
        print("\n" + "="*70)
        print("SpO₂ REFERENCE DATA COLLECTION")
        print("="*70)
        print("This will create calibration points for accurate SpO₂ measurement.")
        print("You need a reference pulse oximeter (standard medical device).")
        print("")
        print("STEPS:")
        print("1. Measure your SpO₂ with reference device")
        print("2. Enter the reference SpO₂ value below")
        print("3. Place SAME finger on MAX30102 sensor")
        print("4. Keep finger STILL for 30 seconds")
        print("5. Calibration point will be saved")
        print("="*70)
        
        # Get reference SpO2
        try:
            ref_spo2_str = input("Enter reference SpO₂ (70-100%): ").strip()
            ref_spo2 = float(ref_spo2_str)
            if not (70 <= ref_spo2 <= 100):
                logger.error("SpO₂ must be between 70-100%")
                return
        except (ValueError, EOFError):
            logger.error("Invalid SpO₂ value")
            return
        
        logger.info(f"Reference SpO₂: {ref_spo2:.1f}%")
        
        # Confirm finger placement
        input("Press Enter when finger is placed on MAX30102 sensor...")
        
        r_values: List[float] = []
        
        try:
            sensor = MAX30102Sensor(self.config.get('max30102', {}))
            sensor.initialize()
            sensor.begin_measurement_session()
            
            logger.info("Collecting R-values for 30 seconds...")
            logger.info("Keep finger COMPLETELY STILL for accurate calibration")
            
            # Accumulate data for HRCalculator (needs at least BUFFER_SIZE = 100 samples)
            accumulated_ir = []
            accumulated_red = []
            sample_rate = self.config.get('max30102', {}).get('sample_rate', 50)
            
            start_time = time.time()
            while time.time() - start_time < 30:
                data = sensor.read_raw_data()
                if data and 'ir' in data and 'red' in data:
                    ir_samples = data['ir']
                    red_samples = data['red']
                    
                    if ir_samples and red_samples:
                        accumulated_ir.extend(ir_samples)
                        accumulated_red.extend(red_samples)
                        
                        logger.debug(f"Accumulated samples: IR={len(accumulated_ir)}, RED={len(accumulated_red)}")
                        
                        # When we have enough samples, calculate HR and SpO2
                        if len(accumulated_ir) >= 100 and len(accumulated_red) >= 100:
                            # Use the last 100 samples for calculation
                            ir_data = np.array(accumulated_ir[-100:])
                            red_data = np.array(accumulated_red[-100:])
                            
                            # Calculate HR and SpO2 using the same algorithm as GUI
                            hr, hr_valid, spo2, spo2_valid, sqi, cv, peak_count, current_r_values = HRCalculator.calc_hr_and_spo2(
                                ir_data, red_data, sample_rate=sample_rate
                            )
                            
                            # Log measurement results
                            logger.info(f"Measurement: HR={hr:.1f} BPM (valid={hr_valid}), "
                                      f"SpO2={spo2:.1f}% (valid={spo2_valid}), "
                                      f"SQI={sqi:.1f}%, CV={cv:.1f}%, peaks={peak_count}")
                            
                            # Use R-values from HRCalculator for calibration
                            if current_r_values:
                                for r_val in current_r_values:
                                    r_values.append(r_val)
                                logger.info(f"R-values collected: {len(current_r_values)} (total={len(r_values)})")
                            
                            # Reset accumulation for next measurement window
                            accumulated_ir = accumulated_ir[-50:]  # Keep some overlap
                            accumulated_red = accumulated_red[-50:]
                
                time.sleep(1)
            
            sensor.end_measurement_session()
            
            if not r_values:
                logger.error("No R-values collected - check sensor connection")
                return
            
            # Calculate statistics
            avg_r = sum(r_values) / len(r_values)
            median_r = sorted(r_values)[len(r_values) // 2]
            std_r = (sum((r - avg_r) ** 2 for r in r_values) / len(r_values)) ** 0.5
            cv_r = (std_r / avg_r * 100) if avg_r > 0 else 0
            
            # Save calibration point
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Create data directory if not exists
            calib_file.parent.mkdir(exist_ok=True)
            
            # Check if file exists to determine if we need header
            file_exists = calib_file.exists()
            
            with open(calib_file, 'a') as f:
                if not file_exists:
                    f.write("# SpO₂ Calibration Points\n")
                    f.write("# Format: timestamp,reference_spo2,r_median,r_avg,r_std,cv_percent,count\n")
                
                f.write(f"{timestamp},{ref_spo2:.1f},{median_r:.4f},{avg_r:.4f},{std_r:.4f},{cv_r:.2f},{len(r_values)}\n")
            
            print("\n" + "="*70)
            print("CALIBRATION POINT SAVED")
            print("="*70)
            logger.info(f"Reference SpO₂: {ref_spo2:.1f}%")
            logger.info(f"R-value (median): {median_r:.4f}")
            logger.info(f"R-value (avg): {avg_r:.4f}")
            logger.info(f"R-value stability: CV={cv_r:.2f}% ({len(r_values)} samples)")
            logger.info(f"Saved to: {calib_file}")
            print("="*70)
            
            # Show current calibration curve prediction
            if 0.4 <= median_r <= 2.5:
                if median_r < 0.7:
                    predicted = -45.060 * (median_r ** 2) + 30.054 * median_r + 94.845
                elif median_r < 1.5:
                    predicted = 95.0 - 12.5 * (median_r - 0.7)
                else:
                    predicted = 85.0 - 15.0 * (median_r - 1.5)
                
                predicted = max(70.0, min(100.0, predicted))
                
                print("CURRENT CALIBRATION PREDICTION:")
                logger.info(f"Predicted SpO₂: {predicted:.1f}% (vs reference {ref_spo2:.1f}%)")
                logger.info(f"Difference: {predicted - ref_spo2:.1f}%")
                
                if abs(predicted - ref_spo2) > 5:
                    print("⚠️  LARGE DIFFERENCE - Calibration curve needs update!")
                    logger.warning("Calibration curve may need adjustment for this R-value range")
                else:
                    print("✅ Good match - Current calibration is reasonable")
            else:
                logger.warning(f"R-value {median_r:.3f} outside calibration range")
            
            print("="*70)
            print("NEXT STEPS:")
            print("1. Repeat with different SpO₂ levels (exercise, breath holding, etc.)")
            print("2. Collect 5-10 calibration points across SpO₂ range 80-100%")
            print("3. Run calibration curve fitting script (to be implemented)")
            print("4. Update max30102_sensor.py with new calibration curve")
            print("="*70)
            
        except Exception as e:
            logger.error(f"Reference data collection failed: {e}")
            import traceback
            traceback.print_exc()
    
    def show_calibration_points(self) -> None:
        """
        Display current SpO₂ calibration points and statistics.
        """
        calib_file = project_root / 'data' / 'spo2_calibration_points.csv'
        
        if not calib_file.exists():
            logger.info("No calibration points found")
            logger.info(f"File location: {calib_file}")
            logger.info("Use option 5 to collect reference data first")
            return
        
        try:
            points = []
            with open(calib_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    parts = line.split(',')
                    if len(parts) >= 3:
                        timestamp = parts[0]
                        ref_spo2 = float(parts[1])
                        r_median = float(parts[2])
                        points.append((timestamp, ref_spo2, r_median))
            
            if not points:
                logger.info("No valid calibration points found")
                return
            
            print("\n" + "="*80)
            print("CURRENT SpO₂ CALIBRATION POINTS")
            print("="*80)
            print(f"{'Timestamp':<20} {'Ref SpO₂':<10} {'R-value':<10} {'Predicted':<10} {'Diff':<8}")
            print("-" * 80)
            
            total_diff = 0
            for timestamp, ref_spo2, r_val in points:
                # Calculate current prediction
                if r_val < 0.7:
                    predicted = -45.060 * (r_val ** 2) + 30.054 * r_val + 94.845
                elif r_val < 1.5:
                    predicted = 95.0 - 12.5 * (r_val - 0.7)
                else:
                    predicted = 85.0 - 15.0 * (r_val - 1.5)
                
                predicted = max(70.0, min(100.0, predicted))
                diff = predicted - ref_spo2
                total_diff += abs(diff)
                
                print(f"{timestamp:<20} {ref_spo2:<10.1f} {r_val:<10.3f} {predicted:<10.1f} {diff:<8.1f}")
            
            avg_error = total_diff / len(points)
            print("-" * 80)
            logger.info(f"Total points: {len(points)}")
            logger.info(f"Average absolute error: {avg_error:.1f}%")
            
            if avg_error > 3:
                print("⚠️  HIGH ERROR - Calibration curve needs improvement!")
                logger.warning("Consider collecting more points or adjusting calibration curve")
            else:
                print("✅ Good calibration accuracy")
            
            print("="*80)
            
        except Exception as e:
            logger.error(f"Failed to read calibration points: {e}")
    
    def test_mlx90614(self) -> None:
        """Test MLX90614 sensor basic functionality."""
        if not MLX90614Sensor:
            logger.error("MLX90614Sensor not available")
            return
        
        try:
            sensor = MLX90614Sensor(self.config.get('mlx90614', {}))
            sensor.initialize()
            
            logger.info("Testing MLX90614 for 10 seconds...")
            start_time = time.time()
            while time.time() - start_time < 10:
                data = sensor.read_raw_data()
                if data:
                    logger.info(f"MLX90614 data: {data}")
                time.sleep(1)
            
            sensor.close()
            logger.info("MLX90614 test completed")
        except Exception as e:
            logger.error(f"MLX90614 test failed: {e}")
    
    def run_menu(self) -> None:
        """Run interactive menu for sensor testing."""
        while True:
            print("\n=== Sensor Test Menu ===")
            print("1. Scan I²C bus")
            print("2. Test MAX30102")
            print("3. Calibrate MAX30102 (collect R-values)")
            print("4. Test MLX90614")
            print("5. Collect SpO₂ Reference Data (with reference device)")
            print("6. Show Calibration Points")
            print("7. Exit")
            
            try:
                choice = input("Select option (1-7): ").strip()
                
                if choice == '1':
                    self.scan_i2c()
                elif choice == '2':
                    self.test_max30102()
                elif choice == '3':
                    self.calibrate_max30102()
                elif choice == '4':
                    self.test_mlx90614()
                elif choice == '5':
                    self.collect_reference_spo2()
                elif choice == '6':
                    self.show_calibration_points()
                elif choice == '7':
                    logger.info("Exiting sensor tester")
                    break
                else:
                    print("Invalid choice")
                    
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Menu error: {e}")

def main():
    """Main entry point."""
    tester = SensorTester()
    tester.run_menu()

if __name__ == '__main__':
    main()