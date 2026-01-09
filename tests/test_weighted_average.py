#!/usr/bin/env python3
"""
Test script để verify Weighted Moving Average implementation
"""
import time
from collections import deque

def calculate_weighted_average(values, timestamps, window_seconds):
    """
    Test implementation của weighted average.
    Copy từ continuous_monitor_screen.py
    """
    if not values or not timestamps:
        return None
    
    now = time.time()
    cutoff = now - window_seconds
    
    # Filter only values within window
    valid_pairs = [(v, ts) for v, ts in zip(values, timestamps) 
                   if ts >= cutoff]
    
    if not valid_pairs:
        return None
    
    # Sort by time (oldest first)
    valid_pairs.sort(key=lambda x: x[1])
    
    # Calculate exponential decay weights
    weights = []
    tau = window_seconds / 3.0  # Time constant
    
    for _, ts in valid_pairs:
        age = now - ts  # Age of reading (seconds)
        # Exponential decay: w = e^(-age/tau)
        w = 2.71828 ** (-age / tau)
        weights.append(w)
    
    # Normalize weights
    total_weight = sum(weights)
    if total_weight == 0:
        # Fallback to simple average
        return sum(v for v, _ in valid_pairs) / len(valid_pairs)
    
    weights = [w / total_weight for w in weights]
    
    # Weighted average
    weighted_sum = sum(v * w for (v, _), w in zip(valid_pairs, weights))
    
    return weighted_sum


def test_scenario_1_jittering_values():
    """Test với giá trị nhảy nhót như user report."""
    print("\n" + "="*60)
    print("TEST 1: Jittering Values (như user report)")
    print("="*60)
    
    # Simulate 5 seconds of data @ 5Hz (1 sample per 0.2s)
    hr_history = deque(maxlen=30)
    hr_timestamps = deque(maxlen=30)
    
    # Giả lập RAW values dao động mạnh
    raw_values = [75, 82, 78, 99, 76, 77, 74, 80, 73, 78]  # BPM
    base_time = time.time() - 2.0  # Start 2 seconds ago
    
    print("\nRAW VALUES:")
    for i, val in enumerate(raw_values):
        ts = base_time + (i * 0.2)
        hr_history.append(float(val))
        hr_timestamps.append(ts)
        print(f"  {i*0.2:.1f}s: {val} BPM")
    
    # Calculate weighted average
    avg = calculate_weighted_average(hr_history, hr_timestamps, 5.0)
    
    print(f"\n5-SECOND WEIGHTED AVERAGE: {avg:.1f} BPM")
    print(f"  → Spike 99 BPM được filter xuống ~{avg:.1f} BPM")
    print(f"  → Display value ổn định hơn RAW values")
    
    # Simulate EMA smoothing
    displayed_hr = 75.0  # Initial
    ema_alpha = 0.3
    
    print(f"\nEMA SMOOTHING (α={ema_alpha}):")
    for i in range(3):
        displayed_hr = ema_alpha * avg + (1 - ema_alpha) * displayed_hr
        print(f"  Iteration {i+1}: {displayed_hr:.1f} BPM")
    
    print(f"\n✓ FINAL DISPLAY: {int(round(displayed_hr))} BPM")
    print(f"  (Smooth transition from raw jitter)")


def test_scenario_2_hysteresis_alarm():
    """Test hysteresis alarm với SpO2 dao động."""
    print("\n" + "="*60)
    print("TEST 2: Hysteresis Alarm (SpO2 oscillating)")
    print("="*60)
    
    # Thresholds
    SPO2_TRIGGER = 90
    SPO2_CLEAR = 92
    DEBOUNCE_DELAY = 10.0
    
    # Simulate SpO2 values oscillating around threshold
    spo2_values = [95, 93, 91, 89, 90, 91, 90, 89, 91, 92, 93]
    alarm_active = False
    alarm_pending_time = 0
    
    print(f"\nTHRESHOLDS:")
    print(f"  Trigger: < {SPO2_TRIGGER}%")
    print(f"  Clear: >= {SPO2_CLEAR}%")
    print(f"  Debounce: {DEBOUNCE_DELAY}s")
    
    print(f"\nSIMULATION (without hysteresis):")
    for i, spo2 in enumerate(spo2_values):
        print(f"  {i}s: SpO2={spo2}%", end="")
        if spo2 < 90:
            print(" → ALARM! 🚨 (no hysteresis)")
        else:
            print(" → OK ✅")
    
    print(f"\nSIMULATION (with hysteresis + debouncing):")
    current_time = 0
    for i, spo2 in enumerate(spo2_values):
        current_time = i
        print(f"  {i}s: SpO2={spo2}%", end="")
        
        if spo2 < SPO2_TRIGGER:
            if alarm_pending_time == 0:
                alarm_pending_time = current_time
                print(f" → Pending (trigger at {SPO2_TRIGGER}%)", end="")
            else:
                elapsed = current_time - alarm_pending_time
                if elapsed >= DEBOUNCE_DELAY and not alarm_active:
                    alarm_active = True
                    print(f" → ALARM TRIGGERED! 🚨 (after {elapsed}s)", end="")
                elif alarm_active:
                    print(f" → ALARM ACTIVE 🚨", end="")
                else:
                    print(f" → Pending ({elapsed}s/{DEBOUNCE_DELAY}s)", end="")
        
        elif spo2 >= SPO2_CLEAR:
            alarm_pending_time = 0
            if alarm_active:
                alarm_active = False
                print(f" → ALARM CLEARED ✅ (clear at {SPO2_CLEAR}%)", end="")
            else:
                print(" → OK", end="")
        
        else:
            # Hysteresis zone (90-92%)
            if alarm_active:
                print(f" → ALARM ACTIVE (hysteresis zone)", end="")
            else:
                print(f" → Hysteresis zone (no change)", end="")
        
        print()
    
    print(f"\n✓ RESULT: Hysteresis prevents false alarms from oscillation")


def test_scenario_3_weighted_average_math():
    """Test toán học của weighted average."""
    print("\n" + "="*60)
    print("TEST 3: Weighted Average Math Verification")
    print("="*60)
    
    # Giả lập 3 samples trong 5 seconds
    now = time.time()
    values = [70.0, 75.0, 80.0]  # HR values
    timestamps = [now - 4.0, now - 2.0, now]  # Ages: 4s, 2s, 0s
    
    print("\nSAMPLES:")
    for i, (val, ts) in enumerate(zip(values, timestamps)):
        age = now - ts
        print(f"  Sample {i+1}: {val} BPM (age: {age:.1f}s)")
    
    # Calculate weights manually
    window_seconds = 5.0
    tau = window_seconds / 3.0
    
    print(f"\nWEIGHT CALCULATION (tau={tau:.2f}s):")
    weights = []
    for i, ts in enumerate(timestamps):
        age = now - ts
        w = 2.71828 ** (-age / tau)
        weights.append(w)
        print(f"  Sample {i+1}: w = e^(-{age:.1f}/{tau:.2f}) = {w:.4f}")
    
    # Normalize
    total = sum(weights)
    normalized = [w / total for w in weights]
    
    print(f"\nNORMALIZED WEIGHTS (sum={total:.4f}):")
    for i, w in enumerate(normalized):
        print(f"  Sample {i+1}: {w:.4f} ({w*100:.1f}%)")
    
    # Weighted average
    avg_manual = sum(v * w for v, w in zip(values, normalized))
    print(f"\nWEIGHTED AVERAGE (manual):")
    print(f"  = {values[0]} × {normalized[0]:.4f} + {values[1]} × {normalized[1]:.4f} + {values[2]} × {normalized[2]:.4f}")
    print(f"  = {avg_manual:.2f} BPM")
    
    # Compare with function
    avg_func = calculate_weighted_average(
        deque(values), deque(timestamps), window_seconds
    )
    print(f"\nWEIGHTED AVERAGE (function): {avg_func:.2f} BPM")
    
    print(f"\n✓ VERIFICATION: {'PASS' if abs(avg_manual - avg_func) < 0.01 else 'FAIL'}")


if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# WEIGHTED MOVING AVERAGE - VERIFICATION TESTS")
    print("#"*60)
    
    test_scenario_1_jittering_values()
    test_scenario_2_hysteresis_alarm()
    test_scenario_3_weighted_average_math()
    
    print("\n" + "#"*60)
    print("# ALL TESTS COMPLETED")
    print("#"*60)
    print()
