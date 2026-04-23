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


import asyncio
import json

class AdminDashboardHandler(logging.Handler):
    """Pushes critical logs directly to the Admin Dashboard."""
    def emit(self, record):
        if record.levelno < logging.WARNING:
            return
        try:
            # Lazy import to avoid circular dependencies
            from services.distributed_state import distributed_state
            if not distributed_state.redis:
                return

            msg = self.format(record)
            
            trace = {
                "event_type": "SYSTEM_ERROR" if record.levelno >= logging.ERROR else "SYSTEM_WARNING",
                "user_id": "system",
                "match_id": "global",
                "payload": {"log": msg, "module": record.module, "func": record.funcName},
                "success": False,
                "error": msg,
                "duration_ms": 0
            }
            
            flat_trace = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in trace.items()}
            
            # Run in background if event loop exists
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(distributed_state.redis.xadd("admin:events", flat_trace, maxlen=1000))
            except RuntimeError:
                pass # No running loop
        except Exception:
            pass

def setup_logger(name: str = "bot") -> logging.Logger:
    """Create and configure the application logger."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    _logger = logging.getLogger(name)
    _logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Standard console handler
    console_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    
    # Avoid duplicate handlers
    if not _logger.handlers:
        _logger.addHandler(console_handler)
        _logger.addHandler(AdminDashboardHandler())
    
    # Add PII scrubbing in production
    if log_level != "DEBUG":
        _logger.addFilter(PIIScrubFilter(enabled=True))
    
    return _logger


# Global logger instance
logger = setup_logger("bot")
