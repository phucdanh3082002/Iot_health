#!/usr/bin/env python3
"""
Blood Pressure Calibration Tool
================================

Tool để hiệu chỉnh HX710B ADC và thuật toán oscillometric.

Usage:
------
python tests/bp_calibration_tool.py

Menu:
  1. Phase 1: ADC Calibration (offset + slope)
  2. Phase 2: Algorithm Calibration (sys_frac + dia_frac)
  3. Update config với kết quả mới
  0. Exit

Author: IoT Health Monitor Team
Date: 2025-10-25
"""

import logging
import time
import numpy as np
from typing import List, Tuple, Dict
import yaml
import matplotlib.pyplot as plt
from scipy import stats
from pathlib import Path
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("BP_Calibration")

# Import sensors
sys.path.append('/home/pi/Desktop/IoT_health')
from src.sensors.hx710b_sensor import HX710BSensor
from src.sensors.blood_pressure_sensor import BloodPressureSensor, BloodPressureMeasurement

try:
    import RPi.GPIO as GPIO
except ImportError:
    logger.warning("RPi.GPIO not available - using mock")
    GPIO = None


# ==================== PHASE 1: ADC CALIBRATION ====================

class ADCCalibrator:
    """
    Hiệu chỉnh HX710B ADC: offset + slope
    
    Method:
    ------
    1. Zero calibration: offset_counts (at 0 mmHg)
    2. Span calibration: slope_mmhg_per_count (linear fit với máy thương mại)
    """
    
    def __init__(self, sensor: HX710BSensor):
        self.sensor = sensor
        self.logger = logging.getLogger("ADC_Calibrator")
    
    def calibrate_zero(self, num_samples: int = 100) -> int:
        """
        Zero calibration (cuff deflated)
        
        Steps:
        1. Đảm bảo cuff xả hết (0 mmHg)
        2. Đọc num_samples từ HX710B
        3. Lấy median làm offset
        
        Args:
            num_samples: Số samples để average
        
        Returns:
            offset_counts: Zero offset value
        """
        self.logger.info("Starting zero calibration...")
        self.logger.info("⚠️  Ensure cuff is DEFLATED (0 mmHg)")
        input("Press ENTER when ready...")
        
        samples = []
        
        self.logger.info(f"Collecting {num_samples} samples...")
        for i in range(num_samples):
            raw = self.sensor.read_raw_data()
            if raw is not None:
                samples.append(raw)
                print(f"Sample {i+1}/{num_samples}: {raw}", end='\r')
            time.sleep(0.1)
        
        print()  # New line
        
        if len(samples) < num_samples * 0.8:
            self.logger.error(f"Insufficient samples: {len(samples)}/{num_samples}")
            return None
        
        offset = int(np.median(samples))
        std = np.std(samples)
        
        self.logger.info(f"✅ Zero calibration complete:")
        self.logger.info(f"   offset_counts: {offset}")
        self.logger.info(f"   Std dev: {std:.1f} counts")
        
        return offset
    
    def calibrate_span_empirical(
        self,
        num_measurements: int = 10
    ) -> Tuple[float, float]:
        """
        Span calibration THỰC NGHIỆM - Đo nhiều lần và so sánh với máy thương mại
        
        Method:
        ------
        1. Đo BP bằng IoT device (ghi counts peak khi SYS)
        2. Đo BP bằng máy thương mại riêng (nhập SYS làm reference)
        3. Lặp lại nhiều lần
        4. Linear regression: SYS_ref vs counts → slope
        
        Workflow:
        --------
        - Session A: Đo bằng IoT (có counts tại SYS)
        - Session B: Đo bằng máy TM (có SYS reference)
        - Ghép cặp theo thời gian gần nhất
        - Fit: pressure = slope × counts
        
        Args:
            num_measurements: Số lần đo (khuyến nghị ≥10)
        
        Returns:
            (slope_mmhg_per_count, r_squared)
        """
        self.logger.info("Starting EMPIRICAL span calibration...")
        self.logger.info("\n📋 PHƯƠNG PHÁP:")
        self.logger.info("   Đo BP nhiều lần bằng cả IoT và máy thương mại")
        self.logger.info("   → So sánh kết quả → tính slope chính xác")
        self.logger.info("\n⚠️  YÊU CẦU:")
        self.logger.info(f"   - Cần ≥{num_measurements} phép đo")
        self.logger.info("   - Đo xen kẽ: IoT → nghỉ 2 phút → Máy TM → lặp lại")
        self.logger.info("   - Ngồi yên, thư giãn khi đo")
        self.logger.info("\n💡 CÁCH HOẠT ĐỘNG:")
        self.logger.info("   1. Tool sẽ bơm và ghi 'counts tại áp cao nhất'")
        self.logger.info("   2. Bạn nhập SYS từ máy TM (đo riêng)")
        self.logger.info("   3. Tool tính: slope = SYS / (counts - offset)")
        input("\n   Press ENTER khi sẵn sàng...")
        
        # Get current offset
        offset = self.sensor.calibration.get('offset_counts', 0)
        self.logger.info(f"\n📊 Using offset: {offset} counts")
        
        if GPIO is None:
            self.logger.error("GPIO not available")
            return None, None
        
        # Setup GPIO for pump/valve control
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        pump_gpio = 26
        valve_gpio = 16
        
        GPIO.setup(pump_gpio, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(valve_gpio, GPIO.OUT, initial=GPIO.LOW)
        
        pressure_ref = []  # SYS from commercial device
        counts_data = []   # Max counts from IoT (corresponds to SYS)
        
        try:
            for i in range(num_measurements):
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"MEASUREMENT {i+1}/{num_measurements}")
                self.logger.info('='*60)

                # Step 1: Inflate to target (~190 mmHg)
                self.logger.info("\nStep 1: Auto-inflating to ~190 mmHg...")
                GPIO.output(valve_gpio, GPIO.HIGH)  # ĐÓNG van NO (HIGH = energize = close)
                GPIO.output(pump_gpio, GPIO.HIGH)   # Pump ON
                
                # Track max pressure during inflate
                current_slope = self.sensor.calibration.get('slope_mmhg_per_count', 3.5e-5)
                max_counts = 0
                max_pressure = 0
                
                while True:
                    raw = self.sensor.read_raw_data()
                    if raw is not None:
                        approx_pressure = (raw - offset) * current_slope
                        
                        if raw > max_counts:
                            max_counts = raw
                            max_pressure = approx_pressure
                        
                        print(f"   Inflating: {approx_pressure:.1f} mmHg (counts: {raw})", end='\r')

                        # Stop at ~190 mmHg
                        if approx_pressure >= 190:
                            break
                        
                        # Safety: hard limit 250 mmHg
                        if approx_pressure >= 250:
                            self.logger.error("⚠️  Emergency stop: pressure too high!")
                            break
                    
                    time.sleep(0.05)
                
                print()
                GPIO.output(pump_gpio, GPIO.LOW)  # Pump OFF
                
                # Step 2: Record max counts
                self.logger.info(f"\n✅ Max counts during inflate: {max_counts} (≈{max_pressure:.1f} mmHg)")
                
                # Step 3: Deflate
                self.logger.info("Step 2: Deflating...")
                GPIO.output(valve_gpio, GPIO.LOW)   # MỞ van NO (LOW = de-energize = open)
                time.sleep(15.0)  # Full deflate
                GPIO.output(valve_gpio, GPIO.HIGH)  # ĐÓNG lại van (sẵn sàng cho lần đo tiếp)
                
                # Step 4: User enters reference SYS
                self.logger.info("\n" + "─"*60)
                self.logger.info("📱 MEASURE WITH COMMERCIAL DEVICE")
                self.logger.info("─"*60)
                self.logger.info("   Wait 1-2 minutes, then measure BP with commercial device")
                
                sys_str = input("   Enter SYS from commercial device (mmHg): ").strip()
                
                if not sys_str:
                    self.logger.warning("⚠️  No input, skipping this measurement")
                    continue
                
                try:
                    sys_actual = float(sys_str)
                except ValueError:
                    self.logger.error("❌ Invalid number, skipping")
                    continue
                
                # Validate
                if sys_actual < 80 or sys_actual > 220:
                    self.logger.warning(f"⚠️  Unusual SYS: {sys_actual} mmHg (expected 80-220)")
                    confirm = input("   Continue anyway? (y/n): ").strip().lower()
                    if confirm != 'y':
                        continue
                
                # Store data
                self.logger.info(f"\n✅ Data point recorded:")
                self.logger.info(f"   IoT max counts: {max_counts}")
                self.logger.info(f"   Commercial SYS: {sys_actual:.1f} mmHg")
                
                pressure_ref.append(sys_actual)
                counts_data.append(max_counts - offset)  # Offset-corrected
                
                # Wait before next measurement
                if i < num_measurements - 1:
                    self.logger.info("\n⏱️  Wait 2 minutes before next measurement...")
                    time.sleep(5)  # Short delay (user can ctrl+c if needed)
            
        except KeyboardInterrupt:
            self.logger.warning("\n⚠️  Calibration interrupted by user")
            GPIO.output(pump_gpio, GPIO.LOW)    # Pump OFF
            GPIO.output(valve_gpio, GPIO.LOW)   # MỞ van khẩn cấp (xả hết khí)
            time.sleep(10.0)
            GPIO.output(valve_gpio, GPIO.HIGH)  # ĐÓNG lại sau khi xả
            
        finally:
            GPIO.output(pump_gpio, GPIO.LOW)    # Pump OFF
            GPIO.output(valve_gpio, GPIO.HIGH)  # ĐÓNG van (trạng thái an toàn)
        
        # Linear regression
        if len(pressure_ref) < 3:
            self.logger.error(f"\n❌ Need at least 3 valid points (have {len(pressure_ref)})")
            return None, None
        
        # Fit: pressure = slope × counts + intercept
        slope, intercept, r_value, p_value, std_err = stats.linregress(counts_data, pressure_ref)
        r_squared = r_value ** 2
        
        self.logger.info("\n" + "="*60)
        self.logger.info("✅ EMPIRICAL SPAN CALIBRATION COMPLETE")
        self.logger.info("="*60)
        self.logger.info(f"Data points collected: {len(pressure_ref)}")
        self.logger.info(f"slope_mmhg_per_count: {slope:.10e}")
        self.logger.info(f"Intercept: {intercept:.2f} mmHg (should be ~0)")
        self.logger.info(f"R²: {r_squared:.4f} (should be > 0.95)")
        self.logger.info(f"Std error: {std_err:.2e}")
        self.logger.info("="*60)
        
        # Validate
        if r_squared < 0.95:
            self.logger.warning("⚠️  Low R² - measurement variability high")
            self.logger.warning("   → Try more measurements or check technique")
        
        if abs(intercept) > 10.0:
            self.logger.warning(f"⚠️  High intercept ({intercept:.2f})")
            self.logger.warning("   → May need to re-run zero calibration")
        
        # Plot
        self._plot_calibration(counts_data, pressure_ref, slope, intercept)
        
        return slope, r_squared
    
    def _plot_calibration(
        self,
        counts: List[float],
        pressures: List[float],
        slope: float,
        intercept: float
    ):
        """Plot calibration curve"""
        plt.figure(figsize=(10, 6))
        plt.scatter(counts, pressures, s=100, alpha=0.6, label='Measured points')
        
        # Fit line
        x_fit = np.linspace(min(counts), max(counts), 100)
        y_fit = slope * x_fit + intercept
        plt.plot(x_fit, y_fit, 'r--', label=f'Fit: y = {slope:.2e}x + {intercept:.2f}')
        
        plt.xlabel('ADC Counts (offset-corrected)')
        plt.ylabel('Pressure (mmHg)')
        plt.title('HX710B ADC Calibration Curve')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Save
        output_dir = Path('/home/pi/Desktop/IoT_health/tests/calibration_results')
        output_dir.mkdir(exist_ok=True)
        plt.savefig(output_dir / 'adc_calibration.png', dpi=150)
        self.logger.info(f"📊 Plot saved to {output_dir / 'adc_calibration.png'}")
        
        plt.close()


# ==================== PHASE 2: ALGORITHM CALIBRATION ====================

class AlgorithmCalibrator:
    """
    Hiệu chỉnh thuật toán oscillometric: sys_frac + dia_frac
    
    Method:
    ------
    1. Đo BP nhiều lần với IoT device (MAP + SYS/DIA từ ratio hiện tại)
    2. Đo BP với máy thương mại (SYS/DIA reference)
    3. Optimize sys_frac, dia_frac để minimize error
    """
    
    def __init__(self, sensor: BloodPressureSensor):
        self.sensor = sensor
        self.logger = logging.getLogger("Algorithm_Calibrator")
        self.measurements: List[Dict] = []
    
    def collect_measurement(self) -> bool:
        """
        Thu thập 1 phép đo so sánh
        
        Workflow:
        1. Đo bằng IoT device
        2. Đo bằng máy thương mại
        3. Lưu data
        """
        self.logger.info("\n" + "="*60)
        self.logger.info("MEASUREMENT SESSION")
        self.logger.info("="*60)
        
        # IoT measurement
        self.logger.info("Step 1: Measuring with IoT device...")
        
        measurement_complete = False
        iot_measurement = None
        
        def on_complete(m: BloodPressureMeasurement):
            nonlocal measurement_complete, iot_measurement
            iot_measurement = m
            measurement_complete = True
        
        self.sensor.start_measurement(callback=on_complete)
        
        # Wait
        timeout = 120
        start_time = time.time()
        
        while not measurement_complete:
            if time.time() - start_time > timeout:
                self.logger.error("⏱️  Timeout")
                self.sensor.stop_measurement(emergency=True)
                return False
            time.sleep(0.5)
        
        if iot_measurement is None:
            self.logger.error("❌ IoT measurement failed")
            return False
        
        self.logger.info(
            f"IoT Result: SYS={iot_measurement.systolic:.1f} "
            f"DIA={iot_measurement.diastolic:.1f} MAP={iot_measurement.map_value:.1f}"
        )
        
        # Commercial measurement
        self.logger.info("\nStep 2: Measure with commercial device")
        sys_ref = float(input("   Enter SYS (mmHg): "))
        dia_ref = float(input("   Enter DIA (mmHg): "))
        
        # Store
        data = {
            'timestamp': iot_measurement.timestamp.isoformat(),
            'iot_sys': iot_measurement.systolic,
            'iot_dia': iot_measurement.diastolic,
            'iot_map': iot_measurement.map_value,
            'ref_sys': sys_ref,
            'ref_dia': dia_ref
        }
        
        self.measurements.append(data)
        
        self.logger.info(f"\n✅ Measurement recorded (total: {len(self.measurements)})")
        
        return True
    
    def calculate_optimal_ratios(self) -> Tuple[float, float]:
        """
        Tính sys_frac và dia_frac tối ưu
        
        Returns:
            (sys_frac_optimal, dia_frac_optimal)
        """
        if len(self.measurements) < 10:
            self.logger.warning(f"⚠️  Need ≥10 measurements (have {len(self.measurements)})")
            return None, None
        
        self.logger.info(f"\nCalculating optimal ratios from {len(self.measurements)} measurements...")
        
        # Extract data
        iot_sys = np.array([m['iot_sys'] for m in self.measurements])
        iot_dia = np.array([m['iot_dia'] for m in self.measurements])
        ref_sys = np.array([m['ref_sys'] for m in self.measurements])
        ref_dia = np.array([m['ref_dia'] for m in self.measurements])
        
        # Current errors
        error_sys = np.mean(np.abs(iot_sys - ref_sys))
        error_dia = np.mean(np.abs(iot_dia - ref_dia))
        
        self.logger.info(f"Current errors: SYS={error_sys:.1f} mmHg, DIA={error_dia:.1f} mmHg")
        
        # Calculate correction factors
        sys_correction = np.mean(ref_sys / iot_sys)
        dia_correction = np.mean(ref_dia / iot_dia)
        
        # Get current ratios
        current_sys_frac = self.sensor.processor.sys_frac
        current_dia_frac = self.sensor.processor.dia_frac
        
        # New ratios
        new_sys_frac = current_sys_frac * sys_correction
        new_dia_frac = current_dia_frac * dia_correction
        
        # Clamp
        new_sys_frac = np.clip(new_sys_frac, 0.4, 0.7)
        new_dia_frac = np.clip(new_dia_frac, 0.7, 0.9)
        
        self.logger.info("\n✅ Ratio calculation complete:")
        self.logger.info(f"   Current: sys_frac={current_sys_frac:.3f}, dia_frac={current_dia_frac:.3f}")
        self.logger.info(f"   New: sys_frac={new_sys_frac:.3f}, dia_frac={new_dia_frac:.3f}")
        
        # Plot Bland-Altman
        self._plot_bland_altman(iot_sys, ref_sys, iot_dia, ref_dia)
        
        return new_sys_frac, new_dia_frac
    
    def _plot_bland_altman(
        self,
        iot_sys: np.ndarray,
        ref_sys: np.ndarray,
        iot_dia: np.ndarray,
        ref_dia: np.ndarray
    ):
        """Plot Bland-Altman comparison"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # Systolic
        mean_sys = (iot_sys + ref_sys) / 2
        diff_sys = iot_sys - ref_sys
        ax1.scatter(mean_sys, diff_sys, alpha=0.6)
        ax1.axhline(np.mean(diff_sys), color='r', linestyle='--', label=f'Mean: {np.mean(diff_sys):.1f}')
        ax1.axhline(np.mean(diff_sys) + 1.96*np.std(diff_sys), color='gray', linestyle=':', label='+1.96 SD')
        ax1.axhline(np.mean(diff_sys) - 1.96*np.std(diff_sys), color='gray', linestyle=':', label='-1.96 SD')
        ax1.set_xlabel('Mean SYS (mmHg)')
        ax1.set_ylabel('Difference (IoT - Reference)')
        ax1.set_title('Bland-Altman: Systolic')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Diastolic
        mean_dia = (iot_dia + ref_dia) / 2
        diff_dia = iot_dia - ref_dia
        ax2.scatter(mean_dia, diff_dia, alpha=0.6, color='orange')
        ax2.axhline(np.mean(diff_dia), color='r', linestyle='--', label=f'Mean: {np.mean(diff_dia):.1f}')
        ax2.axhline(np.mean(diff_dia) + 1.96*np.std(diff_dia), color='gray', linestyle=':', label='+1.96 SD')
        ax2.axhline(np.mean(diff_dia) - 1.96*np.std(diff_dia), color='gray', linestyle=':', label='-1.96 SD')
        ax2.set_xlabel('Mean DIA (mmHg)')
        ax2.set_ylabel('Difference (IoT - Reference)')
        ax2.set_title('Bland-Altman: Diastolic')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # Save
        output_dir = Path('/home/pi/Desktop/IoT_health/tests/calibration_results')
        output_dir.mkdir(exist_ok=True)
        plt.savefig(output_dir / 'algorithm_calibration.png', dpi=150)
        self.logger.info(f"📊 Plot saved to {output_dir / 'algorithm_calibration.png'}")
        
        plt.close()
    
    def save_results(self, output_path: str = 'tests/calibration_results/measurements.yaml'):
        """Save data"""
        output_file = Path(output_path)
        output_file.parent.mkdir(exist_ok=True)
        
        with open(output_file, 'w') as f:
            yaml.dump({'measurements': self.measurements}, f, default_flow_style=False)
        
        self.logger.info(f"💾 Results saved to {output_file}")


# ==================== MAIN MENU ====================

def main():
    """Main calibration menu"""
    
    print("\n" + "="*60)
    print("BLOOD PRESSURE CALIBRATION TOOL")
    print("="*60)
    
    # Load config
    config_path = Path('/home/pi/Desktop/IoT_health/config/app_config.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    bp_config = config['sensors']['blood_pressure']
    
    while True:
        print("\n📋 MENU:")
        print("  1. Phase 1: ADC Calibration (offset + slope)")
        print("  2. Phase 2: Algorithm Calibration (sys_frac + dia_frac)")
        print("  3. Update config")
        print("  0. Exit")
        
        choice = input("\nSelect: ").strip()
        
        if choice == '1':
            # Phase 1
            from src.sensors.hx710b_sensor import create_hx710b_sensor_from_config
            
            sensor = create_hx710b_sensor_from_config(bp_config['hx710b'])
            if not sensor:
                logger.error("Failed to create HX710B sensor")
                continue
            
            sensor.start()
            calibrator = ADCCalibrator(sensor)
            
            # Zero
            print("\n--- Zero Calibration ---")
            offset = calibrator.calibrate_zero()
            
            if offset is None:
                sensor.stop()
                continue
            
            # Span
            print("\n--- Span Calibration (Empirical Method) ---")
            slope, r2 = calibrator.calibrate_span_empirical()
            
            if slope is None:
                sensor.stop()
                continue
            
            # Results
            print("\n" + "="*60)
            print("RESULTS:")
            print("="*60)
            print(f"offset_counts: {offset}")
            print(f"slope_mmhg_per_count: {slope:.10e}")
            print(f"R²: {r2:.4f}")
            print("="*60)
            
            sensor.stop()
        
        elif choice == '2':
            # Phase 2
            from src.sensors.blood_pressure_sensor import create_blood_pressure_sensor_from_config
            
            sensor = create_blood_pressure_sensor_from_config(bp_config)
            if not sensor:
                logger.error("Failed to create BP sensor")
                continue
            
            sensor.start()
            calibrator = AlgorithmCalibrator(sensor)
            
            # Collect
            print("\n--- Data Collection ---")
            print("Collect ≥10 measurements")
            
            while True:
                print(f"\nMeasurements: {len(calibrator.measurements)}")
                action = input("Press ENTER to measure (or 'q'): ").strip().lower()
                
                if action == 'q':
                    break
                
                calibrator.collect_measurement()
            
            # Calculate
            if len(calibrator.measurements) >= 10:
                sys_frac, dia_frac = calibrator.calculate_optimal_ratios()
                
                if sys_frac and dia_frac:
                    print("\n" + "="*60)
                    print("RESULTS:")
                    print("="*60)
                    print(f"sys_frac: {sys_frac:.4f}")
                    print(f"dia_frac: {dia_frac:.4f}")
                    print("="*60)
                    
                    calibrator.save_results()
            
            sensor.stop()
        
        elif choice == '3':
            # Update config
            print("\n--- Update Config ---")
            
            offset_str = input(f"offset_counts [{bp_config['hx710b']['calibration']['offset_counts']}]: ").strip()
            slope_str = input(f"slope_mmhg_per_count [{bp_config['hx710b']['calibration']['slope_mmhg_per_count']}]: ").strip()
            sys_frac_str = input(f"sys_frac [{bp_config['algorithm']['sys_frac']}]: ").strip()
            dia_frac_str = input(f"dia_frac [{bp_config['algorithm']['dia_frac']}]: ").strip()
            
            if offset_str:
                bp_config['hx710b']['calibration']['offset_counts'] = int(offset_str)
            if slope_str:
                bp_config['hx710b']['calibration']['slope_mmhg_per_count'] = float(slope_str)
            if sys_frac_str:
                bp_config['algorithm']['sys_frac'] = float(sys_frac_str)
            if dia_frac_str:
                bp_config['algorithm']['dia_frac'] = float(dia_frac_str)
            
            config['sensors']['blood_pressure'] = bp_config
            
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"✅ Config updated")
        
        elif choice == '0':
            print("\n👋 Goodbye!")
            break


if __name__ == "__main__":
    main()