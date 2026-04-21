"""
TrafficPipeline — Main orchestration engine.
Ties together: detection → tracking → classification → speed → ANPR → rendering.
"""

import os
import time
import cv2
from typing import Optional
from datetime import datetime

from core.config import settings
from modules.detection.detector import VehicleDetector
from modules.tracking.tracker import VehicleTracker
from modules.tracking.vehicle_state import VehicleStateManager
from modules.calibration.roi_manager import ROIManager
from modules.calibration.calibrator import Calibrator
from modules.speed.speed_estimator import SpeedEstimator
from modules.anpr.plate_reader import PlateReader
from modules.anpr.plate_detector import PlateDetector
from modules.classification.classifier import VehicleClassifier
from modules.visualization.renderer import FrameRenderer
from modules.utils.video_utils import get_video_info, extract_frames, create_video_writer
from modules.utils.geometry import bbox_center
from modules.data.database import save_vehicles, update_video_status, init_db
from modules.data.excel_report import generate_excel_report
from modules.utils.logger import get_logger

logger = get_logger(__name__)


class TrafficPipeline:
    """
    Full-stack traffic analysis pipeline.
    Usage:
        pipeline = TrafficPipeline()
        pipeline.process_video(video_path, video_id, progress_callback)
    """

    def __init__(self):
        logger.info("Initializing TrafficPipeline...")

        self.detector = VehicleDetector(
            confidence_threshold=settings.DETECTION_CONFIDENCE,
        )
        self.tracker = VehicleTracker()
        self.state_manager = VehicleStateManager()
        self.classifier = VehicleClassifier()

        self.roi_manager = ROIManager(
            line_a_y=settings.ROI_LINE_A_Y,
            line_b_y=settings.ROI_LINE_B_Y,
            known_distance=settings.ROI_DISTANCE_METERS,
        )
        self.calibrator = Calibrator()
        self.speed_estimator = SpeedEstimator(
            roi_manager=self.roi_manager,
            calibrator=self.calibrator,
            state_manager=self.state_manager,
        )

        self.plate_detector = PlateDetector()
        self.plate_reader = PlateReader()

        self.renderer = FrameRenderer(debug=settings.DEBUG)

        logger.info("TrafficPipeline ready ✓")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_video(
        self,
        video_path: str,
        video_id: int,
        progress_callback=None,
    ) -> str:
        """
        Process a video file end-to-end.

        Args:
            video_path: Path to the input video.
            video_id: DB record ID for status updates.
            progress_callback: Optional callable(progress: int) invoked each frame batch.

        Returns:
            Path to the output annotated video.
        """
        logger.info(f"Starting pipeline for video_id={video_id}: {video_path}")

        # Reset state for fresh run
        self.state_manager.reset()
        self.roi_manager.reset()

        # Get video info
        info = get_video_info(video_path)
        fps = info.fps
        width = info.width
        height = info.height
        total_frames = info.total_frames

        # ── Compute processing resolution ─────────────────────────────
        proc_w = settings.PROCESS_WIDTH
        if proc_w > 0 and width > proc_w:
            scale    = proc_w / width
            proc_h   = int(height * scale)
        else:
            scale    = 1.0
            proc_w   = width
            proc_h   = height

        detect_every = max(1, settings.DETECT_EVERY_N_FRAMES)
        logger.info(
            f"Pipeline config: detect_every={detect_every} frames, "
            f"proc_size={proc_w}x{proc_h} (scale={scale:.2f}), "
            f"ocr_interval={settings.OCR_EVERY_N_FRAMES}"
        )

        # Update ROI line positions based on PROCESSING height (not original)
        self.roi_manager.set_lines(
            line_a_y=int(proc_h * 0.35),
            line_b_y=int(proc_h * 0.65),
        )
        self.roi_manager.frame_width = proc_w

        # Setup output video
        os.makedirs(settings.OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(
            settings.OUTPUT_DIR, f"processed_{video_id}_{os.path.basename(video_path)}"
        )
        writer = create_video_writer(out_path, fps, (width, height))

        frame_num = 0
        update_video_status(video_id, "processing", progress=0)

        try:
            for frame_obj in extract_frames(video_path):
                frame_num = frame_obj.frame_id
                timestamp = frame_obj.timestamp

                # ── Frame skip: only process every N frames ───────────
                # Still write every frame to output video for smooth playback
                if frame_num % detect_every != 0:
                    # Write original frame (no annotation) to keep video smooth
                    writer.write(frame_obj.image)
                    continue

                frame = frame_obj.image

                # ── Resize for faster processing ──────────────────────
                if scale < 1.0:
                    small = cv2.resize(frame, (proc_w, proc_h), interpolation=cv2.INTER_LINEAR)
                else:
                    small = frame

                # ── Detection ──────────────────────────────────────────
                detections = self.detector.detect(small)

                # ── Tracking ───────────────────────────────────────────
                tracked_vehicles = self.tracker.update(detections)
                current_ids = {v.vehicle_id for v in tracked_vehicles}

                # ── Per-vehicle processing ─────────────────────────────
                for vehicle in tracked_vehicles:
                    vid    = vehicle.vehicle_id
                    center = bbox_center(vehicle.bbox)

                    # Update state (positions in proc-space coords)
                    self.state_manager.update_position(
                        vid, center, timestamp, vehicle.bbox, vehicle.confidence
                    )

                    # Classification
                    vehicle_type = self.classifier.classify(vehicle.class_name)
                    self.state_manager.set_vehicle_type(vid, vehicle_type)

                    # Speed estimation via ROI line crossing
                    prev_pos = self.state_manager.get_previous_position(vid)
                    if prev_pos is not None:
                        speed_data = self.speed_estimator.update(
                            vid, prev_pos, center, timestamp
                        )
                        if speed_data and speed_data.speed_kmh is not None:
                            self.state_manager.set_speed(vid, speed_data.speed_kmh)

                    # ANPR — throttled: only on stable frames, every OCR_EVERY_N_FRAMES
                    state = self.state_manager.get_vehicle(vid)
                    if (
                        state is not None
                        and state.frame_count >= 5
                        and state.plate_confidence < 0.85
                        and frame_num % settings.OCR_EVERY_N_FRAMES == 0
                    ):
                        # Crop from ORIGINAL frame for best OCR quality
                        if scale < 1.0:
                            x1 = int(vehicle.bbox[0] / scale)
                            y1 = int(vehicle.bbox[1] / scale)
                            x2 = int(vehicle.bbox[2] / scale)
                            y2 = int(vehicle.bbox[3] / scale)
                        else:
                            x1, y1, x2, y2 = [int(c) for c in vehicle.bbox]

                        h_orig, w_orig = frame.shape[:2]
                        x1 = max(0, x1); y1 = max(0, y1)
                        x2 = min(w_orig, x2); y2 = min(h_orig, y2)
                        vehicle_crop = frame[y1:y2, x1:x2]

                        if vehicle_crop.size > 0:
                            plate_img = self.plate_detector.detect(vehicle_crop)
                            if plate_img is not None:
                                plate_data = self.plate_reader.read_plate(plate_img)
                                if plate_data:
                                    self.state_manager.set_plate(
                                        vid, plate_data.plate_number, plate_data.confidence
                                    )

                # Cleanup stale tracks
                self.state_manager.cleanup_stale(
                    max_age_frames=999999,
                    current_vehicle_ids=current_ids,
                )

                # ── Render on original-size frame ──────────────────────
                # Scale bboxes back to original resolution for rendering
                if scale < 1.0:
                    annotated = self.renderer.draw(
                        frame,
                        self.state_manager,
                        roi_manager=self.roi_manager,
                        frame_number=frame_num,
                        video_fps=fps,
                        bbox_scale=1.0 / scale,
                    )
                else:
                    annotated = self.renderer.draw(
                        frame,
                        self.state_manager,
                        roi_manager=self.roi_manager,
                        frame_number=frame_num,
                        video_fps=fps,
                    )
                writer.write(annotated)

                # Progress update
                if total_frames > 0 and frame_num % 30 == 0:
                    progress = min(int(frame_num / total_frames * 100), 99)
                    update_video_status(video_id, "processing", progress=progress)
                    if progress_callback:
                        progress_callback(progress)

        except Exception as exc:
            logger.error(f"Pipeline error at frame {frame_num}: {exc}", exc_info=True)
            update_video_status(video_id, "failed", error_message=str(exc))
            raise
        finally:
            writer.release()

        # ── Post-processing: save to DB ──
        self._save_results(video_id, video_path, out_path, fps, total_frames)

        logger.info(f"Pipeline complete for video_id={video_id} → {out_path}")
        return out_path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _save_results(
        self,
        video_id: int,
        input_path: str,
        output_path: str,
        fps: float,
        total_frames: int,
    ) -> None:
        """Persist vehicle data to DB, then generate Excel from that same DB data.

        Single source of truth: state_manager → DB → Excel + API.
        """
        from modules.data.analytics import compute_analytics
        from modules.data.database import delete_vehicles_for_video

        # ── Fallback speed for vehicles that never crossed both ROI lines ──
        self._estimate_fallback_speeds(fps)

        df = self.state_manager.export_to_dataframe()
        duration = total_frames / fps if fps > 0 else 0

        # ── STEP 1: Save to DB (delete first to prevent duplicates on re-run) ──
        delete_vehicles_for_video(video_id)
        vehicle_records = df.to_dict(orient="records") if not df.empty else []
        save_vehicles(video_id, vehicle_records)
        logger.info(f"Saved {len(vehicle_records)} vehicles to DB for video {video_id}")

        # ── STEP 2: Update video status so DB is complete before Excel ──
        total = len(vehicle_records)
        update_video_status(
            video_id,
            "completed",
            progress=100,
            total_vehicles=total,
            duration=duration,
            fps=fps,
            processed_video_path=output_path,
        )

        # ── STEP 3: Generate Excel FROM DB (same data the API serves) ──
        from modules.data.database import get_vehicles_by_video
        import pandas as pd

        db_vehicles = get_vehicles_by_video(video_id)
        analytics   = compute_analytics(video_id)   # reads from DB

        # Build DataFrame from DB records (canonical format)
        df_excel = pd.DataFrame([
            {
                "vehicle_id":   v["vehicle_unique_id"],
                "vehicle_type": v["vehicle_type"],
                "plate_number": v["plate_number"],
                "avg_speed":    v["avg_speed"],
                "max_speed":    v["max_speed"],
                "overspeed":    v["overspeed_flag"],
                "overspeed_flag": v["overspeed_flag"],
                "first_seen":   str(v.get("first_seen_time") or ""),
                "last_seen":    str(v.get("last_seen_time") or ""),
                "frame_count":  v.get("frame_count", 0),
            }
            for v in db_vehicles
        ])

        excel_path = os.path.join(
            settings.OUTPUT_DIR, f"report_video_{video_id}.xlsx"
        )
        generate_excel_report(
            vehicle_df=df_excel,
            analytics=analytics,
            output_path=excel_path,
            video_filename=os.path.basename(input_path),
        )

        # ── STEP 4: Persist Excel path to DB ──
        update_video_status(video_id, "completed", excel_path=excel_path)

        logger.info(
            f"Results saved: {total} vehicles | "
            f"mAP avg_speed={analytics.get('avg_speed',0):.1f} km/h | "
            f"excel={excel_path}"
        )

    def _estimate_fallback_speeds(self, fps: float) -> None:
        """For vehicles that never crossed both ROI lines, estimate speed from
        pixel displacement across their tracked positions.

        This ensures vehicles that enter/exit from the sides or are only
        partially in frame still get a meaningful speed estimate.

        Args:
            fps: Video frames per second.
        """
        if fps <= 0:
            return

        # pixels per meter from calibrator
        ppm = self.calibrator.pixels_per_meter
        if ppm <= 0:
            return

        for vid, state in self.state_manager.vehicles.items():
            # Only apply fallback if no speed was measured via ROI
            if state.speed_history:
                continue

            # Need at least 2 position samples
            if len(state.positions) < 2:
                continue

            # Calculate total pixel displacement over all tracked positions
            total_px = 0.0
            for i in range(1, len(state.positions)):
                x0, y0, _ = state.positions[i - 1]
                x1, y1, _ = state.positions[i]
                total_px += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5

            # Time span from first to last position
            t_start = state.positions[0][2]
            t_end = state.positions[-1][2]
            time_span = t_end - t_start

            if time_span <= 0:
                continue

            # Convert to real-world speed
            total_meters = total_px / ppm
            speed_mps = total_meters / time_span
            speed_kmh = round(speed_mps * 3.6, 2)

            # Sanity cap
            if speed_kmh > 300:
                speed_kmh = 300.0
            if speed_kmh < 0:
                speed_kmh = 0.0

            self.state_manager.set_speed(vid, speed_kmh)
            logger.debug(
                f"Fallback speed for vehicle {vid}: {speed_kmh:.1f} km/h "
                f"(px={total_px:.0f}, m={total_meters:.1f}, t={time_span:.2f}s)"
            )
