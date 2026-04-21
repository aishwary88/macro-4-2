"""
License plate detection: locates plate regions within vehicle bounding boxes.

Primary:  trained YOLOv8 plate_detector.pt model (high accuracy)
Fallback: contour-based detection (when model not available)
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional
from modules.utils.logger import get_logger

logger = get_logger("plate_detector")

# Path to trained plate detector — use it if available
_PLATE_MODEL_PATH = Path("models/plate_detector.pt")
# Also check the training output directly
_PLATE_MODEL_ALT  = Path("runs/detect/models/plate_detector/weights/best.pt")


class PlateDetector:
    """Detects license plate regions within vehicle images.

    Uses trained YOLOv8 model when available, falls back to
    contour-based detection otherwise.
    """

    def __init__(
        self,
        min_area: int = 800,
        max_area: int = 80000,
        min_aspect: float = 1.5,
        max_aspect: float = 6.5,
        model_conf: float = 0.35,
    ):
        self.min_area   = min_area
        self.max_area   = max_area
        self.min_aspect = min_aspect
        self.max_aspect = max_aspect
        self.model_conf = model_conf
        self._model     = None
        self._use_model = False

        # Try to load trained plate model
        for model_path in [_PLATE_MODEL_PATH, _PLATE_MODEL_ALT]:
            if model_path.exists():
                try:
                    from ultralytics import YOLO
                    self._model     = YOLO(str(model_path))
                    self._use_model = True
                    logger.info(f"PlateDetector: using trained model → {model_path}")
                    break
                except Exception as e:
                    logger.warning(f"Could not load plate model {model_path}: {e}")

        if not self._use_model:
            logger.info("PlateDetector: using contour-based fallback")

    # ------------------------------------------------------------------
    def detect(self, vehicle_image: np.ndarray) -> Optional[np.ndarray]:
        """Detect and crop the license plate from a vehicle image.

        Args:
            vehicle_image: Cropped vehicle region (BGR).

        Returns:
            Cropped plate image (BGR) or None.
        """
        if vehicle_image is None or vehicle_image.size == 0:
            return None

        if self._use_model:
            result = self._detect_with_model(vehicle_image)
            if result is not None:
                return result
            # Fall through to contour if model finds nothing

        return self._detect_with_contours(vehicle_image)

    # ------------------------------------------------------------------
    def _detect_with_model(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Use trained YOLO model to find plate bbox."""
        try:
            results = self._model(image, conf=self.model_conf, verbose=False)
            best_conf = 0.0
            best_box  = None

            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    conf = float(box.conf[0])
                    if conf > best_conf:
                        best_conf = conf
                        best_box  = box.xyxy[0].cpu().numpy().astype(int)

            if best_box is None:
                return None

            x1, y1, x2, y2 = best_box
            h, w = image.shape[:2]
            # Add small padding
            pad = 4
            x1 = max(0, x1 - pad)
            y1 = max(0, y1 - pad)
            x2 = min(w, x2 + pad)
            y2 = min(h, y2 + pad)

            crop = image[y1:y2, x1:x2]
            if crop.size == 0:
                return None

            logger.debug(f"Plate detected by model (conf={best_conf:.2f}): {x2-x1}x{y2-y1}")
            return crop

        except Exception as e:
            logger.debug(f"Model plate detection error: {e}")
            return None

    # ------------------------------------------------------------------
    def _detect_with_contours(self, vehicle_image: np.ndarray) -> Optional[np.ndarray]:
        """Contour-based fallback plate detection."""
        try:
            h, w = vehicle_image.shape[:2]
            # Plates are in the lower 60% of the vehicle
            roi = vehicle_image[int(h * 0.35):, :]

            gray    = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            blur    = cv2.GaussianBlur(gray, (5, 5), 0)
            edged   = cv2.Canny(blur, 80, 200)
            kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            dilated = cv2.dilate(edged, kernel, iterations=1)

            contours, _ = cv2.findContours(
                dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )

            candidates = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if not (self.min_area <= area <= self.max_area):
                    continue
                x, y, cw, ch = cv2.boundingRect(cnt)
                if ch == 0:
                    continue
                aspect = float(cw) / ch
                if self.min_aspect < aspect < self.max_aspect:
                    candidates.append((area, x, y, cw, ch))

            if not candidates:
                return None

            _, x, y, cw, ch = max(candidates, key=lambda c: c[0])
            pad = 5
            x  = max(0, x - pad)
            y  = max(0, y - pad)
            cw = min(roi.shape[1] - x, cw + 2 * pad)
            ch = min(roi.shape[0] - y, ch + 2 * pad)

            crop = roi[y:y + ch, x:x + cw]
            return crop if crop.size > 0 else None

        except Exception as e:
            logger.debug(f"Contour plate detection error: {e}")
            return None
