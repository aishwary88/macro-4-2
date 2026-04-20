"""
Logging system with file + console handlers.
Structured logging for all modules.
"""

import logging
import sys
from pathlib import Path

# Ensure logs directory exists
_LOGS_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

_LOG_FILE = _LOGS_DIR / "app.log"
_initialized = False


def _setup_root_logger():
    """Configure the root logger once."""
    global _initialized
    if _initialized:
        return

    root_logger = logging.getLogger("traffic_analyzer")
    root_logger.setLevel(logging.DEBUG)

    # Formatter
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (INFO level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (DEBUG level — captures everything)
    file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    _initialized = True


def get_logger(module_name: str) -> logging.Logger:
    """Get a module-specific logger.

    Usage:
        from modules.utils.logger import get_logger
        logger = get_logger("detection")
        logger.info("Detected 5 vehicles")
    """
    _setup_root_logger()
    return logging.getLogger(f"traffic_analyzer.{module_name}")
