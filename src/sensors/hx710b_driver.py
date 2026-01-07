#!/usr/bin/env python3
"""
HX710B 24-bit ADC Driver
========================

Driver for HX710(A/B) precision 24-bit ADC based on official datasheet.

Hardware Specifications (from Avia Semiconductor datasheet):
-----------------------------------------------------------
- Resolution: 24-bit signed (0x800000 to 0x7FFFFF)
- Gain: 128 (fixed)
- Full-scale input: ±0.0039 × VREF (±20mV @ 5V, ±13.2mV @ 3.3V)
- Output data rate: 10 SPS (25 pulses) or 40 SPS (27 pulses)
- Settling time: 400ms (10 SPS), 100ms (40 SPS)
- Power-down: SCK HIGH > 60μs

Serial Protocol (from datasheet):
---------------------------------
1. Wait for DOUT = LOW (data ready)
2. Apply 25-27 positive clock pulses on SCK
3. Each pulse shifts out one bit on DOUT (MSB first)
4. 25th pulse pulls DOUT back HIGH
5. Number of pulses selects mode:
   - 25 pulses: Differential input @ 10 Hz
   - 26 pulses: Temperature (HX710A) / DVDD-AVDD (HX710B) @ 40 Hz
   - 27 pulses: Differential input @ 40 Hz

Timing Requirements (from datasheet Table T1-T4):
------------------------------------------------
- T1: DOUT falling → SCK rising: ≥ 0.1 μs
- T2: SCK rising → DOUT valid: ≤ 0.1 μs
- T3: SCK high time: 0.2 μs (min), 1 μs (typ), 50 μs (max)
- T4: SCK low time: 0.2 μs (min), 1 μs (typ)

Author: IoT Health Monitor Team
Date: 2025-10-24
Version: 3.0.0 (Rewritten based on official datasheet)
"""

from typing import Optional, Callable
from enum import Enum
import logging
import time
import threading

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


class HX710Mode(Enum):
    """HX710B operating modes (based on number of SCK pulses)"""
    DIFFERENTIAL_10SPS = 25   # Differential input @ 10 Hz
    TEMP_OR_DIFF_40SPS = 26   # Temperature (HX710A) or DVDD-AVDD (HX710B) @ 40 Hz
    DIFFERENTIAL_40SPS = 27   # Differential input @ 40 Hz


class HX710BDriver:
    """
    HX710B 24-bit ADC Driver (Datasheet-accurate implementation)
    
    Thread-safe driver implementing exact timing and protocol from official datasheet.
    
    Features:
    ---------
    - Configurable data rate (10 SPS or 40 SPS)
    - Proper power-up sequence with settling time
    - Automatic power-down prevention
    - Thread-safe operations
    - Saturation detection
    
    Usage Example:
    -------------
    >>> driver = HX710BDriver(gpio_dout=6, gpio_sck=5, mode=HX710Mode.DIFFERENTIAL_10SPS)
    >>> driver.initialize()
    >>> 
    >>> # Read raw counts
    >>> counts = driver.read()
    >>> 
    >>> # Or use callback
    >>> def on_data(counts, timestamp):
    >>>     print(f"ADC: {counts} @ {timestamp:.3f}s")
    >>> 
    >>> driver.set_callback(on_data)
    >>> driver.start_continuous()  # Auto-read in background
    """
    
    # Timing constants (from datasheet)
    T_SCK_HIGH_US = 1.0      # SCK high time (typ 1μs, min 0.2μs, max 50μs)
    T_SCK_LOW_US = 1.0       # SCK low time (typ 1μs, min 0.2μs)
    T_POWERDOWN_US = 60      # Power-down threshold (>60μs)
    
    # Settling times (from datasheet)
    SETTLING_TIME_10SPS = 0.4  # 400ms for 10 SPS
    SETTLING_TIME_40SPS = 0.1  # 100ms for 40 SPS
    
    # ADC constants
    ADC_MIN = -0x800000  # -8388608 (24-bit signed min)
    ADC_MAX = 0x7FFFFF   # 8388607 (24-bit signed max)
    
    def __init__(
        self,
        gpio_dout: int,
        gpio_sck: int,
        mode: HX710Mode = HX710Mode.DIFFERENTIAL_10SPS,
        timeout_ms: int = 500
    ):
        """
        Initialize HX710B driver
        
        Args:
            gpio_dout: GPIO pin for DOUT (data output, input to MCU)
            gpio_sck: GPIO pin for SCK (serial clock, output from MCU)
            mode: Operating mode (10 SPS or 40 SPS)
            timeout_ms: Timeout for waiting data ready (ms)
        """
        self.gpio_dout = gpio_dout
        self.gpio_sck = gpio_sck
        self.mode = mode
        self.timeout_ms = timeout_ms
        
        self.logger = logging.getLogger(f"HX710B[DOUT={gpio_dout},SCK={gpio_sck}]")
        
        # State
        self._lock = threading.Lock()
        self._is_initialized = False
        self._callback: Optional[Callable] = None
        self._continuous_thread: Optional[threading.Thread] = None
        self._stop_continuous = threading.Event()
        
        # Statistics
        self._read_count = 0
        self._error_count = 0
        self._last_value: Optional[int] = None
        
    def initialize(self) -> bool:
        """
        Initialize HX710B (power-up sequence from datasheet)
        
        Sequence:
        1. Setup GPIO pins (SCK = LOW to avoid power-down)
        2. Wait for settling time (400ms for 10 SPS, 100ms for 40 SPS)
        3. Perform wake-up reads to trigger conversion cycle
        4. Verify ADC is responding
        
        Returns:
            bool: True if successful
        """
        if not GPIO:
            self.logger.error("RPi.GPIO not available")
            return False
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup pins (CRITICAL: SCK must be LOW initially)
            GPIO.setup(self.gpio_sck, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.gpio_dout, GPIO.IN)
            
            self.logger.info(f"GPIO initialized (DOUT=GPIO{self.gpio_dout}, SCK=GPIO{self.gpio_sck})")
            
            # Wait for power-up settling (from datasheet)
            settling_time = (
                self.SETTLING_TIME_10SPS if self.mode == HX710Mode.DIFFERENTIAL_10SPS
                else self.SETTLING_TIME_40SPS
            )
            
            self.logger.info(f"Waiting for settling time ({settling_time*1000:.0f}ms for {self.mode.name})...")
            time.sleep(settling_time)
            
            self._is_initialized = True
            
            # Perform wake-up sequence (multiple reads to ensure conversion cycle starts)
            self.logger.info("Performing wake-up sequence...")
            wake_success = 0
            
            for attempt in range(3):
                value = self.read()
                
                if value is not None:
                    # Check if valid (not saturation)
                    if self.ADC_MIN < value < self.ADC_MAX:
                        wake_success += 1
                        self.logger.debug(f"Wake-up {attempt+1}/3: Valid ({value})")
                    else:
                        self.logger.debug(f"Wake-up {attempt+1}/3: Saturation ({value})")
                else:
                    self.logger.debug(f"Wake-up {attempt+1}/3: Timeout")
                
                time.sleep(0.15)  # Wait between attempts
            
            if wake_success > 0:
                self.logger.info(f"HX710B initialized successfully ({wake_success}/3 valid reads)")
                return True
            else:
                self.logger.warning("Wake-up sequence had no valid reads (continuing anyway)")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to initialize: {e}")
            return False
    
    def read(self, timeout_ms: Optional[int] = None) -> Optional[int]:
        """
        Read 24-bit value from HX710B (blocking, thread-safe)
        
        Protocol (from datasheet):
        1. Wait for DOUT = LOW (data ready)
        2. Clock out 24 bits (MSB first)
        3. Send additional pulses for mode selection (25/26/27 total)
        4. Convert to signed 24-bit integer
        
        Args:
            timeout_ms: Override default timeout (ms)
        
        Returns:
            int: Signed 24-bit value (-8388608 to 8388607)
            None: On timeout or error
        """
        if not self._is_initialized:
            self.logger.error("Driver not initialized")
            return None
        
        timeout = timeout_ms if timeout_ms is not None else self.timeout_ms
        
        with self._lock:
            try:
                # Step 1: Wait for DOUT = LOW (data ready)
                start_time = time.time()
                timeout_s = timeout / 1000.0
                
                while GPIO.input(self.gpio_dout) == GPIO.HIGH:
                    if time.time() - start_time > timeout_s:
                        self._error_count += 1
                        self.logger.debug(f"Timeout waiting for data ready ({timeout}ms)")
                        return None
                    time.sleep(0.001)  # 1ms poll interval (like test.py)
                
                # Step 2: Clock out 24 bits (MSB first)
                value = 0
                
                for _ in range(24):
                    # Generate clock pulse (datasheet Table T1-T4)
                    # T3: SCK HIGH time (typ 1μs, min 0.2μs)
                    # T4: SCK LOW time (typ 1μs, min 0.2μs)
                    # NOTE: GPIO.output() on RPi has ~0.1-0.5μs natural delay, 
                    #       sufficient to meet timing requirements. 
                    #       time.sleep() has 10ms overhead in Python - TOO SLOW!
                    GPIO.output(self.gpio_sck, GPIO.HIGH)
                    GPIO.output(self.gpio_sck, GPIO.LOW)
                    
                    # T2: DOUT valid after SCK rising (≤ 0.1μs)
                    # Read DOUT AFTER LOW transition (data stable)
                    bit = GPIO.input(self.gpio_dout)
                    value = (value << 1) | bit
                
                # Step 3: Additional pulses for mode selection
                pulses_needed = self.mode.value  # 25, 26, or 27
                additional_pulses = pulses_needed - 24
                
                for _ in range(additional_pulses):
                    GPIO.output(self.gpio_sck, GPIO.HIGH)
                    GPIO.output(self.gpio_sck, GPIO.LOW)
                
                # Step 4: Convert to signed 24-bit (2's complement)
                if value & 0x800000:  # MSB = 1 (negative)
                    value -= 0x1000000
                
                # Update statistics
                self._read_count += 1
                self._last_value = value
                
                return value
                
            except Exception as e:
                self._error_count += 1
                self.logger.error(f"Read error: {e}")
                return None
    
    def is_saturated(self, value: int) -> bool:
        """
        Check if ADC value is saturated (from datasheet: 0x800000 or 0x7FFFFF)
        
        Args:
            value: ADC value to check
        
        Returns:
            bool: True if saturated
        """
        return value == self.ADC_MIN or value == self.ADC_MAX
    
    def power_down(self):
        """
        Enter power-down mode (SCK = HIGH > 60μs, from datasheet)
        
        In power-down:
        - Analog current: 0.3 μA (typ)
        - Digital current: 0.2 μA (typ)
        """
        if GPIO and self._is_initialized:
            GPIO.output(self.gpio_sck, GPIO.HIGH)
            time.sleep(self.T_POWERDOWN_US / 1_000_000 * 2)  # 2× safety margin
            self.logger.info("Entered power-down mode")
    
    def power_up(self):
        """
        Exit power-down mode (SCK = LOW, from datasheet)
        
        Note: Settings from before power-down are restored.
        """
        if GPIO and self._is_initialized:
            GPIO.output(self.gpio_sck, GPIO.LOW)
            
            # Wait for settling time
            settling_time = (
                self.SETTLING_TIME_10SPS if self.mode == HX710Mode.DIFFERENTIAL_10SPS
                else self.SETTLING_TIME_40SPS
            )
            time.sleep(settling_time)
            
            self.logger.info("Exited power-down mode")
    
    def set_callback(self, callback: Callable[[int, float], None]):
        """
        Set callback for continuous reading mode
        
        Args:
            callback: Function(value: int, timestamp: float)
        """
        self._callback = callback
    
    def start_continuous(self):
        """
        Start continuous reading in background thread
        
        Reads at maximum rate supported by mode (10 or 40 SPS).
        Callback is called for each successful read.
        """
        if self._continuous_thread and self._continuous_thread.is_alive():
            self.logger.warning("Continuous mode already running")
            return
        
        self._stop_continuous.clear()
        self._continuous_thread = threading.Thread(
            target=self._continuous_read_loop,
            daemon=True,
            name="HX710B_Continuous"
        )
        self._continuous_thread.start()
        self.logger.info("Started continuous reading mode")
    
    def stop_continuous(self):
        """Stop continuous reading"""
        if self._continuous_thread and self._continuous_thread.is_alive():
            self._stop_continuous.set()
            self._continuous_thread.join(timeout=2.0)
            self.logger.info("Stopped continuous reading mode")
    
    def _continuous_read_loop(self):
        """Background thread for continuous reading"""
        while not self._stop_continuous.is_set():
            timestamp = time.time()
            value = self.read()
            
            if value is not None and self._callback:
                try:
                    self._callback(value, timestamp)
                except Exception as e:
                    self.logger.error(f"Callback error: {e}")
            
            # NO SLEEP - Let ADC data-ready signal control timing (like test.py)
            # HX710B runs at 10/40 SPS naturally
    
    def get_stats(self) -> dict:
        """
        Get driver statistics
        
        Returns:
            dict: Statistics (read_count, error_count, error_rate, last_value)
        """
        total = self._read_count + self._error_count
        error_rate = self._error_count / total if total > 0 else 0.0
        
        return {
            'read_count': self._read_count,
            'error_count': self._error_count,
            'error_rate': error_rate,
            'last_value': self._last_value,
            'mode': self.mode.name
        }
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        self.stop_continuous()
        
        if self._is_initialized and GPIO:
            try:
                GPIO.output(self.gpio_sck, GPIO.LOW)
                # Don't call GPIO.cleanup() - other sensors may use GPIO
                self._is_initialized = False
                self.logger.info("Driver cleaned up")
            except Exception as e:
                self.logger.error(f"Cleanup error: {e}")
    
    def __del__(self):
        """Destructor"""
        self.cleanup()
