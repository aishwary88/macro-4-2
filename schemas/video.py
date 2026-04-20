"""Pydantic schemas for video upload, status, and results."""

from pydantic import BaseModel
from typing import Optional


class VideoUploadResponse(BaseModel):
    video_id: int
    status: str
    message: str


class VideoStatusResponse(BaseModel):
    video_id: int
    status: str
    progress: int           # 0-100
    message: Optional[str] = None


class VideoResultsResponse(BaseModel):
    video_id: int
    total_vehicles: int
    cars: int
    trucks: int
    buses: int
    bikes: int
    overspeed_count: int
    overspeed_percentage: float
    avg_speed: float
    max_speed: float
    min_speed: float
    vehicles_per_minute: Optional[float] = None
    peak_traffic_time: Optional[str] = None


class VideoListItem(BaseModel):
    video_id: int
    filename: str
    status: str
    upload_time: str
    total_vehicles: Optional[int] = None
    duration: Optional[float] = None
