"""
Shared singleton objects: YOLO model, EasyOCR reader, DB session.
Loaded once and reused across the entire application to avoid
re-loading heavy models multiple times.
"""

import threading
from typing import Optional

_lock = threading.Lock()

# ========================================
# YOLO Model (lazy loaded singleton)
# ========================================
_yolo_model = None


def get_yolo_model():
    """Get or create the YOLO model singleton."""
    global _yolo_model
    if _yolo_model is None:
        with _lock:
            if _yolo_model is None:
                from ultralytics import YOLO
                from core.config import settings
                from modules.utils.logger import get_logger

                logger = get_logger("dependencies")
                logger.info(f"Loading YOLO model from {settings.YOLO_MODEL_PATH}")
                _yolo_model = YOLO(settings.YOLO_MODEL_PATH)
                logger.info("YOLO model loaded successfully")
    return _yolo_model


# ========================================
# EasyOCR Reader (lazy loaded singleton)
# ========================================
_ocr_reader = None


def get_ocr_reader():
    """Get or create the EasyOCR reader singleton."""
    global _ocr_reader
    if _ocr_reader is None:
        with _lock:
            if _ocr_reader is None:
                import easyocr
                from modules.utils.logger import get_logger

                logger = get_logger("dependencies")
                logger.info("Loading EasyOCR reader (first run may download models)...")
                _ocr_reader = easyocr.Reader(["en"], gpu=False)
                logger.info("EasyOCR reader loaded successfully")
    return _ocr_reader


# ========================================
# Database Session Factory
# ========================================
_session_factory = None


def get_db_session_factory():
    """Get or create the SQLAlchemy session factory."""
    global _session_factory
    if _session_factory is None:
        with _lock:
            if _session_factory is None:
                from modules.data.database import create_session_factory

                _session_factory = create_session_factory()
    return _session_factory


def get_db_session():
    """Get a new database session."""
    factory = get_db_session_factory()
    return factory()
