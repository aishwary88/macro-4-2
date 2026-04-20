"""
VideoService — CRUD operations for video records.
Handles saving uploads, querying status, and listing processed videos.
"""

import os
import shutil
from datetime import datetime
from typing import List, Optional

from core.config import settings
from modules.data.database import (
    create_video, update_video_status, get_video, get_session, Video,
)
from modules.utils.logger import get_logger

logger = get_logger(__name__)


class VideoService:

    @staticmethod
    def save_uploaded_video(filename: str, tmp_path: str) -> tuple:
        """
        Move uploaded file from tmp_path into INPUT_DIR and create a DB record.
        Returns (video_id, final_filepath).
        """
        os.makedirs(settings.INPUT_DIR, exist_ok=True)
        dest_path = os.path.join(settings.INPUT_DIR, filename)

        # Avoid overwriting: append timestamp if file already exists
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{base}_{ts}{ext}"
            dest_path = os.path.join(settings.INPUT_DIR, filename)

        shutil.move(tmp_path, dest_path)
        logger.info(f"Saved upload → {dest_path}")

        video_id = create_video(filename)
        return video_id, dest_path

    @staticmethod
    def get_video_status(video_id: int) -> dict:
        """Return status dict for the given video."""
        record = get_video(video_id)
        if record is None:
            return {"status": "not_found", "progress": 0}
        return {
            "video_id": video_id,
            "status": record["status"],
            "progress": record.get("progress", 0),
        }

    @staticmethod
    def get_video_results(video_id: int) -> Optional[dict]:
        """Return the stored video record as a dict."""
        return get_video(video_id)

    @staticmethod
    def set_video_status(video_id: int, status: str, progress: int = 0, **kwargs) -> None:
        update_video_status(video_id, status, progress, **kwargs)

    @staticmethod
    def list_videos() -> List[dict]:
        session = get_session()
        try:
            records = (
                session.query(Video)
                .order_by(Video.upload_time.desc())
                .all()
            )
            return [
                {
                    "video_id": r.id,
                    "filename": r.filename,
                    "status": r.status,
                    "upload_time": str(r.upload_time),
                    "total_vehicles": r.total_vehicles,
                    "duration": r.duration,
                }
                for r in records
            ]
        finally:
            session.close()
