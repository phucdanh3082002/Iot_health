#!/usr/bin/env python3
"""
Envelope Analysis Tool
======================

Phân tích chi tiết envelope extraction và ratio method.

Mục đích:
- Kiểm tra chất lượng envelope
- Visualize crossing points
- Recommend optimal ratios

Author: IoT Health Monitor Team
Date: 2026-01-05
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt, hilbert, detrend, savgol_filter
import sys
import json
from pathlib import Path
sys.path.append('/home/pi/Desktop/IoT_health')

def analyze_deflate_data(pressures, timestamps):
    """
    Analyze deflate data and visualize envelope
    
    Args:
        pressures: List of pressure readings (mmHg)
        timestamps: List of timestamps (seconds)
    """
    
    pressures_arr = np.array(pressures)
    timestamps_arr = np.array(timestamps)
    
    # Calculate sample rate
    duration = timestamps_arr[-1] - timestamps_arr[0]
    sample_rate = len(timestamps) / duration
    print(f"Sample rate: {sample_rate:.1f} SPS")
    print(f"Duration: {duration:.1f} s")
    print(f"Samples: {len(pressures)}")
    
    # Step 1: Detrend
    pressure_detrended = detrend(pressures_arr, type='linear')
    
    # Step 2: Bandpass filter
    nyquist = sample_rate / 2.0
    low = 0.5 / nyquist
    high = 5.0 / nyquist
    low = max(0.01, min(low, 0.95))
    high = max(low + 0.05, min(high, 0.95))
    
    b, a = butter(4, [low, high], btype='band')
    oscillations = filtfilt(b, a, pressure_detrended)
    
    # Step 3: Envelope
    analytic_signal = hilbert(oscillations)
    envelope = np.abs(analytic_signal)
    
    window_size = max(3, int(sample_rate / 5))
    if window_size % 2 == 0:
        window_size += 1
    envelope_smooth = savgol_filter(envelope, window_size, 2)
    
    # Step 4: MAP detection
    map_idx = np.argmax(envelope_smooth)
    map_pressure = pressures_arr[map_idx]
    map_amplitude = envelope_smooth[map_idx]
    
    print(f"\nMAP detected: {map_pressure:.1f} mmHg @ idx {map_idx}/{len(pressures)}")
    print(f"MAP amplitude: {map_amplitude:.3f} mmHg")
    print(f"MAP position: {map_idx/len(pressures)*100:.1f}% of deflate cycle")
    
    # Step 5: Test different ratios
    print("\n" + "="*60)
    print("TESTING DIFFERENT RATIOS:")
    print("="*60)
    
    test_ratios = [
        (0.50, 0.85, "Conservative (50%/85%)"),
        (0.55, 0.80, "Standard (55%/80%)"),
        (0.60, 0.75, "Aggressive (60%/75%)")
    ]
    
    for sys_ratio, dia_ratio, name in test_ratios:
        sys_threshold = map_amplitude * sys_ratio
        dia_threshold = map_amplitude * dia_ratio
        
        # Find crossings
        sys_idx = None
        for i in range(1, map_idx):
            if envelope_smooth[i-1] < sys_threshold <= envelope_smooth[i]:
                sys_idx = i
                break
        
        dia_idx = None
        for i in range(map_idx + 1, len(envelope_smooth)):
            if envelope_smooth[i-1] > dia_threshold >= envelope_smooth[i]:
                dia_idx = i
                break
        
        if sys_idx and dia_idx:
            sys_pressure = pressures_arr[sys_idx]
            dia_pressure = pressures_arr[dia_idx]
            pulse_pressure = sys_pressure - dia_pressure
            
            print(f"\n{name}:")
            print(f"  SYS: {sys_pressure:.1f} mmHg @ idx {sys_idx}")
            print(f"  DIA: {dia_pressure:.1f} mmHg @ idx {dia_idx}")
            print(f"  Pulse Pressure: {pulse_pressure:.1f} mmHg")
            
            if pulse_pressure < 20:
                print(f"  ⚠️  WARNING: Pulse pressure < 20 mmHg")
            elif pulse_pressure > 80:
                print(f"  ⚠️  WARNING: Pulse pressure > 80 mmHg")
            else:
                print(f"  ✅ Pulse pressure in range (20-80 mmHg)")
        else:
            print(f"\n{name}: ❌ No crossing found")
    
    # Visualization
    fig, axes = plt.subplots(4, 1, figsize=(14, 10))
    
    # Plot 1: Raw pressure
    axes[0].plot(timestamps_arr, pressures_arr, 'b-', linewidth=1)
    axes[0].axvline(timestamps_arr[map_idx], color='r', linestyle='--', label='MAP')
    axes[0].set_ylabel('Pressure (mmHg)')
    axes[0].set_title('Raw Pressure During Deflate')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Plot 2: Detrended + Oscillations
    axes[1].plot(timestamps_arr, pressure_detrended, 'g-', linewidth=0.5, label='Detrended', alpha=0.5)
    axes[1].plot(timestamps_arr, oscillations, 'b-', linewidth=1, label='Filtered')
    axes[1].axvline(timestamps_arr[map_idx], color='r', linestyle='--', label='MAP')
    axes[1].set_ylabel('Amplitude (mmHg)')
    axes[1].set_title('Oscillations (After Bandpass Filter)')
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    
    # Plot 3: Envelope
    axes[2].plot(timestamps_arr, envelope_smooth, 'r-', linewidth=2, label='Envelope')
    axes[2].axhline(map_amplitude, color='orange', linestyle=':', label=f'MAP amplitude ({map_amplitude:.3f})')
    axes[2].axhline(map_amplitude * 0.55, color='green', linestyle='--', label='SYS threshold (55%)', alpha=0.7)
    axes[2].axhline(map_amplitude * 0.80, color='blue', linestyle='--', label='DIA threshold (80%)', alpha=0.7)
    axes[2].axvline(timestamps_arr[map_idx], color='r', linestyle='--', label='MAP position')
    axes[2].set_ylabel('Envelope (mmHg)')
    axes[2].set_title('Envelope Extraction (Hilbert Transform)')
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)
    
    # Plot 4: Pressure vs Envelope
    axes[3].plot(pressures_arr, envelope_smooth, 'purple', linewidth=1.5)
    axes[3].scatter([map_pressure], [map_amplitude], color='red', s=100, zorder=5, label='MAP')
    axes[3].axhline(map_amplitude * 0.55, color='green', linestyle='--', alpha=0.5)
    axes[3].axhline(map_amplitude * 0.80, color='blue', linestyle='--', alpha=0.5)
    axes[3].set_xlabel('Pressure (mmHg)')
    axes[3].set_ylabel('Envelope (mmHg)')
    axes[3].set_title('Envelope vs Pressure (Oscillometric Curve)')
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)
    axes[3].invert_xaxis()  # High pressure on left
    
    plt.tight_layout()
    plt.savefig('/home/pi/Desktop/IoT_health/envelope_analysis.png', dpi=150)
    print(f"\n✅ Plot saved to: /home/pi/Desktop/IoT_health/envelope_analysis.png")
    plt.show()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Load from saved data
        timestamp = sys.argv[1]
        data_dir = Path('/home/pi/Desktop/IoT_health/bp_data')
        
        pressures_file = data_dir / f'pressures_{timestamp}.npy'
        timestamps_file = data_dir / f'timestamps_{timestamp}.npy'
        metadata_file = data_dir / f'metadata_{timestamp}.json'
        
        if not pressures_file.exists():
            print(f"❌ Data file not found: {pressures_file}")
            sys.exit(1)
        
        print("Loading data...")
        pressures = np.load(pressures_file)
        timestamps = np.load(timestamps_file)
        
        with open(metadata_file) as f:
            metadata = json.load(f)
        
        print(f"✅ Loaded {len(pressures)} samples")
        print(f"Metadata: {metadata['result']}")
        print()
        
        analyze_deflate_data(pressures.tolist(), timestamps.tolist())
        
    else:
        print("Envelope Analysis Tool")
        print("="*60)
        print("\nUsage:")
        print("  python analyze_envelope.py <timestamp>")
        print("\nExample:")
        print("  python analyze_envelope.py 20260105_110230")
        print("\nOr run capture_bp_data.py first to collect data")
        print("  python tests/capture_bp_data.py")
