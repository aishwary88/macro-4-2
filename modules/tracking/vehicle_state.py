"""
Central Vehicle State Manager.
THE most critical data structure — links positions, speed, plates, and status per vehicle.
Without this, speed breaks, plate mapping breaks, everything breaks.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import pandas as pd
from core.constants import SPEED_LIMIT_KMH
from core.config import settings
from modules.utils.logger import get_logger

logger = get_logger("vehicle_state")


@dataclass
class VehicleState:
    """Complete state for a single tracked vehicle."""
    vehicle_id: int
    vehicle_type: str = "unknown"

    # Position tracking
    positions: List[Tuple[float, float, float]] = field(default_factory=list)
    # Each entry: (x, y, timestamp)

    # Speed
    speed: Optional[float] = None
    max_speed: float = 0.0
    speed_history: List[float] = field(default_factory=list)

    # License plate
    plate: Optional[str] = None
    plate_confidence: float = 0.0

    # ROI crossings
    line_a_time: Optional[float] = None
    line_b_time: Optional[float] = None

    # Status
    overspeed: bool = False
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    frame_count: int = 0

    # Current bounding box
    current_bbox: Optional[Tuple[float, float, float, float]] = None
    confidence: float = 0.0


class VehicleStateManager:
    """Central state manager for all tracked vehicles.

    This is the single source of truth for vehicle data during processing.
    All modules read/write vehicle state through this manager.
    """

    def __init__(self):
        self.vehicles: Dict[int, VehicleState] = {}
        self._speed_limit = settings.SPEED_LIMIT_KMH
        logger.info(f"VehicleStateManager initialized (speed limit: {self._speed_limit} km/h)")

    def get_or_create(self, vehicle_id: int) -> VehicleState:
        """Get existing vehicle state or create new one.

        Args:
            vehicle_id: Unique vehicle tracking ID.

        Returns:
            VehicleState for the vehicle.
        """
        if vehicle_id not in self.vehicles:
            self.vehicles[vehicle_id] = VehicleState(
                vehicle_id=vehicle_id,
                first_seen=datetime.now(),
            )
        return self.vehicles[vehicle_id]

    def update_position(
        self,
        vehicle_id: int,
        position: Tuple[float, float],
        timestamp: float,
        bbox: Tuple[float, float, float, float],
        confidence: float = 0.0,
    ):
        """Update vehicle position and bbox.

        Args:
            vehicle_id: Vehicle tracking ID.
            position: (x, y) center position.
            timestamp: Frame timestamp in seconds.
            bbox: (x1, y1, x2, y2) bounding box.
            confidence: Detection confidence.
        """
        state = self.get_or_create(vehicle_id)
        state.positions.append((position[0], position[1], timestamp))
        state.current_bbox = bbox
        state.confidence = confidence
        state.last_seen = datetime.now()
        state.frame_count += 1

    def set_vehicle_type(self, vehicle_id: int, vehicle_type: str):
        """Set standardized vehicle type.

        Args:
            vehicle_id: Vehicle tracking ID.
            vehicle_type: Standardized type (Car, Truck, Bus, Bike).
        """
        state = self.get_or_create(vehicle_id)
        state.vehicle_type = vehicle_type

    def set_speed(self, vehicle_id: int, speed: float):
        """Set vehicle speed and check overspeed.

        Args:
            vehicle_id: Vehicle tracking ID.
            speed: Speed in km/h.
        """
        state = self.get_or_create(vehicle_id)
        state.speed = speed
        state.speed_history.append(speed)

        if speed > state.max_speed:
            state.max_speed = speed

        if speed > self._speed_limit:
            state.overspeed = True
            logger.warning(f"🚨 Vehicle {vehicle_id} OVERSPEEDING: {speed:.1f} km/h")

    def set_plate(self, vehicle_id: int, plate: str, confidence: float):
        """Set license plate if confidence is higher than existing.

        Args:
            vehicle_id: Vehicle tracking ID.
            plate: Plate text.
            confidence: OCR confidence.
        """
        state = self.get_or_create(vehicle_id)

        # Only update if better confidence
        if confidence > state.plate_confidence:
            state.plate = plate
            state.plate_confidence = confidence
            logger.info(f"Vehicle {vehicle_id} plate: {plate} (conf: {confidence:.2f})")

    def set_line_crossing(self, vehicle_id: int, line: str, timestamp: float):
        """Record line crossing time.

        Args:
            vehicle_id: Vehicle tracking ID.
            line: 'line_a' or 'line_b'.
            timestamp: Crossing timestamp.
        """
        state = self.get_or_create(vehicle_id)
        if line == "line_a":
            state.line_a_time = timestamp
        elif line == "line_b":
            state.line_b_time = timestamp

    def get_vehicle(self, vehicle_id: int) -> Optional[VehicleState]:
        """Get vehicle state.

        Args:
            vehicle_id: Vehicle tracking ID.

        Returns:
            VehicleState or None.
        """
        return self.vehicles.get(vehicle_id)

    def get_all_vehicles(self) -> Dict[int, VehicleState]:
        """Get all vehicle states."""
        return self.vehicles

    def get_active_vehicles(self) -> Dict[int, VehicleState]:
        """Get vehicles that have a current bbox (are visible in current frame)."""
        return {
            vid: state
            for vid, state in self.vehicles.items()
            if state.current_bbox is not None
        }

    def get_overspeeding(self) -> List[VehicleState]:
        """Get all overspeeding vehicles."""
        return [v for v in self.vehicles.values() if v.overspeed]

    def get_previous_position(self, vehicle_id: int) -> Optional[Tuple[float, float]]:
        """Get the previous position of a vehicle.

        Args:
            vehicle_id: Vehicle tracking ID.

        Returns:
            (x, y) previous position or None.
        """
        state = self.vehicles.get(vehicle_id)
        if state and len(state.positions) >= 2:
            return (state.positions[-2][0], state.positions[-2][1])
        return None

    def is_good_frame_for_ocr(self, vehicle_id: int) -> bool:
        """Check if current frame is good for OCR on this vehicle.

        Criteria:
        - Vehicle has been tracked for at least 5 frames (stable)
        - Vehicle doesn't already have a high-confidence plate
        - Position is relatively stable (not moving too fast between frames)

        Args:
            vehicle_id: Vehicle tracking ID.

        Returns:
            True if OCR should be attempted.
        """
        state = self.vehicles.get(vehicle_id)
        if state is None:
            return False

        # Already has a good plate
        if state.plate_confidence > 0.7:
            return False

        # Need at least 5 frames for stability
        if state.frame_count < 5:
            return False

        # Check frame interval
        if state.frame_count % settings.ANPR_FRAME_INTERVAL != 0:
            return False

        return True

    def cleanup_stale(self, max_age_frames: int = 30, current_vehicle_ids: set = None):
        """Remove vehicles that haven't been seen recently.

        Args:
            max_age_frames: Maximum frames since last seen to keep.
            current_vehicle_ids: Set of currently visible vehicle IDs.
        """
        if current_vehicle_ids is None:
            return

        stale_ids = []
        for vid, state in self.vehicles.items():
            if vid not in current_vehicle_ids and state.frame_count < max_age_frames:
                stale_ids.append(vid)

        for vid in stale_ids:
            del self.vehicles[vid]

        if stale_ids:
            logger.debug(f"Cleaned up {len(stale_ids)} stale vehicles")

    def export_to_dataframe(self) -> pd.DataFrame:
        """Export all vehicle data to a Pandas DataFrame.

        Returns:
            DataFrame with vehicle data for reports.
        """
        records = []
        for vid, state in self.vehicles.items():
            avg_speed = (
                sum(state.speed_history) / len(state.speed_history)
                if state.speed_history
                else 0
            )
            records.append({
                "vehicle_id": vid,
                "vehicle_type": state.vehicle_type,
                "plate_number": state.plate or "N/A",
                "avg_speed": round(avg_speed, 2),
                "max_speed": round(state.max_speed, 2),
                "overspeed": state.overspeed,
                "first_seen": state.first_seen.strftime("%Y-%m-%d %H:%M:%S") if state.first_seen else "",
                "last_seen": state.last_seen.strftime("%Y-%m-%d %H:%M:%S") if state.last_seen else "",
                "frame_count": state.frame_count,
            })

        return pd.DataFrame(records)

    def get_stats(self) -> dict:
        """Get summary statistics.

        Returns:
            Dict with total, per-type counts, speed stats.
        """
        total = len(self.vehicles)
        types = {}
        overspeed_count = 0
        speeds = []

        for state in self.vehicles.values():
            vtype = state.vehicle_type
            types[vtype] = types.get(vtype, 0) + 1

            if state.overspeed:
                overspeed_count += 1

            if state.speed_history:
                speeds.extend(state.speed_history)

        return {
            "total_vehicles": total,
            "vehicle_types": types,
            "overspeed_count": overspeed_count,
            "avg_speed": round(sum(speeds) / len(speeds), 2) if speeds else 0,
            "max_speed": round(max(speeds), 2) if speeds else 0,
            "min_speed": round(min(speeds), 2) if speeds else 0,
        }

    def reset(self):
        """Clear all vehicle states."""
        self.vehicles.clear()
        logger.info("Vehicle state manager reset")
