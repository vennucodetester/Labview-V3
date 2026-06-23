"""
logging_setup.py

Configure application-wide logging to both console and file.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime


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
    
    # Remove any existing handlers
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    
    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
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
    
    # Log initialization message
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized -> {log_path}")
    
    return log_path

