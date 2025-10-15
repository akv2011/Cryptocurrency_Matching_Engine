"""
Structured JSON logging for the matching engine.

Provides audit trail for all operations with high-precision timestamps.
"""

import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Includes:
        - timestamp (ISO 8601 with microseconds)
        - level
        - logger name
        - message
        - extra fields
        - exception info (if present)
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        # Add extra fields from record
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Get a configured logger with JSON formatting.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(level)
        
        # Console handler with JSON formatter
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(JSONFormatter())
        
        logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
    
    return logger


# Convenience function for structured logging
def log_event(logger: logging.Logger, level: str, event: str, **kwargs: Any) -> None:
    """
    Log a structured event with additional context.
    
    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error, critical)
        event: Event name/type
        **kwargs: Additional context fields
        
    Example:
        log_event(logger, 'info', 'order_submitted',
                 order_id='123', symbol='BTC-USDT', side='buy')
    """
    log_func = getattr(logger, level.lower())
    log_func(event, extra=kwargs)


# Create default logger for the application
app_logger = get_logger("matching_engine")
