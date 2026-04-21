"""
SentrySpeed FastAPI Application.
All API routes + static file serving + camera stream.
"""

import os
import tempfile
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from core.config import settings
from modules.data.database import init_db
from modules.utils.logger import get_logger
from schemas.video import VideoUploadResponse, VideoStatusResponse, VideoResultsResponse, VideoListItem
from schemas.vehicle import VehicleResponse, VehicleDetailResponse
from schemas.response import APIResponse, ErrorResponse
from services.video_service import VideoService
from services.vehicle_service import VehicleService
from services.report_service import ReportService
from services.processing_service import ProcessingService

logger = get_logger("app")

# ------------------------------------------------------------------
# App Factory
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app):
    init_db()
    settings.ensure_directories()
    logger.info("SentrySpeed API started ✓")
    yield


app = FastAPI(
    title="SentrySpeed — Traffic Analyzer",
    description="Production-grade modular traffic analysis API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Static files
_static_dir = os.path.join(os.path.dirname(__file__), "static")
_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(_static_dir, exist_ok=True)
os.makedirs(_templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=_static_dir), name="static")
templates = Jinja2Templates(directory=_templates_dir)



# ------------------------------------------------------------------
# Frontend
# ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
async def dashboard(request: Request):
    """Serve the premium dashboard."""
    return templates.TemplateResponse(request=request, name="index.html")


# ------------------------------------------------------------------
# Video Endpoints
# ------------------------------------------------------------------

@app.post("/api/upload", response_model=VideoUploadResponse, tags=["Video"])
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file and start background processing."""
    if not file.filename:
        raise HTTPException(400, "No file provided.")

    allowed_ext = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        raise HTTPException(400, f"Unsupported format: {ext}. Use: {allowed_ext}")

    # Save to temp file first, then move to INPUT_DIR
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    video_id, dest_path = VideoService.save_uploaded_video(file.filename, tmp_path)

    # Start async processing
    ProcessingService.enqueue_video(video_id, dest_path)

    return VideoUploadResponse(
        video_id=video_id,
        status="processing",
        message=f"Video '{file.filename}' uploaded. Processing started.",
    )


@app.get("/api/status/{video_id}", response_model=VideoStatusResponse, tags=["Video"])
async def get_video_status(video_id: int):
    """Get processing progress (0–100) for a video."""
    status = VideoService.get_video_status(video_id)
    if status.get("status") == "not_found":
        raise HTTPException(404, f"Video {video_id} not found.")

    # Merge in-memory progress from background thread
    task_progress = ProcessingService.get_progress(video_id)
    reported_progress = max(status.get("progress", 0), task_progress)

    return VideoStatusResponse(
        video_id=video_id,
        status=status["status"],
        progress=reported_progress,
    )


@app.get("/api/results/{video_id}", response_model=VideoResultsResponse, tags=["Video"])
async def get_video_results(video_id: int):
    """Get analytics summary for a completed video."""
    analytics = ReportService.generate_summary(video_id)
    if not analytics or analytics.get("total_vehicles", 0) == 0:
        record = VideoService.get_video_results(video_id)
        if record is None:
            raise HTTPException(404, f"Video {video_id} not found.")
        if record.get("status") != "completed":
            raise HTTPException(400, f"Video {video_id} is not yet completed (status: {record.get('status')}).")

    return VideoResultsResponse(
        video_id=video_id,
        total_vehicles=analytics.get("total_vehicles", 0),
        cars=analytics.get("cars", 0),
        trucks=analytics.get("trucks", 0),
        buses=analytics.get("buses", 0),
        bikes=analytics.get("bikes", 0),
        overspeed_count=analytics.get("overspeed_count", 0),
        overspeed_percentage=analytics.get("overspeed_percentage", 0.0),
        avg_speed=analytics.get("avg_speed", 0.0),
        max_speed=analytics.get("max_speed", 0.0),
        min_speed=analytics.get("min_speed", 0.0),
        vehicles_with_plates=analytics.get("vehicles_with_plates", 0),
    )


@app.get("/api/videos", response_model=List[VideoListItem], tags=["Video"])
async def list_videos():
    """List all uploaded/processed videos."""
    return [
        VideoListItem(**v) for v in VideoService.list_videos()
    ]


# ------------------------------------------------------------------
# Vehicle Endpoints
# ------------------------------------------------------------------

@app.get("/api/vehicles/{video_id}", response_model=List[VehicleResponse], tags=["Vehicles"])
async def get_vehicles(video_id: int):
    """List all vehicles detected in a video."""
    vehicles = VehicleService.get_vehicles(video_id)
    return [VehicleResponse(**v) for v in vehicles]


@app.get("/api/vehicle/{vehicle_id}", response_model=VehicleDetailResponse, tags=["Vehicles"])
async def get_vehicle_detail(vehicle_id: int):
    """Get detailed vehicle info including speed logs."""
    detail = VehicleService.get_vehicle_detail(vehicle_id)
    if detail is None:
        raise HTTPException(404, f"Vehicle {vehicle_id} not found.")
    return VehicleDetailResponse(**detail)


@app.get("/api/vehicles/{video_id}/overspeed", response_model=List[VehicleResponse], tags=["Vehicles"])
async def get_overspeeding_vehicles(video_id: int):
    """Get only overspeeding vehicles for a video."""
    vehicles = VehicleService.get_overspeeding_vehicles(video_id)
    return [VehicleResponse(**v) for v in vehicles]


# ------------------------------------------------------------------
# Download Endpoints
# ------------------------------------------------------------------

@app.get("/api/download/excel/{video_id}", tags=["Downloads"])
async def download_excel(video_id: int):
    """Download the Excel report for a video."""
    excel_path = ReportService.get_excel_path(video_id)
    if excel_path is None:
        # Try to generate on the fly
        try:
            excel_path = ReportService.generate_excel_report(video_id)
        except Exception as e:
            raise HTTPException(500, f"Failed to generate report: {e}")

    return FileResponse(
        path=excel_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(excel_path),
    )


@app.get("/api/download/video/{video_id}", tags=["Downloads"])
async def download_video(video_id: int):
    """Download the processed annotated video."""
    record = VideoService.get_video_results(video_id)
    if record is None:
        raise HTTPException(404, "Video not found.")

    video_path = record.get("processed_video_path")
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(404, "Processed video not available yet.")

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=os.path.basename(video_path),
    )


# ------------------------------------------------------------------
# Camera Endpoints
# ------------------------------------------------------------------

@app.post("/api/camera/start", response_model=APIResponse, tags=["Camera"])
async def start_camera(camera_source: str = Query(None)):
    """Start the live camera processing stream.
    
    Args:
        camera_source: Either a camera index ("0", "1") or a URL ("http://...", "rtsp://...")
    
    Example URLs for phone camera:
        - http://192.168.1.100:8080/video (IP Webcam app)
        - rtsp://192.168.1.100:554/stream (RTSP stream)
    """
    source = camera_source or "0"
    logger.info(f"Camera start requested with source: {source}")
    success = ProcessingService.start_camera_stream(source)
    if not success:
        return APIResponse(success=False, message="Camera stream is already running.")
    return APIResponse(success=True, message="Camera stream started.")


@app.post("/api/camera/stop", response_model=APIResponse, tags=["Camera"])
async def stop_camera():
    """Stop the live camera processing stream."""
    ProcessingService.stop_camera_stream()
    return APIResponse(success=True, message="Camera stream stopping.")


@app.get("/api/camera/stream", tags=["Camera"])
async def camera_stream():
    """MJPEG stream endpoint for the live camera feed."""
    def generate():
        import time
        frame_interval = 1.0 / settings.CAMERA_FPS
        while True:
            frame = ProcessingService.get_latest_camera_frame()
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            time.sleep(frame_interval)  # Use configured camera FPS

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/camera/frame", tags=["Camera"])
async def camera_frame():
    """Get latest single frame as JPEG (for polling)."""
    frame = ProcessingService.get_latest_camera_frame()
    if frame:
        return Response(content=frame, media_type="image/jpeg")
    else:
        return Response(content=b'', status_code=204)  # No content


@app.get("/api/camera/stats", tags=["Camera"])
async def camera_stats():
    """Get real-time stats from the active camera stream."""
    stats = ProcessingService.get_camera_stats()
    return APIResponse(
        success=True,
        message="Camera stats retrieved",
        data=stats,
    )


# ------------------------------------------------------------------
# Model Metrics Endpoint
# ------------------------------------------------------------------

@app.get("/api/model-metrics", tags=["System"])
async def model_metrics():
    """Return plate detector training metrics from results.csv."""
    import csv, os
    csv_path = "runs/detect/models/plate_detector/results.csv"
    if not os.path.exists(csv_path):
        return {"available": False}

    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k.strip(): v.strip() for k, v in row.items()})

    if not rows:
        return {"available": False}

    # Best epoch = highest mAP50
    best = max(rows, key=lambda r: float(r.get("metrics/mAP50(B)", 0)))
    last = rows[-1]

    def _f(row, key):
        try: return round(float(row[key]), 4)
        except: return 0.0

    # Per-epoch data for charts
    epochs = [int(r["epoch"]) for r in rows]

    return {
        "available": True,
        "best_epoch": int(best["epoch"]),
        "total_epochs": len(rows),
        "best": {
            "precision":  _f(best, "metrics/precision(B)"),
            "recall":     _f(best, "metrics/recall(B)"),
            "mAP50":      _f(best, "metrics/mAP50(B)"),
            "mAP50_95":   _f(best, "metrics/mAP50-95(B)"),
        },
        "last": {
            "precision":  _f(last, "metrics/precision(B)"),
            "recall":     _f(last, "metrics/recall(B)"),
            "mAP50":      _f(last, "metrics/mAP50(B)"),
            "mAP50_95":   _f(last, "metrics/mAP50-95(B)"),
        },
        "chart_data": {
            "epochs":     epochs,
            "box_loss":   [_f(r, "train/box_loss")         for r in rows],
            "cls_loss":   [_f(r, "train/cls_loss")         for r in rows],
            "val_loss":   [_f(r, "val/box_loss")           for r in rows],
            "precision":  [_f(r, "metrics/precision(B)")   for r in rows],
            "recall":     [_f(r, "metrics/recall(B)")      for r in rows],
            "mAP50":      [_f(r, "metrics/mAP50(B)")       for r in rows],
            "mAP50_95":   [_f(r, "metrics/mAP50-95(B)")    for r in rows],
        },
    }


# ------------------------------------------------------------------
# Health Check
# ------------------------------------------------------------------

@app.get("/api/health", tags=["System"])
async def health():
    return {"status": "ok", "version": "2.0.0"}
