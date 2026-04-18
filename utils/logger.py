"""
Logger module with PII scrubbing for production safety.
"""

import os
import re
import logging


class PIIScrubFilter(logging.Filter):
    """Logging filter that redacts potential PII from log messages in production.
    
    Scrubs:
    - PSIDs (long numeric sequences that could be Facebook IDs)
    - Full user IDs (replaces with last 4 digits)
    - Webhook payload previews containing user data
    """
    # Match standalone long numbers (potential user IDs / PSIDs)
    _LONG_NUM_PATTERN = re.compile(r'\b(\d{10,})\b')
    
    def __init__(self, enabled: bool = True):
        super().__init__()
        self.enabled = enabled

    def filter(self, record: logging.LogRecord) -> bool:
        if self.enabled and hasattr(record, 'msg'):
            try:
                msg = str(record.msg)
                # Replace long numeric IDs with redacted versions
                msg = self._LONG_NUM_PATTERN.sub(
                    lambda m: f"...{m.group(1)[-4:]}", msg
                )
                record.msg = msg
            except Exception:
                pass  # Never break logging
        return True


def setup_logger(name: str = "bot") -> logging.Logger:
    """Create and configure the application logger."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    _logger = logging.getLogger(name)
    _logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Add PII scrubbing in production (when not DEBUG)
    if log_level != "DEBUG":
        _logger.addFilter(PIIScrubFilter(enabled=True))
    
    return _logger


# Global logger instance
logger = setup_logger("bot")
