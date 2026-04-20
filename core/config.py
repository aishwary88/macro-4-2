"""
Global configuration loaded from .env file.
All system settings are centralized here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Application settings loaded from environment variables."""

    # Base paths
    BASE_DIR: Path = BASE_DIR
    INPUT_DIR: Path = BASE_DIR / os.getenv("INPUT_DIR", "input")
    OUTPUT_DIR: Path = BASE_DIR / os.getenv("OUTPUT_DIR", "output")
    MODELS_DIR: Path = BASE_DIR / os.getenv("MODELS_DIR", "models")
    LOGS_DIR: Path = BASE_DIR / os.getenv("LOGS_DIR", "logs")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./traffic_analyzer.db")

    # YOLO Model
    YOLO_MODEL_PATH: str = str(BASE_DIR / os.getenv("YOLO_MODEL_PATH", "models/yolov8n.pt"))

    # Speed settings
    SPEED_LIMIT_KMH: float = float(os.getenv("SPEED_LIMIT_KMH", "60"))
    ROI_DISTANCE_METERS: float = float(os.getenv("ROI_DISTANCE_METERS", "10"))
    ROI_LINE_A_Y: int = int(os.getenv("ROI_LINE_A_Y", "300"))
    ROI_LINE_B_Y: int = int(os.getenv("ROI_LINE_B_Y", "500"))

    # Detection
    DETECTION_CONFIDENCE: float = float(os.getenv("DETECTION_CONFIDENCE", "0.5"))
    OCR_CONFIDENCE: float = float(os.getenv("OCR_CONFIDENCE", "0.4"))

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # Processing
    ANPR_FRAME_INTERVAL: int = int(os.getenv("ANPR_FRAME_INTERVAL", "10"))
    MAX_TRACK_AGE: int = int(os.getenv("MAX_TRACK_AGE", "30"))
    CAMERA_FPS: int = int(os.getenv("CAMERA_FPS", "60"))
    CAMERA_FRAME_SKIP: int = int(os.getenv("CAMERA_FRAME_SKIP", "0"))

    @classmethod
    def ensure_directories(cls):
        """Create all required directories if they don't exist."""
        for directory in [cls.INPUT_DIR, cls.OUTPUT_DIR, cls.MODELS_DIR, cls.LOGS_DIR]:
            directory.mkdir(parents=True, exist_ok=True)


# Singleton settings instance
settings = Settings()
settings.ensure_directories()
