"""Pydantic schemas for vehicle data responses."""

from pydantic import BaseModel
from typing import Optional, List


class SpeedLogEntry(BaseModel):
    timestamp: float
    speed: float
    position_x: float
    position_y: float


class VehicleResponse(BaseModel):
    id: int
    vehicle_unique_id: int
    vehicle_type: str
    plate_number: Optional[str] = None
    avg_speed: Optional[float] = None
    max_speed: Optional[float] = None
    status: str          # "normal" | "overspeed"
    first_seen: str
    last_seen: str


class VehicleDetailResponse(VehicleResponse):
    speed_logs: List[SpeedLogEntry] = []
