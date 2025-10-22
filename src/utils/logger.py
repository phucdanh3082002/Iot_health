"""
Logger Utilities
Centralized logging setup cho IoT Health Monitoring System
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from datetime import datetime


def setup_logger(name: str = "health_monitor", 
                config_path: Optional[str] = None,
                log_level: str = "INFO") -> logging.Logger:
    """
    Setup centralized logger for the application
    
    Args:
        name: Logger name
        config_path: Path to logging configuration file
        log_level: Default log level
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Set log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    
    # Create formatters
    formatter = get_formatter("detailed")
    
    # Add console handler
    console_handler = create_console_handler(log_level)
    logger.addHandler(console_handler)
    
    # Try to add file handler if config available
    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logging_config = config.get('logging', {})
            log_file = logging_config.get('file', 'logs/health_monitor.log')
            max_size = logging_config.get('max_size', '10MB')
            backup_count = logging_config.get('backup_count', 5)
            
            file_handler = create_file_handler(log_file, max_size, backup_count, log_level)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not load logging config: {e}")
    
    # Configure third-party loggers
    configure_third_party_loggers("WARNING")
    
    return logger


def create_file_handler(log_file: str, 
                       max_size: str = "10MB",
                       backup_count: int = 5,
                       log_level: str = "INFO") -> logging.handlers.RotatingFileHandler:
    """
    Create rotating file handler for logging
    
    Args:
        log_file: Path to log file
        max_size: Maximum file size before rotation
        backup_count: Number of backup files to keep
        log_level: Log level for this handler
        
    Returns:
        Configured file handler
    """
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Parse max size
    max_bytes = parse_log_size(max_size)
    
    # Create handler
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
    )
    
    # Set level and formatter
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    handler.setLevel(numeric_level)
    handler.setFormatter(get_formatter("detailed"))
    
    return handler


def create_console_handler(log_level: str = "INFO") -> logging.StreamHandler:
    """
    Create console handler for logging
    
    Args:
        log_level: Log level for console output
        
    Returns:
        Configured console handler
    """
    handler = logging.StreamHandler(sys.stdout)
    
    # Set level and formatter
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    handler.setLevel(numeric_level)
    handler.setFormatter(get_formatter("simple"))
    
    return handler


def create_syslog_handler(address: str = "/dev/log",
                         facility: int = logging.handlers.SysLogHandler.LOG_USER) -> logging.handlers.SysLogHandler:
    """
    Create syslog handler for system logging
    
    Args:
        address: Syslog address
        facility: Syslog facility
        
    Returns:
        Configured syslog handler
    """
    try:
        handler = logging.handlers.SysLogHandler(address=address, facility=facility)
        handler.setFormatter(get_formatter("syslog"))
        return handler
    except OSError:
        # Syslog not available, return None
        return None


def get_formatter(format_type: str = "detailed") -> logging.Formatter:
    """
    Get logging formatter
    
    Args:
        format_type: Type of formatter ('simple', 'detailed', 'json', 'syslog')
        
    Returns:
        Logging formatter
    """
    if format_type == "simple":
        return logging.Formatter(
            '%(levelname)s: %(message)s'
        )
    elif format_type == "detailed":
        return logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    elif format_type == "json":
        return JSONFormatter()
    elif format_type == "syslog":
        return logging.Formatter(
            '%(name)s[%(process)d]: %(levelname)s %(message)s'
        )
    else:
        return logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )


def parse_log_size(size_str: str) -> int:
    """
    Parse log size string to bytes
    
    Args:
        size_str: Size string (e.g., "10MB", "1GB")
        
    Returns:
        Size in bytes
    """
    size_str = size_str.upper().strip()
    
    # Extract number and unit
    import re
    match = re.match(r'^(\d+(?:\.\d+)?)\s*(B|KB|MB|GB)?$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    
    number = float(match.group(1))
    unit = match.group(2) or 'B'
    
    # Convert to bytes
    multipliers = {
        'B': 1,
        'KB': 1024,
        'MB': 1024 * 1024,
        'GB': 1024 * 1024 * 1024
    }
    
    return int(number * multipliers[unit])


def setup_module_logger(module_name: str, parent_logger: str = "health_monitor") -> logging.Logger:
    """
    Setup logger for specific module
    
    Args:
        module_name: Name of the module
        parent_logger: Parent logger name
        
    Returns:
        Module-specific logger
    """
    logger = logging.getLogger(f"{parent_logger}.{module_name}")
    return logger


def log_system_info(logger: logging.Logger):
    """
    Log system information at startup
    
    Args:
        logger: Logger instance
    """
    import platform
    import psutil
    
    try:
        logger.info("=== System Information ===")
        logger.info(f"Platform: {platform.platform()}")
        logger.info(f"Python version: {platform.python_version()}")
        logger.info(f"CPU count: {psutil.cpu_count()}")
        logger.info(f"Memory: {psutil.virtual_memory().total / (1024**3):.1f} GB")
        logger.info(f"Disk space: {psutil.disk_usage('/').total / (1024**3):.1f} GB")
        logger.info("=== End System Information ===")
    except ImportError:
        logger.warning("psutil not available for system info logging")
    except Exception as e:
        logger.error(f"Error logging system info: {e}")


def log_exception(logger: logging.Logger, exception: Exception, 
                 context: Dict[str, Any] = None):
    """
    Log exception with context information
    
    Args:
        logger: Logger instance
        exception: Exception to log
        context: Additional context information
    """
    logger.error(f"Exception occurred: {type(exception).__name__}: {exception}")
    
    if context:
        logger.error(f"Context: {context}")
    
    # Log full traceback
    import traceback
    logger.error(f"Traceback: {traceback.format_exc()}")


def create_audit_logger(audit_file: str = "logs/audit.log") -> logging.Logger:
    """
    Create audit logger for security events
    
    Args:
        audit_file: Path to audit log file
        
    Returns:
        Audit logger instance
    """
    logger = logging.getLogger("audit")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create audit file handler
    audit_path = Path(audit_file)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    
    handler = logging.FileHandler(audit_file, encoding='utf-8')
    handler.setLevel(logging.INFO)
    
    # Audit-specific formatter
    formatter = logging.Formatter(
        '%(asctime)s - AUDIT - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.propagate = False  # Don't propagate to root logger
    
    return logger


def log_health_event(logger: logging.Logger, event_type: str, 
                    patient_id: str, data: Dict[str, Any]):
    """
    Log health monitoring events
    
    Args:
        logger: Logger instance
        event_type: Type of health event
        patient_id: Patient identifier
        data: Event data
    """
    logger.info(f"HEALTH_EVENT - Type: {event_type} - Patient: {patient_id} - Data: {data}")


def configure_third_party_loggers(level: str = "WARNING"):
    """
    Configure third-party library loggers
    
    Args:
        level: Log level for third-party loggers
    """
    numeric_level = getattr(logging, level.upper(), logging.WARNING)
    
    # Common third-party libraries to configure
    third_party_loggers = [
        'urllib3',
        'requests',
        'gpiozero',
        'smbus2',
        'RPi.GPIO',
        'numpy',
        'scipy',
        'matplotlib',
        'PIL'
    ]
    
    for logger_name in third_party_loggers:
        logging.getLogger(logger_name).setLevel(numeric_level)


class HealthMonitorLogFilter(logging.Filter):
    """
    Custom log filter for health monitor logs
    """
    
    def __init__(self, patient_id: Optional[str] = None):
        """
        Initialize log filter
        
        Args:
            patient_id: Patient ID to filter by (optional)
        """
        super().__init__()
        self.patient_id = patient_id
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records
        
        Args:
            record: Log record to filter
            
        Returns:
            True if record should be logged
        """
        # Filter by patient ID if specified
        if self.patient_id:
            if hasattr(record, 'patient_id'):
                return record.patient_id == self.patient_id
            elif 'patient' in record.getMessage().lower():
                return True  # Allow patient-related messages
        
        # Allow all other messages
        return True


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging
    """
    
    def __init__(self):
        """Initialize JSON formatter"""
        super().__init__()
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON
        
        Args:
            record: Log record to format
            
        Returns:
            JSON-formatted log string
        """
        import json
        from datetime import datetime
        
        # Create log entry
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_entry['extra'] = record.extra_data
        
        return json.dumps(log_entry, ensure_ascii=False)


def get_logger(name: str = "health_monitor") -> logging.Logger:
    """
    Get or create a logger instance
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return setup_logger(name)