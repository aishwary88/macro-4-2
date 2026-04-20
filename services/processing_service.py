"""
ProcessingService — orchestrates video processing lifecycle.
Bridges API layer → tasks.py → pipeline.py.
"""

import os
import threading
import time
from typing import Optional

from core.config import settings
from modules.data.database import init_db, update_video_status
from modules.utils.logger import get_logger

logger = get_logger(__name__)

# Camera stream state
_camera_active = False
_camera_lock = threading.Lock()
_camera_thread: Optional[threading.Thread] = None
_current_frame = None
_camera_stats = {
    "total_vehicles": 0,
    "avg_speed": 0.0,
    "overspeed_count": 0,
    "plates_detected": 0,
    "cars": 0,
    "trucks": 0,
    "buses": 0,
    "bikes": 0,
}


class ProcessingService:

    @staticmethod
    def enqueue_video(video_id: int, video_path: str) -> None:
        """Start async background processing for a video."""
        from tasks import start_processing
        init_db()
        start_processing(video_id, video_path)
        logger.info(f"Video {video_id} enqueued for processing.")

    @staticmethod
    def get_progress(video_id: int) -> int:
        """Get in-memory progress (0-100) for a video task."""
        from tasks import get_task_progress
        return get_task_progress(video_id)

    @staticmethod
    def start_camera_stream(camera_source = 0) -> bool:
        """Start processing the live camera stream in a background thread.
        
        Args:
            camera_source: Either int (camera index like 0) or str (URL like "http://...")
        """
        global _camera_active, _camera_thread

        with _camera_lock:
            if _camera_active:
                logger.warning("Camera stream already running.")
                return False
            _camera_active = True

        _camera_thread = threading.Thread(
            target=_run_camera_loop,
            args=(camera_source,),
            daemon=True,
            name="camera-stream",
        )
        _camera_thread.start()
        logger.info(f"Camera stream started (source={camera_source})")
        return True

    @staticmethod
    def stop_camera_stream() -> None:
        global _camera_active
        with _camera_lock:
            _camera_active = False
        logger.info("Camera stream stop requested.")

    @staticmethod
    def get_latest_camera_frame():
        """Return the latest JPEG-encoded frame from the camera stream."""
        return _current_frame

    @staticmethod
    def get_camera_stats() -> dict:
        """Return current camera stream stats."""
        with _camera_lock:
            return _camera_stats.copy()

    @staticmethod
    def _update_camera_stats(state_mgr) -> None:
        """Calculate and update camera stats from vehicle state manager."""
        global _camera_stats
        try:
            vehicles = state_mgr.vehicles
            if not vehicles:
                _camera_stats = {
                    "total_vehicles": 0,
                    "avg_speed": 0.0,
                    "overspeed_count": 0,
                    "plates_detected": 0,
                    "cars": 0,
                    "trucks": 0,
                    "buses": 0,
                    "bikes": 0,
                }
                return

            speeds = []
            overspeed_count = 0
            plates_detected = 0
            vehicle_types = {"Car": 0, "Truck": 0, "Bus": 0, "Bike": 0}

            for vid, vdata in vehicles.items():
                # Count speeds (access VehicleState object attributes, not dict keys)
                if vdata.speed is not None:
                    speeds.append(vdata.speed)
                    logger.debug(f"Vehicle {vid}: speed={vdata.speed} km/h, type={vdata.vehicle_type}, plate={vdata.plate}")
                    if vdata.speed > settings.SPEED_LIMIT_KMH:
                        overspeed_count += 1

                # Count plates (access VehicleState.plate attribute)
                if vdata.plate:
                    plates_detected += 1

                # Count vehicle types (access VehicleState.vehicle_type attribute)
                vehicle_type = vdata.vehicle_type or "Car"
                vehicle_types[vehicle_type] = vehicle_types.get(vehicle_type, 0) + 1

            avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

            with _camera_lock:
                _camera_stats = {
                    "total_vehicles": len(vehicles),
                    "avg_speed": round(avg_speed, 2),
                    "overspeed_count": overspeed_count,
                    "plates_detected": plates_detected,
                    "cars": vehicle_types.get("Car", 0),
                    "trucks": vehicle_types.get("Truck", 0),
                    "buses": vehicle_types.get("Bus", 0),
                    "bikes": vehicle_types.get("Bike", 0),
                }
                logger.debug(f"Camera stats updated: total={len(vehicles)}, speeds_calculated={len(speeds)}, avg_speed={avg_speed}, overspeed={overspeed_count}")
        except Exception as e:
            logger.error(f"Error updating camera stats: {e}", exc_info=True)


def _run_camera_loop(camera_source) -> None:
    """Background thread: captures frames from camera/URL, runs detection, updates _current_frame.
    
    Args:
        camera_source: Either int (camera index) or str (camera URL)
    """
    global _camera_active, _current_frame
    import cv2
    from modules.detection.detector import VehicleDetector
    from modules.tracking.tracker import VehicleTracker
    from modules.tracking.vehicle_state import VehicleStateManager
    from modules.classification.classifier import VehicleClassifier
    from modules.calibration.roi_manager import ROIManager
    from modules.visualization.renderer import FrameRenderer
    from modules.utils.geometry import bbox_center

    try:
        # Convert string to int if it's a numeric index
        if isinstance(camera_source, str) and camera_source.isdigit():
            camera_index = int(camera_source)
        else:
            camera_index = camera_source
        
        # For IP camera URLs, try to connect with proper MJPEG streaming options
        if isinstance(camera_index, str) and (camera_index.startswith("http") or camera_index.startswith("rtsp")):
            logger.info(f"Connecting to IP camera stream: {camera_index}")
            # Create VideoCapture with specific CAP_PROP options for IP streams
            cap = cv2.VideoCapture(camera_index)
            # Set buffer size to 1 to get latest frame (reduces lag)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            # Local camera device
            cap = cv2.VideoCapture(camera_index)
        
        if not cap.isOpened():
            source_str = f"'{camera_source}'" if isinstance(camera_source, str) else f"index {camera_source}"
            logger.error(f"Cannot open camera {source_str}. Make sure it's accessible and properly formatted.")
            logger.error(f"Verify: Phone camera is running, same WiFi network, correct IP and port in URL")
            _camera_active = False
            return

        detector = VehicleDetector(confidence_threshold=settings.DETECTION_CONFIDENCE)
        tracker = VehicleTracker()
        state_mgr = VehicleStateManager()
        classifier = VehicleClassifier()
        roi_mgr = ROIManager(
            line_a_y=settings.ROI_LINE_A_Y,
            line_b_y=settings.ROI_LINE_B_Y,
            known_distance=settings.ROI_DISTANCE_METERS,
        )
        renderer = FrameRenderer(debug=settings.DEBUG)

        frame_num = 0
        fps = cap.get(cv2.CAP_PROP_FPS) or settings.CAMERA_FPS
        frame_skip = settings.CAMERA_FRAME_SKIP
        frame_interval = 1.0 / settings.CAMERA_FPS  # Target frame interval in seconds
        last_process_time = time.time()
        last_stats_update = time.time()

        source_type = "URL" if isinstance(camera_source, str) and (camera_source.startswith("http") or camera_source.startswith("rtsp")) else "Device Index"
        logger.info(f"Camera loop started: Source={camera_source} ({source_type}), FPS={settings.CAMERA_FPS}, confidence_threshold={settings.DETECTION_CONFIDENCE}")

        while _camera_active:
            ret, frame = cap.read()
            if not ret:
                logger.warning("Camera read failed; retrying...")
                continue

            # Skip frames if configured
            if frame_skip > 0 and frame_num % (frame_skip + 1) != 0:
                frame_num += 1
                continue

            # Throttle to target FPS
            current_time = time.time()
            time_since_last = current_time - last_process_time
            if time_since_last < frame_interval:
                time.sleep(frame_interval - time_since_last)
            last_process_time = time.time()

            timestamp = frame_num / settings.CAMERA_FPS
            detections = detector.detect(frame)
            tracked = tracker.update(detections)

            if len(tracked) > 0:
                logger.debug(f"Frame {frame_num}: Detected {len(tracked)} vehicles")

            for v in tracked:
                center = bbox_center(v.bbox)
                state_mgr.update_position(v.vehicle_id, center, timestamp, v.bbox, v.confidence)
                state_mgr.set_vehicle_type(v.vehicle_id, classifier.classify(v.class_name))

            annotated = renderer.draw(frame, state_mgr, roi_manager=roi_mgr, frame_number=frame_num, video_fps=settings.CAMERA_FPS)

            _, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            with _camera_lock:
                _current_frame = buffer.tobytes()

            # Update stats every 0.5 seconds
            if current_time - last_stats_update >= 0.5:
                ProcessingService._update_camera_stats(state_mgr)
                last_stats_update = current_time

            frame_num += 1

        cap.release()
        logger.info("Camera stream stopped.")
    except Exception as e:
        logger.error(f"Error in camera loop: {e}", exc_info=True)
        _camera_active = False
