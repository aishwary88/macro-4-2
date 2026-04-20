"""
ROI (Region of Interest) Manager: defines virtual lines/regions and tracks crossings.
This is the foundation of accurate speed measurement.
"""

import time
from typing import Dict, Tuple, Optional, List
from modules.utils.geometry import point_crosses_line
from modules.utils.logger import get_logger

logger = get_logger("roi_manager")


class ROIManager:
    """Manages virtual ROI lines and tracks vehicle crossings.

    Two horizontal lines (Line A and Line B) define the speed measurement zone.
    When a vehicle crosses both lines, the time difference is used to calculate speed.
    """

    def __init__(
        self,
        line_a_y: int = 300,
        line_b_y: int = 500,
        known_distance: float = 10.0,
        frame_width: int = 1920,
    ):
        """Initialize ROI Manager.

        Args:
            line_a_y: Y-coordinate of Line A (entry line).
            line_b_y: Y-coordinate of Line B (exit line).
            known_distance: Real-world distance between lines in meters.
            frame_width: Width of the video frame (for drawing).
        """
        self.line_a_y = line_a_y
        self.line_b_y = line_b_y
        self.known_distance = known_distance
        self.frame_width = frame_width

        # Crossing records: {vehicle_id: {'line_a': timestamp, 'line_b': timestamp}}
        self._crossings: Dict[int, Dict[str, Optional[float]]] = {}

        # Optional polygon ROI region
        self._roi_polygon: Optional[List[Tuple[float, float]]] = None

        logger.info(
            f"ROI Manager initialized: Line A @ y={line_a_y}, "
            f"Line B @ y={line_b_y}, distance={known_distance}m"
        )

    def set_lines(self, line_a_y: int, line_b_y: int):
        """Update line positions.

        Args:
            line_a_y: Y-coordinate of Line A.
            line_b_y: Y-coordinate of Line B.
        """
        self.line_a_y = line_a_y
        self.line_b_y = line_b_y
        logger.info(f"ROI lines updated: A={line_a_y}, B={line_b_y}")

    def set_roi_region(self, polygon_points: List[Tuple[float, float]]):
        """Set an optional polygon ROI region.

        Args:
            polygon_points: List of (x, y) vertices defining the region.
        """
        self._roi_polygon = polygon_points
        logger.info(f"ROI polygon set with {len(polygon_points)} points")

    def check_line_crossing(
        self,
        vehicle_id: int,
        prev_pos: Tuple[float, float],
        curr_pos: Tuple[float, float],
        timestamp: float,
    ) -> Optional[str]:
        """Check if a vehicle crossed any ROI line.

        Args:
            vehicle_id: Unique vehicle tracking ID.
            prev_pos: Previous (x, y) position.
            curr_pos: Current (x, y) position.
            timestamp: Current frame timestamp in seconds.

        Returns:
            'line_a', 'line_b', or None.
        """
        # Initialize crossing record for new vehicles
        if vehicle_id not in self._crossings:
            self._crossings[vehicle_id] = {"line_a": None, "line_b": None}

        record = self._crossings[vehicle_id]

        # Check Line A crossing
        crossing_a = point_crosses_line(prev_pos, curr_pos, self.line_a_y)
        if crossing_a and record["line_a"] is None:
            record["line_a"] = timestamp
            logger.debug(f"Vehicle {vehicle_id} crossed Line A at t={timestamp:.3f}s")
            return "line_a"

        # Check Line B crossing
        crossing_b = point_crosses_line(prev_pos, curr_pos, self.line_b_y)
        if crossing_b and record["line_b"] is None:
            record["line_b"] = timestamp
            logger.debug(f"Vehicle {vehicle_id} crossed Line B at t={timestamp:.3f}s")
            return "line_b"

        return None

    def get_crossing_times(self, vehicle_id: int) -> Tuple[Optional[float], Optional[float]]:
        """Get crossing timestamps for a vehicle.

        Args:
            vehicle_id: Vehicle tracking ID.

        Returns:
            Tuple of (line_a_time, line_b_time), either can be None.
        """
        record = self._crossings.get(vehicle_id, {})
        return (record.get("line_a"), record.get("line_b"))

    def has_both_crossings(self, vehicle_id: int) -> bool:
        """Check if vehicle has crossed both lines.

        Args:
            vehicle_id: Vehicle tracking ID.

        Returns:
            True if both lines have been crossed.
        """
        t_a, t_b = self.get_crossing_times(vehicle_id)
        return t_a is not None and t_b is not None

    def get_crossing_time_delta(self, vehicle_id: int) -> Optional[float]:
        """Get time difference between Line A and Line B crossings.

        Args:
            vehicle_id: Vehicle tracking ID.

        Returns:
            Time delta in seconds, or None if both lines not yet crossed.
        """
        t_a, t_b = self.get_crossing_times(vehicle_id)
        if t_a is not None and t_b is not None:
            return abs(t_b - t_a)
        return None

    def get_lines_for_drawing(self) -> List[Dict]:
        """Get line data for visualization.

        Returns:
            List of dicts with line info for the renderer.
        """
        return [
            {
                "label": "Line A (Entry)",
                "y": self.line_a_y,
                "start": (0, self.line_a_y),
                "end": (self.frame_width, self.line_a_y),
            },
            {
                "label": "Line B (Exit)",
                "y": self.line_b_y,
                "start": (0, self.line_b_y),
                "end": (self.frame_width, self.line_b_y),
            },
        ]

    def cleanup_vehicle(self, vehicle_id: int):
        """Remove crossing data for a vehicle.

        Args:
            vehicle_id: Vehicle tracking ID to remove.
        """
        self._crossings.pop(vehicle_id, None)

    def reset(self):
        """Clear all crossing records."""
        self._crossings.clear()
        logger.info("ROI Manager reset — all crossings cleared")
