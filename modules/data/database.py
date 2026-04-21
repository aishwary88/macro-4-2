"""
SQLAlchemy ORM models and database management.
Tables: Videos, Vehicles, SpeedLogs, FrameEvents.
"""

from datetime import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, ForeignKey, Text,
)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, relationship, Session,
)
from core.config import settings
from modules.utils.logger import get_logger

logger = get_logger("database")

Base = declarative_base()


# ========================================
# ORM Models
# ========================================

class Video(Base):
    """Videos table — one record per uploaded video."""
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    upload_time = Column(DateTime, default=datetime.now)
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    total_vehicles = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    fps = Column(Float, default=0.0)
    processed_video_path = Column(String(500), nullable=True)
    excel_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    vehicles = relationship("Vehicle", back_populates="video", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Video(id={self.id}, filename='{self.filename}', status='{self.status}')>"


class Vehicle(Base):
    """Vehicles table — one row per detected vehicle per video."""
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    vehicle_unique_id = Column(Integer, nullable=False)  # tracking ID
    vehicle_type = Column(String(50), default="Unknown")
    plate_number = Column(String(50), default="N/A")
    avg_speed = Column(Float, default=0.0)
    max_speed = Column(Float, default=0.0)
    overspeed_flag = Column(Boolean, default=False)
    first_seen_time = Column(DateTime, nullable=True)
    last_seen_time = Column(DateTime, nullable=True)
    frame_count = Column(Integer, default=0)

    # Relationships
    video = relationship("Video", back_populates="vehicles")
    speed_logs = relationship("SpeedLog", back_populates="vehicle", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Vehicle(id={self.id}, type='{self.vehicle_type}', speed={self.avg_speed:.1f})>"


class SpeedLog(Base):
    """Speed logs — per-frame speed data for detailed analysis."""
    __tablename__ = "speed_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    timestamp = Column(Float, nullable=False)  # seconds from video start
    speed = Column(Float, nullable=False)

    # Relationships
    vehicle = relationship("Vehicle", back_populates="speed_logs")


class FrameEvent(Base):
    """Frame events — position data per frame for debugging."""
    __tablename__ = "frame_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    vehicle_unique_id = Column(Integer, nullable=False)
    frame_number = Column(Integer, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)


# ========================================
# Database Setup
# ========================================

_engine = None
_SessionFactory = None


def get_engine():
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = settings.DATABASE_URL
        # Handle relative SQLite paths
        if db_url.startswith("sqlite:///./"):
            db_path = settings.BASE_DIR / db_url.replace("sqlite:///./", "")
            db_url = f"sqlite:///{db_path}"

        _engine = create_engine(db_url, echo=False)
        logger.info(f"Database engine created: {db_url}")
    return _engine


def create_session_factory():
    """Create and return a sessionmaker factory."""
    global _SessionFactory
    engine = get_engine()
    _SessionFactory = sessionmaker(bind=engine)
    return _SessionFactory


def init_db():
    """Create all tables in the database."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully")


def get_session() -> Session:
    """Get a new database session."""
    global _SessionFactory
    if _SessionFactory is None:
        create_session_factory()
    return _SessionFactory()


# ========================================
# CRUD Operations
# ========================================

def create_video(filename: str, fps: float = 0.0, duration: float = 0.0) -> int:
    """Create a new video record.

    Returns:
        Video ID.
    """
    session = get_session()
    try:
        video = Video(
            filename=filename,
            status="pending",
            fps=fps,
            duration=duration,
        )
        session.add(video)
        session.commit()
        video_id = video.id
        logger.info(f"Video record created: id={video_id}, file={filename}")
        return video_id
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating video record: {e}")
        raise
    finally:
        session.close()


def update_video_status(video_id: int, status: str, progress: int = None, **kwargs):
    """Update video processing status."""
    session = get_session()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if video:
            video.status = status
            if progress is not None:
                video.progress = progress
            for key, value in kwargs.items():
                if hasattr(video, key):
                    setattr(video, key, value)
            session.commit()
            logger.debug(f"Video {video_id} status: {status} ({progress}%)")
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating video status: {e}")
    finally:
        session.close()


def get_video(video_id: int) -> dict:
    """Get video record as dict."""
    session = get_session()
    try:
        video = session.query(Video).filter_by(id=video_id).first()
        if not video:
            return None
        return {
            "id": video.id,
            "filename": video.filename,
            "upload_time": video.upload_time.isoformat() if video.upload_time else None,
            "status": video.status,
            "progress": video.progress,
            "total_vehicles": video.total_vehicles,
            "duration": video.duration,
            "fps": video.fps,
            "processed_video_path": video.processed_video_path,
            "excel_path": video.excel_path,
            "error_message": video.error_message,
        }
    finally:
        session.close()


def save_vehicles(video_id: int, vehicle_data_list: list):
    """Save multiple vehicle records to database.

    Args:
        video_id: Video ID.
        vehicle_data_list: List of dicts with vehicle info.
    """
    if not vehicle_data_list:
        logger.warning(f"save_vehicles called with empty list for video {video_id}")
        return

    session = get_session()
    try:
        for vdata in vehicle_data_list:
            # Handle first_seen / last_seen — may be datetime or string
            first_seen = vdata.get("first_seen")
            last_seen = vdata.get("last_seen")
            if isinstance(first_seen, str):
                try:
                    first_seen = datetime.fromisoformat(first_seen) if first_seen else None
                except ValueError:
                    first_seen = None
            if isinstance(last_seen, str):
                try:
                    last_seen = datetime.fromisoformat(last_seen) if last_seen else None
                except ValueError:
                    last_seen = None

            # Support both "overspeed" and "overspeed_flag" key names
            overspeed = vdata.get("overspeed_flag", vdata.get("overspeed", False))

            vehicle = Vehicle(
                video_id=video_id,
                vehicle_unique_id=vdata.get("vehicle_id", 0),
                vehicle_type=vdata.get("vehicle_type", "Unknown"),
                plate_number=vdata.get("plate_number", "N/A"),
                avg_speed=vdata.get("avg_speed", 0.0),
                max_speed=vdata.get("max_speed", 0.0),
                overspeed_flag=bool(overspeed),
                first_seen_time=first_seen,
                last_seen_time=last_seen,
                frame_count=vdata.get("frame_count", 0),
            )
            session.add(vehicle)

        session.commit()
        logger.info(f"Saved {len(vehicle_data_list)} vehicles for video {video_id}")
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving vehicles: {e}", exc_info=True)
    finally:
        session.close()


def delete_vehicles_for_video(video_id: int) -> int:
    """Delete all vehicle records for a video (used before re-save to prevent duplicates).

    Args:
        video_id: Video ID.

    Returns:
        Number of records deleted.
    """
    session = get_session()
    try:
        deleted = session.query(Vehicle).filter_by(video_id=video_id).delete()
        session.commit()
        if deleted:
            logger.info(f"Deleted {deleted} existing vehicle records for video {video_id}")
        return deleted
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting vehicles for video {video_id}: {e}")
        return 0
    finally:
        session.close()


def get_vehicles_by_video(video_id: int) -> list:
    """Get all vehicles for a video."""
    session = get_session()
    try:
        vehicles = session.query(Vehicle).filter_by(video_id=video_id).all()
        return [
            {
                "id": v.id,
                "vehicle_unique_id": v.vehicle_unique_id,
                "vehicle_type": v.vehicle_type,
                "plate_number": v.plate_number,
                "avg_speed": v.avg_speed,
                "max_speed": v.max_speed,
                "overspeed_flag": v.overspeed_flag,
                "first_seen_time": v.first_seen_time.isoformat() if v.first_seen_time else None,
                "last_seen_time": v.last_seen_time.isoformat() if v.last_seen_time else None,
                "frame_count": v.frame_count,
            }
            for v in vehicles
        ]
    finally:
        session.close()
