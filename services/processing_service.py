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
        """Calculate and update camera stats from vehicle state manager.
        
        Shows stats for currently visible vehicles only (those with a current bbox).
        """
        global _camera_stats
        try:
            # Only count vehicles currently visible in the frame
            active_vehicles = {
                vid: v for vid, v in state_mgr.vehicles.items()
                if v.current_bbox is not None
            }
            all_vehicles = state_mgr.vehicles

            speeds = []
            overspeed_count = 0
            plates_detected = 0
            vehicle_types = {"Car": 0, "Truck": 0, "Bus": 0, "Bike": 0}

            for vid, vdata in all_vehicles.items():
                # Use full speed_history for a stable average
                if vdata.speed_history:
                    avg = sum(vdata.speed_history) / len(vdata.speed_history)
                    speeds.append(avg)
                    if vdata.overspeed:
                        overspeed_count += 1
                elif vdata.speed is not None:
                    speeds.append(vdata.speed)
                    if vdata.overspeed:
                        overspeed_count += 1

                if vdata.plate:
                    plates_detected += 1

                vtype = vdata.vehicle_type or "Car"
                vehicle_types[vtype] = vehicle_types.get(vtype, 0) + 1

            avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0

            with _camera_lock:
                _camera_stats = {
                    "total_vehicles": len(all_vehicles),
                    "active_vehicles": len(active_vehicles),
                    "avg_speed": avg_speed,
                    "overspeed_count": overspeed_count,
                    "plates_detected": plates_detected,
                    "cars": vehicle_types.get("Car", 0),
                    "trucks": vehicle_types.get("Truck", 0),
                    "buses": vehicle_types.get("Bus", 0),
                    "bikes": vehicle_types.get("Bike", 0),
                }
        except Exception as e:
            logger.error(f"Error updating camera stats: {e}", exc_info=True)


def _run_camera_loop(camera_source) -> None:
    """Background thread: captures frames, runs full detection+tracking+speed pipeline.

    Args:
        camera_source: Either int (camera index) or str (camera URL)
    """
    global _camera_active, _current_frame
    import cv2
    import threading as _threading
    from modules.detection.detector import VehicleDetector
    from modules.tracking.tracker import VehicleTracker
    from modules.tracking.vehicle_state import VehicleStateManager
    from modules.classification.classifier import VehicleClassifier
    from modules.calibration.roi_manager import ROIManager
    from modules.calibration.calibrator import Calibrator
    from modules.speed.speed_estimator import SpeedEstimator
    from modules.visualization.renderer import FrameRenderer
    from modules.utils.geometry import bbox_center, bbox_bottom_center

    try:
        # ── Open capture ──────────────────────────────────────────────
        if isinstance(camera_source, str) and camera_source.isdigit():
            camera_index = int(camera_source)
        else:
            camera_index = camera_source

        is_url = isinstance(camera_index, str) and (
            camera_index.startswith("http") or camera_index.startswith("rtsp")
        )

        cap = cv2.VideoCapture(camera_index)
        if is_url:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            logger.error(
                f"Cannot open camera source: '{camera_source}'. "
                f"Check that the camera is connected / URL is reachable."
            )
            _camera_active = False
            return

        # ── Detect real FPS from capture ──────────────────────────────
        real_fps = cap.get(cv2.CAP_PROP_FPS)
        if not real_fps or real_fps <= 0 or real_fps > 120:
            real_fps = 30.0   # safe default for webcams and phone streams
        logger.info(f"Camera FPS detected: {real_fps:.1f}")

        # ── Frame dimensions ──────────────────────────────────────────
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

        # ── Thread-safe frame buffer ──────────────────────────────────
        _frame_lock = _threading.Lock()
        _latest_frame = [None]
        _reader_active = [True]

        def _reader_thread():
            while _reader_active[0] and _camera_active:
                ret, frm = cap.read()
                if ret and frm is not None:
                    with _frame_lock:
                        _latest_frame[0] = frm
                else:
                    time.sleep(0.01)

        reader = _threading.Thread(target=_reader_thread, daemon=True, name="cam-reader")
        reader.start()

        # ── Pipeline components ───────────────────────────────────────
        detector  = VehicleDetector(confidence_threshold=settings.DETECTION_CONFIDENCE)
        tracker   = VehicleTracker(frame_rate=int(real_fps))
        state_mgr = VehicleStateManager()
        classifier = VehicleClassifier()

        # ROI lines at 35% and 65% of frame height (same as video pipeline)
        line_a_y = int(frame_h * 0.35)
        line_b_y = int(frame_h * 0.65)
        roi_mgr = ROIManager(
            line_a_y=line_a_y,
            line_b_y=line_b_y,
            known_distance=settings.ROI_DISTANCE_METERS,
        )
        roi_mgr.frame_width = frame_w

        calibrator = Calibrator()
        calibrator.compute_pixels_per_meter(line_a_y, line_b_y, settings.ROI_DISTANCE_METERS)

        speed_estimator = SpeedEstimator(
            roi_manager=roi_mgr,
            calibrator=calibrator,
            state_manager=state_mgr,
        )

        renderer = FrameRenderer(debug=settings.DEBUG)

        logger.info(
            f"Camera loop started: source={camera_source}, "
            f"size={frame_w}x{frame_h}, fps={real_fps:.1f}, "
            f"ROI lines: A={line_a_y}px B={line_b_y}px, "
            f"distance={settings.ROI_DISTANCE_METERS}m"
        )

        frame_num = 0
        frame_interval = 1.0 / real_fps
        last_process_time = time.time()
        last_stats_update = time.time()
        last_cleanup_time = time.time()

        # Wait for first frame
        for _ in range(50):
            with _frame_lock:
                if _latest_frame[0] is not None:
                    break
            time.sleep(0.05)

        while _camera_active:
            # ── Throttle to real FPS ──────────────────────────────────
            now = time.time()
            elapsed = now - last_process_time
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
            last_process_time = time.time()

            # ── Grab latest frame ─────────────────────────────────────
            with _frame_lock:
                frame = _latest_frame[0]
            if frame is None:
                continue
            frame = frame.copy()

            # ── Timestamp based on real wall-clock time ───────────────
            timestamp = frame_num / real_fps

            # ── Detection + Tracking ──────────────────────────────────
            detections = detector.detect(frame)
            tracked    = tracker.update(detections)
            current_ids = {v.vehicle_id for v in tracked}

            # ── Per-vehicle state update ──────────────────────────────
            for v in tracked:
                vid    = v.vehicle_id
                center = bbox_center(v.bbox)
                bottom = bbox_bottom_center(v.bbox)

                state_mgr.update_position(vid, center, timestamp, v.bbox, v.confidence)
                state_mgr.set_vehicle_type(vid, classifier.classify(v.class_name))

                # Speed via ROI line crossing (uses bottom-center for accuracy)
                prev_pos = state_mgr.get_previous_position(vid)
                if prev_pos is not None:
                    speed_data = speed_estimator.update(vid, prev_pos, center, timestamp)
                    if speed_data and speed_data.speed_kmh is not None:
                        state_mgr.set_speed(vid, speed_data.speed_kmh)

            # ── Cleanup stale tracks every 2 seconds ──────────────────
            if now - last_cleanup_time >= 2.0:
                state_mgr.cleanup_stale(
                    max_age_frames=settings.MAX_TRACK_AGE,
                    current_vehicle_ids=current_ids,
                )
                last_cleanup_time = now

            # ── Render annotated frame ────────────────────────────────
            annotated = renderer.draw(
                frame, state_mgr,
                roi_manager=roi_mgr,
                frame_number=frame_num,
                video_fps=real_fps,
            )

            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            with _camera_lock:
                _current_frame = buf.tobytes()

            # ── Update stats every 0.5 s ──────────────────────────────
            if now - last_stats_update >= 0.5:
                ProcessingService._update_camera_stats(state_mgr)
                last_stats_update = now

            frame_num += 1

        # ── Cleanup ───────────────────────────────────────────────────
        _reader_active[0] = False
        reader.join(timeout=2.0)
        cap.release()
        logger.info("Camera stream stopped.")

    except Exception as e:
        logger.error(f"Camera loop error: {e}", exc_info=True)
        _camera_active = False
