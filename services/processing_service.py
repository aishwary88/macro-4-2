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
_camera_state_mgr = None   # live reference to state manager for vehicle table
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
    def get_camera_vehicles() -> list:
        """Return live per-vehicle data from the active camera stream."""
        global _camera_state_mgr
        if _camera_state_mgr is None:
            return []
        try:
            vehicles = []
            for vid, v in _camera_state_mgr.vehicles.items():
                avg_spd = round(
                    sum(v.speed_history) / len(v.speed_history), 1
                ) if v.speed_history else (v.speed or 0.0)
                vehicles.append({
                    "vehicle_unique_id": vid,
                    "vehicle_type":      v.vehicle_type or "Unknown",
                    "plate_number":      v.plate or "N/A",
                    "avg_speed":         avg_spd,
                    "max_speed":         round(v.max_speed, 1),
                    "status":            "overspeed" if v.overspeed else "normal",
                })
            # Sort by vehicle ID
            vehicles.sort(key=lambda x: x["vehicle_unique_id"])
            return vehicles
        except Exception as e:
            logger.error(f"Error getting camera vehicles: {e}")
            return []

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
    """Background thread: captures frames, runs full detection+tracking+speed pipeline."""
    global _camera_active, _current_frame, _camera_state_mgr
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

        # Phone/IP cameras: try FFMPEG backend first (better MJPEG support)
        if is_url:
            logger.info(f"Connecting to IP/phone camera: {camera_index}")
            cap = cv2.VideoCapture(camera_index, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            time.sleep(0.8)  # give FFMPEG time to connect
            if not cap.isOpened():
                cap.release()
                cap = cv2.VideoCapture(camera_index)  # fallback to default
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                time.sleep(0.5)
        else:
            cap = cv2.VideoCapture(camera_index)

        if not cap.isOpened():
            logger.error(
                f"Cannot open camera: '{camera_source}'. "
                f"Phone camera: ensure IP Webcam app is running, "
                f"same WiFi, correct URL (e.g. http://192.168.x.x:8080/video)"
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

        # Expose state manager globally for /api/camera/vehicles
        global _camera_state_mgr
        _camera_state_mgr = state_mgr

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

        frame_num = 0
        frame_interval = 1.0 / real_fps
        detect_every   = max(1, settings.DETECT_EVERY_N_FRAMES)
        last_process_time = time.time()
        last_stats_update = time.time()
        last_cleanup_time = time.time()
        last_annotated    = [None]   # keep last annotated frame for skipped frames

        # Compute processing resolution
        proc_w = settings.PROCESS_WIDTH
        if proc_w > 0 and frame_w > proc_w:
            cam_scale = proc_w / frame_w
            proc_h    = int(frame_h * cam_scale)
        else:
            cam_scale = 1.0
            proc_w    = frame_w
            proc_h    = frame_h

        # Re-set ROI lines for actual processing resolution
        line_a_y = int(proc_h * 0.35)
        line_b_y = int(proc_h * 0.65)
        roi_mgr.set_lines(line_a_y, line_b_y)
        roi_mgr.frame_width = proc_w
        calibrator.compute_pixels_per_meter(line_a_y, line_b_y, settings.ROI_DISTANCE_METERS)

        # ── Pixel-displacement speed estimator (primary for camera) ──
        from modules.speed.pixel_speed_estimator import PixelSpeedEstimator
        pixel_speed = PixelSpeedEstimator(fps=real_fps)

        # ANPR components for camera
        from modules.anpr.plate_detector import PlateDetector as _PD
        from modules.anpr.plate_reader import PlateReader as _PR
        plate_detector_cam = _PD()
        plate_reader_cam   = _PR()

        logger.info(
            f"Camera loop started: source={camera_source}, "
            f"input={frame_w}x{frame_h}, proc={proc_w}x{proc_h}, "
            f"fps={real_fps:.1f}, detect_every={detect_every}, "
            f"pixel_scale={settings.PIXEL_SCALE} m/px, "
            f"ROI A={line_a_y}px B={line_b_y}px"
        )

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

            # ── Frame skip ────────────────────────────────────────────
            frame_num += 1
            if frame_num % detect_every != 0:
                # Serve last annotated frame (with boxes) not raw frame
                if last_annotated[0] is not None:
                    with _camera_lock:
                        _current_frame = last_annotated[0]
                else:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    with _camera_lock:
                        _current_frame = buf.tobytes()
                continue

            timestamp = frame_num / real_fps

            # ── Resize for detection ──────────────────────────────────
            if cam_scale < 1.0:
                small = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_LINEAR)
            else:
                small = frame

            # ── Detection + Tracking ──────────────────────────────────
            detections  = detector.detect(small)
            tracked     = tracker.update(detections)
            current_ids = {v.vehicle_id for v in tracked}

            # ── Per-vehicle state update ──────────────────────────────
            for v in tracked:
                vid    = v.vehicle_id
                center = bbox_center(v.bbox)

                state_mgr.update_position(vid, center, timestamp, v.bbox, v.confidence)
                state_mgr.set_vehicle_type(vid, classifier.classify(v.class_name))

                # ── Speed: pixel-displacement (primary, always runs) ──
                px_speed = pixel_speed.update(vid, center, frame_num)
                if px_speed is not None:
                    state_mgr.set_speed(vid, px_speed)

                # ── Speed: ROI line-crossing (secondary, more accurate
                #    when vehicle crosses both lines) ──────────────────
                prev_pos = state_mgr.get_previous_position(vid)
                if prev_pos is not None:
                    speed_data = speed_estimator.update(vid, prev_pos, center, timestamp)
                    if speed_data and speed_data.speed_kmh is not None:
                        # ROI result overrides pixel speed (more accurate)
                        state_mgr.set_speed(vid, speed_data.speed_kmh)
                        # Reset pixel smoother so it doesn't drag down the ROI value
                        pixel_speed._state.pop(vid, None)

                # ANPR — throttled per vehicle
                vstate = state_mgr.get_vehicle(vid)
                if (
                    vstate is not None
                    and vstate.frame_count >= 5
                    and vstate.plate_confidence < 0.85
                    and frame_num % settings.OCR_EVERY_N_FRAMES == 0
                ):
                    # Crop from original frame for best quality
                    if cam_scale < 1.0:
                        x1 = int(v.bbox[0] / cam_scale); y1 = int(v.bbox[1] / cam_scale)
                        x2 = int(v.bbox[2] / cam_scale); y2 = int(v.bbox[3] / cam_scale)
                    else:
                        x1, y1, x2, y2 = [int(c) for c in v.bbox]
                    fh, fw = frame.shape[:2]
                    crop = frame[max(0,y1):min(fh,y2), max(0,x1):min(fw,x2)]
                    if crop.size > 0:
                        plate_img = plate_detector_cam.detect(crop)
                        if plate_img is not None:
                            plate_data = plate_reader_cam.read_plate(plate_img)
                            if plate_data:
                                state_mgr.set_plate(vid, plate_data.plate_number, plate_data.confidence)

            # ── Cleanup stale tracks every 2 seconds ──────────────────
            if now - last_cleanup_time >= 2.0:
                state_mgr.cleanup_stale(
                    max_age_frames=settings.MAX_TRACK_AGE,
                    current_vehicle_ids=current_ids,
                )
                # Also clean pixel speed state for removed vehicles
                active_ids = set(state_mgr.vehicles.keys())
                for vid in list(pixel_speed._state.keys()):
                    if vid not in active_ids:
                        pixel_speed.remove(vid)
                last_cleanup_time = now

            # ── Clear stale bboxes for vehicles not in current frame ──
            # This prevents boxes "sticking" on vehicles that left the frame
            for vid, vstate in state_mgr.vehicles.items():
                if vid not in current_ids:
                    vstate.current_bbox = None

            # ── Render on original frame ──────────────────────────────
            # ROI lines are in proc-space — scale them to original frame size
            # bbox_scale converts proc-space coords → original frame coords
            render_scale = 1.0 / cam_scale if cam_scale < 1.0 else 1.0

            # Temporarily scale ROI line positions for rendering
            orig_line_a = roi_mgr.line_a_y
            orig_line_b = roi_mgr.line_b_y
            roi_mgr.line_a_y = int(orig_line_a * render_scale)
            roi_mgr.line_b_y = int(orig_line_b * render_scale)

            annotated = renderer.draw(
                frame, state_mgr,
                roi_manager=roi_mgr,
                frame_number=frame_num,
                video_fps=real_fps,
                bbox_scale=render_scale,
            )

            # Restore ROI line positions
            roi_mgr.line_a_y = orig_line_a
            roi_mgr.line_b_y = orig_line_b

            _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            buf_bytes = buf.tobytes()
            last_annotated[0] = buf_bytes   # save for skipped frames
            with _camera_lock:
                _current_frame = buf_bytes

            # ── Update stats every 0.5 s ──────────────────────────────
            if now - last_stats_update >= 0.5:
                ProcessingService._update_camera_stats(state_mgr)
                last_stats_update = now

        # ── Cleanup ───────────────────────────────────────────────────
        _reader_active[0] = False
        reader.join(timeout=2.0)
        cap.release()
        _camera_state_mgr = None
        logger.info("Camera stream stopped.")

    except Exception as e:
        logger.error(f"Camera loop error: {e}", exc_info=True)
        _camera_active = False
