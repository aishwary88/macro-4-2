"""
YOLOv8 vehicle detection module.
Detects vehicles in video frames and returns structured detection data.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple
from core.constants import VEHICLE_CLASS_IDS, MIN_DETECTION_AREA
from modules.utils.logger import get_logger
from modules.utils.geometry import bbox_area

logger = get_logger("detection")


@dataclass
class Detection:
    """Represents a single vehicle detection."""
    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    confidence: float
    class_id: int
    class_name: str


class VehicleDetector:
    """YOLOv8-based vehicle detector.

    Filters detections to only include vehicle classes with
    confidence above threshold.
    """

    def __init__(self, model=None, confidence_threshold: float = 0.5):
        """Initialize detector.

        Args:
            model: Pre-loaded YOLO model (from dependencies.py).
            confidence_threshold: Minimum confidence for detections.
        """
        if model is None:
            from core.dependencies import get_yolo_model
            model = get_yolo_model()

        self.model = model
        self.confidence_threshold = confidence_threshold
        self._class_names = model.names if hasattr(model, 'names') else {}

        logger.info(f"VehicleDetector initialized (confidence >= {confidence_threshold})")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run detection on a single frame.

        Args:
            frame: BGR image as numpy array.

        Returns:
            List of Detection objects for vehicles only.
        """
        results = self.model(frame, verbose=False)
        detections = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                cls_id = int(box.cls[0])
                confidence = float(box.conf[0])

                # Filter: vehicle classes only
                if cls_id not in VEHICLE_CLASS_IDS:
                    continue

                # Filter: confidence threshold
                if confidence < self.confidence_threshold:
                    continue

                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                bbox = (float(x1), float(y1), float(x2), float(y2))

                # Filter: minimum area
                if bbox_area(bbox) < MIN_DETECTION_AREA:
                    continue

                class_name = VEHICLE_CLASS_IDS.get(cls_id, "unknown")

                detections.append(Detection(
                    bbox=bbox,
                    confidence=confidence,
                    class_id=cls_id,
                    class_name=class_name,
                ))

        logger.debug(f"Detected {len(detections)} vehicles in frame")
        return detections

    def detect_batch(self, frames: List[np.ndarray]) -> List[List[Detection]]:
        """Run detection on multiple frames.

        Args:
            frames: List of BGR images.

        Returns:
            List of detection lists, one per frame.
        """
        all_detections = []
        for frame in frames:
            all_detections.append(self.detect(frame))
        return all_detections
