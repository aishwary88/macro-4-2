"""
ByteTrack-based vehicle tracker via the supervision library.
Maintains consistent vehicle IDs across frames.
"""

import numpy as np
import supervision as sv
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from modules.detection.detector import Detection
from modules.utils.geometry import bbox_center, bbox_bottom_center
from modules.utils.logger import get_logger
from core.constants import TRACK_HISTORY_LENGTH

logger = get_logger("tracking")


@dataclass
class TrackedVehicle:
    """Represents a tracked vehicle with consistent ID."""
    vehicle_id: int
    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    class_name: str
    confidence: float
    center: Tuple[float, float]
    bottom_center: Tuple[float, float]
    track_history: List[Tuple[float, float]] = field(default_factory=list)


class VehicleTracker:
    """ByteTrack-based multi-object tracker.

    Uses the supervision library's ByteTrack implementation for
    robust vehicle tracking with occlusion handling.
    """

    def __init__(
        self,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
        frame_rate: int = 30,
    ):
        """Initialize ByteTrack tracker.

        Args:
            track_activation_threshold: Confidence threshold for new tracks.
            lost_track_buffer: Frames to keep lost tracks before deletion.
            minimum_matching_threshold: IoU threshold for matching.
            frame_rate: Video frame rate.
        """
        self.tracker = sv.ByteTrack(
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
            frame_rate=frame_rate,
        )

        # Track history storage: {tracker_id: [(x, y), ...]}
        self._histories: dict = {}

        logger.info(
            f"VehicleTracker initialized (ByteTrack: "
            f"activation={track_activation_threshold}, "
            f"buffer={lost_track_buffer})"
        )

    def update(self, detections: List[Detection]) -> List[TrackedVehicle]:
        """Update tracker with new detections.

        Args:
            detections: List of Detection objects from the detector.

        Returns:
            List of TrackedVehicle objects with consistent IDs.
        """
        if not detections:
            return []

        # Convert to supervision Detections format
        bboxes = np.array([d.bbox for d in detections], dtype=np.float32)
        confidences = np.array([d.confidence for d in detections], dtype=np.float32)
        class_ids = np.array([d.class_id for d in detections], dtype=int)

        sv_detections = sv.Detections(
            xyxy=bboxes,
            confidence=confidences,
            class_id=class_ids,
        )

        # Run ByteTrack
        tracked = self.tracker.update_with_detections(sv_detections)

        # Build result list
        result = []

        if tracked.tracker_id is None:
            return result

        for i, tracker_id in enumerate(tracked.tracker_id):
            tracker_id = int(tracker_id)
            bbox = tuple(tracked.xyxy[i].tolist())
            confidence = float(tracked.confidence[i]) if tracked.confidence is not None else 0.0
            cls_id = int(tracked.class_id[i]) if tracked.class_id is not None else 0

            # Find matching class name from original detections
            class_name = "unknown"
            for det in detections:
                if det.class_id == cls_id:
                    class_name = det.class_name
                    break

            center = bbox_center(bbox)
            bottom = bbox_bottom_center(bbox)

            # Update track history
            if tracker_id not in self._histories:
                self._histories[tracker_id] = []

            self._histories[tracker_id].append(center)

            # Trim history to max length
            if len(self._histories[tracker_id]) > TRACK_HISTORY_LENGTH:
                self._histories[tracker_id] = self._histories[tracker_id][-TRACK_HISTORY_LENGTH:]

            result.append(TrackedVehicle(
                vehicle_id=tracker_id,
                bbox=bbox,
                class_name=class_name,
                confidence=confidence,
                center=center,
                bottom_center=bottom,
                track_history=list(self._histories[tracker_id]),
            ))

        logger.debug(f"Tracking {len(result)} vehicles")
        return result

    def get_history(self, vehicle_id: int) -> List[Tuple[float, float]]:
        """Get position history for a vehicle.

        Args:
            vehicle_id: Tracker ID.

        Returns:
            List of (x, y) positions.
        """
        return self._histories.get(vehicle_id, [])

    def reset(self):
        """Reset tracker state."""
        self.tracker.reset()
        self._histories.clear()
        logger.info("Tracker reset")
