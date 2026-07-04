"""
logging_setup.py

Configure application-wide logging to both console and file.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime


class _StreamToLogger:
    """File-like stream that forwards print output to logging without recursion."""

    def __init__(self, logger_name: str, level: int, fallback):
        self.logger = logging.getLogger(logger_name)
        self.level = level
        self.fallback = fallback
        self._buffer = ""
        self._logging = False

    def write(self, message):
        if not message:
            return
        if self._logging:
            if self.fallback is not None:
                try:
                    self.fallback.write(str(message))
                except Exception:
                    pass
            return
        self._buffer += str(message)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                try:
                    self._logging = True
                    self.logger.log(self.level, line.rstrip())
                finally:
                    self._logging = False

    def flush(self):
        if self._buffer.strip():
            try:
                self._logging = True
                self.logger.log(self.level, self._buffer.rstrip())
            finally:
                self._logging = False
        self._buffer = ""
        try:
            if self.fallback is not None:
                self.fallback.flush()
        except Exception:
            pass

    def isatty(self):
        return False


def init_logging(log_path: str | None = None) -> str:
    """
    Initialize root logger with console and file handlers.
    
    Args:
        log_path: Optional path to log file. If None, creates logs/app_YYYYMMDD_HHMMSS.log
    
    Returns:
        Path to the log file
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Default log path if not provided
    if not log_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join("logs", f"app_{timestamp}.log")
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    logging.raiseExceptions = False
    
    # Remove any existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    
    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler. pythonw/double-click launches often have no console
    # stream; installing a handler with a None stream makes every print fail.
    if sys.__stdout__ is not None and hasattr(sys.__stdout__, "write"):
        console_handler = logging.StreamHandler(sys.__stdout__)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Log initialization message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized -> {log_path}")

    # The app is normally launched via .pyw/.vbs, where print diagnostics have
    # no visible console. Capture them into the same rotating log file.
    sys.stdout = _StreamToLogger("stdout", logging.INFO, sys.__stdout__)
    sys.stderr = _StreamToLogger("stderr", logging.ERROR, sys.__stderr__)
    
    return log_path

