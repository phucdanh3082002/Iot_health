#!/usr/bin/env python3
"""
HX710B Sensor - BaseSensor Adapter
===================================

Adapter layer connecting HX710BDriver (low-level) with BaseSensor (high-level).

Architecture Layers:
-------------------
1. HX710BDriver (hx710b_driver.py): GPIO bit-banging, datasheet timing
2. HX710BSensor (THIS FILE): BaseSensor interface, calibration, validation
3. BloodPressureSensor: Oscillometric algorithm, BP measurement logic

Design Principles:
-----------------
- Composition over inheritance: Uses HX710BDriver internally
- Blocking mode: ADC waits for data-ready signal (DOUT=LOW)
- Type safety: read_raw_data() returns int (not Dict)
- Calibration: Converts raw counts → mmHg using config params
- Validation: Checks saturation before processing

Configuration Example (from app_config.yaml):
--------------------------------------------
sensors:
  hx710b:
    enabled: true
    gpio_dout: 6              # BCM GPIO6 (DOUT pin)
    gpio_sck: 5               # BCM GPIO5 (SCK pin)
    mode: '10sps'             # '10sps' or '40sps'
    read_timeout_ms: 1000     # Timeout for ADC read
    calibration:
      offset_counts: 0                      # Zero offset (from calibration tool)
      slope_mmhg_per_count: 9.536743e-06    # Conversion factor (from datasheet)
      adc_inverted: false                   # Invert sign if needed

Usage Example:
-------------
>>> from src.sensors.hx710b_sensor import HX710BSensor
>>> 
>>> config = {
>>>     'gpio_dout': 6,
>>>     'gpio_sck': 5,
>>>     'mode': '10sps',
>>>     'calibration': {
>>>         'offset_counts': 12500,
>>>         'slope_mmhg_per_count': 9.536743e-06
>>>     }
>>> }
>>> 
>>> # Create and start sensor
>>> sensor = HX710BSensor("BP_ADC", config)
>>> sensor.start()
>>> 
>>> # Get calibrated data
>>> data = sensor.get_latest_data()
>>> print(f"Pressure: {data['pressure_mmhg']:.1f} mmHg")
>>> 
>>> # Get raw value for debugging
>>> raw_counts = sensor.get_raw_value()
>>> print(f"Raw ADC: {raw_counts}")
>>> 
>>> sensor.stop()

Author: IoT Health Monitor Team
Date: 2025-10-24
Version: 1.0.0
"""

from typing import Optional, Dict, Any
import logging

from .base_sensor import BaseSensor
from .hx710b_driver import HX710BDriver, HX710Mode


class HX710BSensor(BaseSensor):
    """
    HX710B ADC Sensor - BaseSensor adapter for HX710BDriver
    
    This adapter bridges the gap between:
    - Low-level HX710BDriver (GPIO operations)
    - High-level BaseSensor interface (lifecycle, callbacks, threading)
    
    Key Features:
    ------------
    1. Blocking mode: read_raw_data() waits for ADC data-ready
    2. Type-safe: Returns int from read_raw_data() (not Dict)
    3. Calibration: Applies offset and slope in process_data()
    4. Validation: Checks saturation via _is_valid_reading()
    5. Thread-safe: All operations protected by locks
    
    Configuration:
    -------------
    - blocking_mode: FORCED to True (ADC nature)
    - read_timeout_ms: Default 1000ms
    - calibration: Contains offset_counts, slope_mmhg_per_count, adc_inverted
    
    Attributes:
    ----------
    driver: HX710BDriver instance (composition)
    mode: HX710Mode enum (DIFFERENTIAL_10SPS or DIFFERENTIAL_40SPS)
    adc_inverted: bool flag to invert ADC sign
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize HX710B sensor adapter
        
        Args:
            name: Sensor name (e.g., "BP_ADC", "Pressure_Sensor")
            config: Configuration dictionary with keys:
                - gpio_dout (int): DOUT pin number (BCM)
                - gpio_sck (int): SCK pin number (BCM)
                - mode (str): '10sps' or '40sps' (default: '10sps')
                - read_timeout_ms (int): Read timeout in ms (default: 1000)
                - calibration (Dict):
                    - offset_counts (int): Zero offset to subtract
                    - slope_mmhg_per_count (float): Conversion factor
                    - adc_inverted (bool): Invert sign (default: False)
        
        Raises:
            KeyError: If required config keys missing
            ValueError: If invalid mode specified
        """
        # FORCE blocking mode for ADC sensor (ADC waits for data-ready)
        config['blocking_mode'] = True
        
        # Set default timeout if not specified
        if 'read_timeout_ms' not in config:
            config['read_timeout_ms'] = 1000
        
        # Initialize BaseSensor (sets up threading, logging, etc.)
        super().__init__(name, config)
        
        # Parse ADC mode from config
        mode_str = config.get('mode', '10sps').lower()
        if mode_str == '10sps':
            self.mode = HX710Mode.DIFFERENTIAL_10SPS
        elif mode_str == '40sps':
            self.mode = HX710Mode.DIFFERENTIAL_40SPS
        else:
            self.logger.warning(f"Invalid mode '{mode_str}', defaulting to 10sps")
            self.mode = HX710Mode.DIFFERENTIAL_10SPS
        
        # Create low-level driver (composition pattern)
        self.driver = HX710BDriver(
            gpio_dout=config['gpio_dout'],
            gpio_sck=config['gpio_sck'],
            mode=self.mode,
            timeout_ms=self.read_timeout_ms
        )
        
        # Extract calibration flags
        self.adc_inverted = self.calibration.get('adc_inverted', False)
        
        self.logger.info(
            f"HX710BSensor initialized: "
            f"DOUT=GPIO{config['gpio_dout']}, SCK=GPIO{config['gpio_sck']}, "
            f"mode={self.mode.name}, timeout={self.read_timeout_ms}ms, "
            f"inverted={self.adc_inverted}"
        )
    
    # ==================== LIFECYCLE METHODS (BaseSensor Interface) ====================
    
    def initialize(self) -> bool:
        """
        Initialize HX710B hardware via low-level driver
        
        Sequence (from driver):
        1. Setup GPIO pins (SCK=LOW initially)
        2. Wait settling time (400ms for 10 SPS, 100ms for 40 SPS)
        3. Perform wake-up reads (3 attempts)
        4. Verify ADC responding
        
        Returns:
            bool: True if hardware initialized successfully
        """
        try:
            success = self.driver.initialize()
            
            if success:
                self.logger.info("HX710B hardware initialized successfully")
                
                # Log driver stats after initialization
                stats = self.driver.get_stats()
                self.logger.debug(f"Driver stats after init: {stats}")
            else:
                self.logger.error("Failed to initialize HX710B hardware")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Exception during initialization: {e}")
            return False
    
    def cleanup(self):
        """
        Cleanup hardware resources via driver
        
        Actions:
        - Stop continuous reading (if running)
        - Set SCK=LOW (avoid power-down)
        - Release GPIO resources
        
        Note: Does NOT call GPIO.cleanup() (other sensors may use GPIO)
        """
        try:
            self.driver.cleanup()
            self.logger.debug("HX710B hardware cleaned up")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    # ==================== DATA METHODS (BaseSensor Interface) ====================
    
    def read_raw_data(self) -> Optional[int]:
        """
        Read raw ADC counts from HX710B
        
        This method BLOCKS until:
        - Data ready (DOUT=LOW detected)
        - OR timeout reached (read_timeout_ms)
        
        Protocol (handled by driver):
        1. Wait for DOUT=LOW (1ms polling)
        2. Clock out 24 bits via SCK pulses
        3. Send mode selection pulses (25/26/27 total)
        4. Convert to signed 24-bit integer
        
        Returns:
            int: Raw ADC counts (-8388608 to 8388607)
                 Sign may be inverted if adc_inverted=True
            None: On timeout or read error
        
        Note:
            - Blocking behavior matches blocking_mode=True in BaseSensor
            - Timeout logged by driver (not counted as error by BaseSensor)
        """
        try:
            # Call driver's blocking read
            counts = self.driver.read(timeout_ms=self.read_timeout_ms)
            
            if counts is None:
                # Timeout already logged by driver
                return None
            
            # Apply sign inversion if configured
            if self.adc_inverted:
                counts = -counts
            
            return counts
            
        except Exception as e:
            self.logger.error(f"Error reading raw data: {e}")
            return None
    
    def process_data(self, raw_data: int) -> Optional[Dict[str, Any]]:
        """
        Process raw ADC counts to calibrated pressure
        
        Calibration Steps:
        1. Subtract offset_counts (zero calibration)
        2. Multiply by slope_mmhg_per_count (sensitivity)
        3. Return Dict with calibrated + raw values
        
        Formula:
            pressure_mmhg = (raw_counts - offset) × slope
        
        Args:
            raw_data: Raw ADC counts (int) from read_raw_data()
        
        Returns:
            Dict with keys:
                - pressure_mmhg (float): Calibrated pressure in mmHg
                - counts (int): Original raw counts (for debugging)
                - counts_zeroed (int): Counts after offset removal
                - valid (bool): Always True (saturation checked earlier)
            None: If processing fails
        
        Example:
            raw_data = 123456
            offset = 12500
            slope = 9.536743e-06
            
            counts_zeroed = 123456 - 12500 = 110956
            pressure_mmhg = 110956 × 9.536743e-06 = 1.058 mmHg
        """
        if raw_data is None:
            return None
        
        try:
            # Get calibration parameters from config
            offset_counts = self.calibration.get('offset_counts', 0)
            slope_mmhg_per_count = self.calibration.get('slope_mmhg_per_count', 9.536743e-06)
            
            # Step 1: Remove zero offset
            counts_zeroed = raw_data - offset_counts
            
            # Step 2: Apply sensitivity calibration
            pressure_mmhg = counts_zeroed * slope_mmhg_per_count
            
            return {
                'pressure_mmhg': pressure_mmhg,
                'counts': raw_data,
                'counts_zeroed': counts_zeroed,
                'valid': True  # Saturation already checked in _is_valid_reading
            }
            
        except Exception as e:
            self.logger.error(f"Error processing data: {e}")
            return None
    
    # ==================== VALIDATION HOOK (BaseSensor Override) ====================
    
    def _is_valid_reading(self, raw_data: int) -> bool:
        """
        Validate raw reading before processing
        
        Checks:
        1. raw_data is not None
        2. ADC not saturated (0x7FFFFF or -0x800000)
        
        Saturation indicates:
        - Input voltage exceeds ADC range (±20mV @ 5V)
        - Possible sensor/circuit fault
        - Reading is unreliable
        
        Args:
            raw_data: Raw ADC counts from read_raw_data()
        
        Returns:
            bool: True if valid (not saturated), False if invalid
        
        Note:
            - Called by BaseSensor._reading_loop() before process_data()
            - Invalid readings are skipped (logged as debug)
        """
        if raw_data is None:
            return False
        
        # Check saturation using driver method
        if self.driver.is_saturated(raw_data):
            self.logger.warning(
                f"ADC saturated: {raw_data} counts (0x{raw_data & 0xFFFFFF:06X})"
            )
            return False
        
        return True
    
    # ==================== UTILITY METHODS ====================
    
    def get_driver_stats(self) -> Dict[str, Any]:
        """
        Get low-level driver statistics
        
        Returns:
            Dict with keys:
                - read_count: Total successful reads
                - error_count: Total failed reads
                - error_rate: Percentage of failed reads
                - last_value: Most recent ADC value
                - mode: Operating mode (DIFFERENTIAL_10SPS or DIFFERENTIAL_40SPS)
        
        Usage:
            Monitor driver health, debug issues
        """
        return self.driver.get_stats()
    
    def self_test(self) -> bool:
        """
        Extended self-test with driver validation
        
        Test Sequence:
        1. Initialize hardware
        2. Read raw data (3 attempts)
        3. Validate readings (not saturated)
        4. Process test data
        5. Verify output format
        6. Check driver stats
        7. Cleanup hardware
        
        Returns:
            bool: True if all tests pass
        
        Logs:
            - INFO: Test progress and results
            - ERROR: Test failures with details
        """
        self.logger.info("Starting HX710B self-test...")
        
        try:
            # Test 1: Initialize hardware
            if not self.initialize():
                self.logger.error("Self-test FAILED: Cannot initialize hardware")
                return False
            
            # Test 2: Read raw data (multiple attempts for reliability)
            valid_reads = 0
            for attempt in range(3):
                raw_data = self.read_raw_data()
                
                if raw_data is not None:
                    if self._is_valid_reading(raw_data):
                        valid_reads += 1
                        self.logger.debug(f"Self-test read {attempt+1}/3: Valid ({raw_data})")
                    else:
                        self.logger.debug(f"Self-test read {attempt+1}/3: Saturated ({raw_data})")
                else:
                    self.logger.debug(f"Self-test read {attempt+1}/3: Timeout")
            
            if valid_reads == 0:
                self.logger.error("Self-test FAILED: No valid reads (all timeout/saturated)")
                return False
            
            # Test 3: Process test data
            test_counts = 123456
            processed = self.process_data(test_counts)
            
            if processed is None:
                self.logger.error("Self-test FAILED: Cannot process data")
                return False
            
            # Test 4: Verify output format
            expected_keys = ['pressure_mmhg', 'counts', 'counts_zeroed', 'valid']
            missing_keys = [k for k in expected_keys if k not in processed]
            if missing_keys:
                self.logger.error(f"Self-test FAILED: Missing keys {missing_keys}")
                return False
            
            # Test 5: Check driver stats
            stats = self.get_driver_stats()
            if stats['read_count'] == 0:
                self.logger.warning("Self-test: No successful reads in driver stats")
            
            # Test 6: Cleanup
            self.cleanup()
            
            # Summary
            self.logger.info(
                f"HX710B self-test PASSED "
                f"(valid_reads={valid_reads}/3, error_rate={stats['error_rate']:.1%})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Self-test EXCEPTION: {e}")
            return False
    
    def __repr__(self) -> str:
        """String representation for debugging"""
        return (
            f"HX710BSensor(name='{self.name}', "
            f"mode={self.mode.name}, "
            f"timeout={self.read_timeout_ms}ms, "
            f"gpio_dout={self.driver.gpio_dout}, "
            f"gpio_sck={self.driver.gpio_sck}, "
            f"inverted={self.adc_inverted})"
        )


# ==================== FACTORY FUNCTION ====================

def create_hx710b_sensor_from_config(config: Dict[str, Any]) -> Optional[HX710BSensor]:
    """
    Factory function to create HX710BSensor from app_config.yaml
    
    Args:
        config: Sensor configuration dict (from sensors.hx710b in YAML)
    
    Returns:
        HX710BSensor instance or None if disabled/invalid
    
    Example YAML:
        sensors:
          hx710b:
            enabled: true
            gpio_dout: 6
            gpio_sck: 5
            mode: '10sps'
            calibration:
              offset_counts: 12500
              slope_mmhg_per_count: 9.536743e-06
    
    Usage:
        >>> from src.sensors.hx710b_sensor import create_hx710b_sensor_from_config
        >>> import yaml
        >>> 
        >>> with open('config/app_config.yaml') as f:
        >>>     cfg = yaml.safe_load(f)
        >>> 
        >>> sensor = create_hx710b_sensor_from_config(cfg['sensors']['hx710b'])
        >>> if sensor:
        >>>     sensor.start()
    """
    logger = logging.getLogger("HX710BSensor.Factory")
    
    # Check if enabled
    if not config.get('enabled', True):
        logger.info("HX710B sensor disabled in config")
        return None
    
    # Validate required keys
    required_keys = ['gpio_dout', 'gpio_sck']
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        logger.error(f"Missing required config keys: {missing_keys}")
        return None
    
    # Create sensor
    try:
        sensor = HX710BSensor("HX710B_ADC", config)
        logger.info("Created HX710B sensor from config")
        return sensor
    except Exception as e:
        logger.error(f"Failed to create sensor: {e}")
        return None
