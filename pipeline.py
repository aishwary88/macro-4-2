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

        # Update ROI line positions based on real frame height
        self.roi_manager.set_lines(
            line_a_y=int(height * 0.35),
            line_b_y=int(height * 0.65),
        )
        self.roi_manager.frame_width = width

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
                frame = frame_obj.image
                timestamp = frame_obj.timestamp
                
                # ── Detection ──
                detections = self.detector.detect(frame)

                # ── Tracking ──
                tracked_vehicles = self.tracker.update(detections)
                current_ids = {v.vehicle_id for v in tracked_vehicles}

                # ── Per-vehicle processing ──
                for vehicle in tracked_vehicles:
                    vid = vehicle.vehicle_id
                    center = bbox_center(vehicle.bbox)

                    # Update state
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

                    # ANPR (throttled, only on stable frames)
                    if self.state_manager.is_good_frame_for_ocr(vid):
                        # Crop vehicle region
                        x1, y1, x2, y2 = vehicle.bbox
                        vehicle_crop = frame[int(y1):int(y2), int(x1):int(x2)]
                        plate_img = self.plate_detector.detect(vehicle_crop)
                        if plate_img is not None:
                            plate_data = self.plate_reader.read_plate(plate_img)
                            if plate_data:
                                self.state_manager.set_plate(
                                    vid, plate_data.plate_number, plate_data.confidence
                                )

                # Cleanup stale tracks — use large age so vehicles aren't lost before _save_results
                self.state_manager.cleanup_stale(
                    max_age_frames=999999,  # video: keep all tracks until end
                    current_vehicle_ids=current_ids,
                )

                # ── Render ──
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
        """Persist vehicle data to DB and generate Excel report."""
        import pandas as pd
        from modules.data.analytics import compute_analytics_from_state

        # ── Fallback speed for vehicles that never crossed both ROI lines ──
        self._estimate_fallback_speeds(fps)

        df = self.state_manager.export_to_dataframe()
        duration = total_frames / fps if fps > 0 else 0

        # Build vehicle records list — convert datetime fields to strings for Excel
        if not df.empty:
            df_excel = df.copy()
            for col in ("first_seen", "last_seen"):
                if col in df_excel.columns:
                    df_excel[col] = df_excel[col].apply(
                        lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime") else (str(v) if v else "")
                    )
        else:
            df_excel = df

        vehicle_records = df.to_dict(orient="records") if not df.empty else []
        save_vehicles(video_id, vehicle_records)

        # Generate Excel
        analytics = compute_analytics_from_state(self.state_manager)
        excel_path = os.path.join(
            settings.OUTPUT_DIR, f"report_video_{video_id}.xlsx"
        )
        generate_excel_report(
            vehicle_df=df_excel,
            analytics=analytics,
            output_path=excel_path,
            video_filename=os.path.basename(input_path),
        )

        # Final DB status
        total = len(self.state_manager.vehicles)
        update_video_status(
            video_id,
            "completed",
            progress=100,
            total_vehicles=total,
            duration=duration,
            fps=fps,
            processed_video_path=output_path,
            excel_path=excel_path,
        )
        logger.info(
            f"Results saved: {total} vehicles, excel={excel_path}"
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
