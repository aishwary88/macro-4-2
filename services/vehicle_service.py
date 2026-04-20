"""
VehicleService — queries for vehicle records stored in the DB.
"""

from typing import List, Optional
from modules.data.database import get_session, Vehicle, SpeedLog
from modules.utils.logger import get_logger

logger = get_logger(__name__)


class VehicleService:

    @staticmethod
    def get_vehicles(video_id: int) -> List[dict]:
        """Return all vehicles detected in a given video."""
        session = get_session()
        try:
            records = (
                session.query(Vehicle)
                .filter(Vehicle.video_id == video_id)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "vehicle_unique_id": r.vehicle_unique_id,
                    "vehicle_type": r.vehicle_type,
                    "plate_number": r.plate_number,
                    "avg_speed": r.avg_speed,
                    "max_speed": r.max_speed,
                    "status": "overspeed" if r.overspeed_flag else "normal",
                    "first_seen": str(r.first_seen_time),
                    "last_seen": str(r.last_seen_time),
                }
                for r in records
            ]
        finally:
            session.close()

    @staticmethod
    def get_vehicle_detail(vehicle_id: int) -> Optional[dict]:
        """Return full vehicle info including speed logs."""
        session = get_session()
        try:
            r = session.get(Vehicle, vehicle_id)
            if r is None:
                return None

            logs = (
                session.query(SpeedLog)
                .filter(SpeedLog.vehicle_id == vehicle_id)
                .order_by(SpeedLog.timestamp)
                .all()
            )
            return {
                "id": r.id,
                "vehicle_unique_id": r.vehicle_unique_id,
                "vehicle_type": r.vehicle_type,
                "plate_number": r.plate_number,
                "avg_speed": r.avg_speed,
                "max_speed": r.max_speed,
                "status": "overspeed" if r.overspeed_flag else "normal",
                "first_seen": str(r.first_seen_time),
                "last_seen": str(r.last_seen_time),
                "speed_logs": [
                    {
                        "timestamp": lg.timestamp,
                        "speed": lg.speed,
                    }
                    for lg in logs
                ],
            }
        finally:
            session.close()

    @staticmethod
    def get_overspeeding_vehicles(video_id: int) -> List[dict]:
        session = get_session()
        try:
            records = (
                session.query(Vehicle)
                .filter(
                    Vehicle.video_id == video_id,
                    Vehicle.overspeed_flag == True,  # noqa: E712
                )
                .all()
            )
            return [
                {
                    "id": r.id,
                    "vehicle_unique_id": r.vehicle_unique_id,
                    "vehicle_type": r.vehicle_type,
                    "plate_number": r.plate_number,
                    "avg_speed": r.avg_speed,
                    "max_speed": r.max_speed,
                }
                for r in records
            ]
        finally:
            session.close()
