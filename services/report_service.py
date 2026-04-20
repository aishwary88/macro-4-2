"""
ReportService — Excel report generation and retrieval.
"""

import os
from typing import Optional

from modules.data.excel_report import generate_excel_report
from modules.data.analytics import compute_analytics
from modules.data.database import get_session, get_video, Video
from modules.utils.logger import get_logger
from core.config import settings

logger = get_logger(__name__)


class ReportService:

    @staticmethod
    def generate_excel_report(video_id: int) -> str:
        """Generate an Excel report for the given video; return its path."""
        from modules.data.database import get_vehicles_by_video
        import pandas as pd

        analytics = compute_analytics(video_id)
        video_record = get_video(video_id)
        filename = video_record.get("filename", f"video_{video_id}") if video_record else f"video_{video_id}"

        # Build dataframe from vehicle records
        vehicles = get_vehicles_by_video(video_id)
        df_data = [
            {
                "vehicle_id": v["vehicle_unique_id"],
                "vehicle_type": v["vehicle_type"],
                "plate_number": v["plate_number"],
                "avg_speed": v["avg_speed"],
                "max_speed": v["max_speed"],
                "overspeed": v["overspeed_flag"],
                "first_seen": str(v.get("first_seen_time", "")),
                "last_seen": str(v.get("last_seen_time", "")),
                "frame_count": v.get("frame_count", 0),
            }
            for v in vehicles
        ]
        df = pd.DataFrame(df_data)

        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        excel_path = os.path.join(
            settings.OUTPUT_DIR,
            f"report_video_{video_id}.xlsx"
        )

        generate_excel_report(df, analytics, excel_path, video_filename=filename)

        # Persist path to DB
        session = get_session()
        try:
            record = session.query(Video).filter_by(id=video_id).first()
            if record:
                record.excel_path = excel_path
                session.commit()
        finally:
            session.close()

        logger.info(f"Excel report saved → {excel_path}")
        return excel_path

    @staticmethod
    def get_excel_path(video_id: int) -> Optional[str]:
        """Return path to existing Excel file or None if not generated yet."""
        record = get_video(video_id)
        if record and record.get("excel_path") and os.path.exists(record["excel_path"]):
            return record["excel_path"]
        return None

    @staticmethod
    def generate_summary(video_id: int) -> dict:
        """Return analytics summary dict for the given video."""
        return compute_analytics(video_id)
