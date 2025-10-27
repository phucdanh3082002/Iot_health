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
    
    def calibrate_span_with_commercial(
        self,
        pressure_targets: List[float] = [50, 100, 150, 200]
    ) -> Tuple[float, float]:
        """
        Span calibration sử dụng máy đo BP thương mại làm reference
        
        Prerequisites:
        -------------
        1. Đấu song song: IoT device + máy thương mại vào cùng cuff (qua T-tube)
        2. Máy thương mại có chế độ hiển thị áp real-time (manual mode)
        
        Workflow:
        --------
        1. IoT device bơm lên target pressure (auto control)
        2. Đợi áp ổn định
        3. User đọc áp từ màn hình máy thương mại
        4. IoT đọc ADC counts
        5. Linear regression → slope
        
        Args:
            pressure_targets: Danh sách áp mục tiêu (mmHg)
        
        Returns:
            (slope_mmhg_per_count, r_squared)
        """
        self.logger.info("Starting span calibration with commercial device...")
        self.logger.info("\n⚠️  SETUP REQUIRED:")
        self.logger.info("   1. Connect IoT device + commercial device to SAME cuff")
        self.logger.info("      (use T-tube or Y-connector)")
        self.logger.info("   2. Set commercial device to MANUAL mode")
        self.logger.info("      (allows reading pressure without auto-deflate)")
        self.logger.info("   3. Ensure no air leaks at connections")
        input("\n   Press ENTER when setup is complete...")
        
        # Get current offset
        offset = self.sensor.calibration.get('offset_counts', 0)
        self.logger.info(f"Using offset: {offset} counts")
        
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
        
        pressure_ref = []
        counts_data = []
        
        try:
            for target in pressure_targets:
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"TARGET PRESSURE: ~{target} mmHg")
                self.logger.info('='*60)
                
                # Step 1: Auto-inflate
                self.logger.info("Step 1: Auto-inflating cuff...")
                GPIO.output(valve_gpio, GPIO.LOW)   # Close valve
                GPIO.output(pump_gpio, GPIO.HIGH)   # Pump ON
                
                # Estimate current pressure
                current_slope = self.sensor.calibration.get('slope_mmhg_per_count', 1e-5)
                
                while True:
                    raw = self.sensor.read_raw_data()
                    if raw is not None:
                        approx_pressure = (raw - offset) * current_slope
                        print(f"   Inflating: {approx_pressure:.1f} mmHg", end='\r')
                        
                        if approx_pressure >= target - 5:
                            break
                    
                    time.sleep(0.05)
                
                print()
                GPIO.output(pump_gpio, GPIO.LOW)  # Pump OFF
                
                # Step 2: Wait stabilization
                self.logger.info("Step 2: Waiting for pressure stabilization...")
                time.sleep(2.0)
                
                # Step 3: User reads reference
                self.logger.info("\n" + "─"*60)
                self.logger.info("📱 READ PRESSURE FROM COMMERCIAL DEVICE")
                self.logger.info("─"*60)
                
                pressure_str = input("Enter displayed pressure (mmHg): ").strip()
                
                if not pressure_str:
                    self.logger.warning("⚠️  No input, skipping this point")
                    continue
                
                try:
                    pressure_actual = float(pressure_str)
                except ValueError:
                    self.logger.error("❌ Invalid number, skipping")
                    continue
                
                # Step 4: Read ADC counts
                self.logger.info("\nStep 3: Reading ADC counts...")
                samples = []
                
                for i in range(20):
                    raw = self.sensor.read_raw_data()
                    if raw is not None:
                        samples.append(raw)
                    time.sleep(0.05)
                
                if len(samples) < 15:
                    self.logger.warning("⚠️  Insufficient ADC samples, skipping")
                    continue
                
                avg_counts = np.median(samples)
                std_counts = np.std(samples)
                
                self.logger.info(f"\n✅ Data point recorded:")
                self.logger.info(f"   Reference pressure: {pressure_actual:.1f} mmHg")
                self.logger.info(f"   ADC counts: {avg_counts:.0f} ± {std_counts:.1f}")
                
                pressure_ref.append(pressure_actual)
                counts_data.append(avg_counts - offset)
                
                # Deflate partially (except last)
                if target != pressure_targets[-1]:
                    self.logger.info("\nDeflating partially...")
                    GPIO.output(valve_gpio, GPIO.HIGH)
                    time.sleep(3.0)
                    GPIO.output(valve_gpio, GPIO.LOW)
            
            # Full deflate
            self.logger.info("\nDeflating completely...")
            GPIO.output(valve_gpio, GPIO.HIGH)
            time.sleep(5.0)
            GPIO.output(valve_gpio, GPIO.LOW)
            
        except KeyboardInterrupt:
            self.logger.warning("\n⚠️  Calibration interrupted")
            GPIO.output(pump_gpio, GPIO.LOW)
            GPIO.output(valve_gpio, GPIO.HIGH)
            time.sleep(5.0)
            return None, None
            
        finally:
            GPIO.output(pump_gpio, GPIO.LOW)
            GPIO.output(valve_gpio, GPIO.LOW)
        
        # Linear regression
        if len(pressure_ref) < 3:
            self.logger.error("\n❌ Need at least 3 valid points")
            return None, None
        
        slope, intercept, r_value, p_value, std_err = stats.linregress(counts_data, pressure_ref)
        r_squared = r_value ** 2
        
        self.logger.info("\n" + "="*60)
        self.logger.info("✅ SPAN CALIBRATION COMPLETE")
        self.logger.info("="*60)
        self.logger.info(f"slope_mmhg_per_count: {slope:.10e}")
        self.logger.info(f"Intercept: {intercept:.2f} mmHg (should be ~0)")
        self.logger.info(f"R²: {r_squared:.4f} (should be > 0.98)")
        self.logger.info("="*60)
        
        # Validate
        if r_squared < 0.98:
            self.logger.warning("⚠️  Low R² - check for air leaks or unstable readings")
        
        if abs(intercept) > 5.0:
            self.logger.warning(f"⚠️  High intercept ({intercept:.2f}) - re-run zero calibration")
        
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
            print("\n--- Span Calibration ---")
            slope, r2 = calibrator.calibrate_span_with_commercial()
            
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