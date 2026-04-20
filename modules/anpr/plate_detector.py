"""
License plate detection: locates plate regions within vehicle bounding boxes.
Uses contour-based detection with aspect ratio filtering.
"""

import cv2
import numpy as np
from typing import Optional, Tuple
from modules.utils.logger import get_logger
from modules.utils.image_utils import crop_region

logger = get_logger("plate_detector")


class PlateDetector:
    """Locates license plate regions within vehicle images.

    Uses edge detection and contour analysis with aspect ratio
    filtering to identify potential plate regions.
    """

    def __init__(
        self,
        min_area: int = 1500,
        max_area: int = 80000,
        min_aspect: float = 1.5,
        max_aspect: float = 6.0,
    ):
        """Initialize plate detector.

        Args:
            min_area: Minimum contour area for plate candidates.
            max_area: Maximum contour area for plate candidates.
            min_aspect: Minimum width/height aspect ratio.
            max_aspect: Maximum width/height aspect ratio.
        """
        self.min_area = min_area
        self.max_area = max_area
        self.min_aspect = min_aspect
        self.max_aspect = max_aspect
        logger.info("PlateDetector initialized")

    def detect(self, vehicle_image: np.ndarray) -> Optional[np.ndarray]:
        """Detect and extract the license plate region from a vehicle image.

        Args:
            vehicle_image: Cropped vehicle region (BGR).

        Returns:
            Cropped plate image or None if no plate found.
        """
        if vehicle_image is None or vehicle_image.size == 0:
            return None

        try:
            h, w = vehicle_image.shape[:2]

            # Focus on the lower portion of the vehicle (where plates usually are)
            bottom_half = vehicle_image[int(h * 0.4):, :]

            # Preprocessing
            gray = cv2.cvtColor(bottom_half, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            edged = cv2.Canny(blur, 100, 200)

            # Dilate to connect edges
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            dilated = cv2.dilate(edged, kernel, iterations=1)

            # Find contours
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
            )

            # Filter contours by area and aspect ratio
            candidates = []
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < self.min_area or area > self.max_area:
                    continue

                x, y, cw, ch = cv2.boundingRect(cnt)
                if ch == 0:
                    continue

                aspect_ratio = float(cw) / ch

                if self.min_aspect < aspect_ratio < self.max_aspect:
                    candidates.append({
                        "contour": cnt,
                        "bbox": (x, y, cw, ch),
                        "area": area,
                        "aspect": aspect_ratio,
                    })

            if not candidates:
                return None

            # Select the best candidate (largest area with good aspect ratio)
            best = max(candidates, key=lambda c: c["area"])
            x, y, cw, ch = best["bbox"]

            # Add padding
            pad = 5
            x = max(0, x - pad)
            y = max(0, y - pad)
            cw = min(bottom_half.shape[1] - x, cw + 2 * pad)
            ch = min(bottom_half.shape[0] - y, ch + 2 * pad)

            plate_image = bottom_half[y:y + ch, x:x + cw]

            if plate_image.size == 0:
                return None

            logger.debug(f"Plate detected: {cw}x{ch} (aspect: {best['aspect']:.2f})")
            return plate_image

        except Exception as e:
            logger.debug(f"Plate detection error: {e}")
            return None
