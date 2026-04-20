"""
Camera calibration: maps pixel distances to real-world distances.
Essential for accurate speed measurement.
"""

import json
import numpy as np
from typing import Tuple, Optional, List
from pathlib import Path
from modules.utils.logger import get_logger

logger = get_logger("calibrator")


class Calibrator:
    """Maps pixel coordinates to real-world distances.

    Supports both simple scale factor and perspective transform calibration.
    """

    def __init__(self):
        self._pixels_per_meter: float = 50.0  # default fallback
        self._calibrated: bool = False
        self._reference_points: Optional[List] = None
        self._homography_matrix: Optional[np.ndarray] = None

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    @property
    def pixels_per_meter(self) -> float:
        return self._pixels_per_meter

    def set_scale_factor(self, pixel_distance: float, real_distance_meters: float):
        """Simple calibration using a known distance.

        Args:
            pixel_distance: Distance in pixels between two reference points.
            real_distance_meters: Corresponding real-world distance in meters.
        """
        if real_distance_meters <= 0:
            logger.error("Real distance must be positive")
            return

        self._pixels_per_meter = pixel_distance / real_distance_meters
        self._calibrated = True
        logger.info(
            f"Calibration set: {self._pixels_per_meter:.2f} pixels/meter "
            f"(pixel_dist={pixel_distance:.1f}, real_dist={real_distance_meters:.1f}m)"
        )

    def set_reference_points(
        self,
        pixel_points: List[Tuple[float, float]],
        real_world_points: List[Tuple[float, float]],
    ):
        """Advanced calibration using multiple reference points.

        Computes a homography matrix for perspective correction.

        Args:
            pixel_points: List of (x, y) coordinates in the image.
            real_world_points: Corresponding real-world (x, y) coordinates in meters.
        """
        if len(pixel_points) < 4 or len(real_world_points) < 4:
            logger.warning("Need at least 4 point pairs for homography. Falling back to scale factor.")
            # Use first two points for simple scale
            if len(pixel_points) >= 2:
                p_dist = np.linalg.norm(
                    np.array(pixel_points[0]) - np.array(pixel_points[1])
                )
                r_dist = np.linalg.norm(
                    np.array(real_world_points[0]) - np.array(real_world_points[1])
                )
                self.set_scale_factor(p_dist, r_dist)
            return

        src = np.float32(pixel_points)
        dst = np.float32(real_world_points)
        self._homography_matrix, _ = cv2.findHomography(src, dst)
        self._reference_points = list(zip(pixel_points, real_world_points))
        self._calibrated = True
        logger.info(f"Homography calibration set with {len(pixel_points)} points")

    def pixels_to_meters(self, pixel_distance: float) -> float:
        """Convert pixel distance to real-world meters.

        Args:
            pixel_distance: Distance in pixels.

        Returns:
            Distance in meters.
        """
        if self._pixels_per_meter <= 0:
            return 0.0
        return pixel_distance / self._pixels_per_meter

    def compute_pixels_per_meter(self, line_a_y: int, line_b_y: int, real_distance: float):
        """Compute pixels_per_meter from ROI line positions.

        Args:
            line_a_y: Y-coordinate of Line A.
            line_b_y: Y-coordinate of Line B.
            real_distance: Known real-world distance between lines in meters.
        """
        pixel_distance = abs(line_b_y - line_a_y)
        self.set_scale_factor(pixel_distance, real_distance)

    def save_calibration(self, filepath: str):
        """Save calibration data to JSON file.

        Args:
            filepath: Path to save the calibration file.
        """
        data = {
            "pixels_per_meter": self._pixels_per_meter,
            "calibrated": self._calibrated,
            "reference_points": self._reference_points,
        }

        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Calibration saved to {filepath}")

    def load_calibration(self, filepath: str) -> bool:
        """Load calibration data from JSON file.

        Args:
            filepath: Path to the calibration file.

        Returns:
            True if loaded successfully, False otherwise.
        """
        try:
            with open(filepath, "r") as f:
                data = json.load(f)

            self._pixels_per_meter = data.get("pixels_per_meter", 50.0)
            self._calibrated = data.get("calibrated", False)
            self._reference_points = data.get("reference_points")

            logger.info(f"Calibration loaded from {filepath}: {self._pixels_per_meter:.2f} px/m")
            return True
        except FileNotFoundError:
            logger.warning(f"Calibration file not found: {filepath}")
            return False
        except Exception as e:
            logger.error(f"Error loading calibration: {e}")
            return False
