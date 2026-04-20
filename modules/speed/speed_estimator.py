"""
ROI-based speed estimation module.
Calculates vehicle speed using two virtual lines and known real-world distance.

How it works:
1. Vehicle crosses Line A → record timestamp
2. Vehicle crosses Line B → record timestamp
3. speed = known_distance / time_difference
4. Convert to km/h
"""

from dataclasses import dataclass
from typing import Tuple, Optional
from modules.calibration.roi_manager import ROIManager
from modules.calibration.calibrator import Calibrator
from modules.tracking.vehicle_state import VehicleStateManager
from modules.utils.logger import get_logger
from core.config import settings

logger = get_logger("speed")


@dataclass
class SpeedData:
    """Speed measurement result."""
    vehicle_id: int
    speed_kmh: float
    timestamp: float
    is_overspeed: bool


class SpeedEstimator:
    """ROI-based vehicle speed estimator.

    Uses two virtual lines on the road with a known real-world distance.
    Speed = distance / time to cross both lines.
    """

    def __init__(
        self,
        roi_manager: ROIManager,
        calibrator: Calibrator,
        state_manager: VehicleStateManager,
    ):
        """Initialize speed estimator.

        Args:
            roi_manager: ROI Manager for line crossing detection.
            calibrator: Calibrator for pixel-to-meter conversion.
            state_manager: Central vehicle state manager.
        """
        self.roi_manager = roi_manager
        self.calibrator = calibrator
        self.state_manager = state_manager
        self._speed_limit = settings.SPEED_LIMIT_KMH

        # If calibrator is not yet calibrated, auto-calibrate from ROI lines
        if not calibrator.is_calibrated:
            calibrator.compute_pixels_per_meter(
                roi_manager.line_a_y,
                roi_manager.line_b_y,
                roi_manager.known_distance,
            )

        logger.info(
            f"SpeedEstimator initialized "
            f"(limit={self._speed_limit} km/h, "
            f"distance={roi_manager.known_distance}m)"
        )

    def update(
        self,
        vehicle_id: int,
        prev_pos: Tuple[float, float],
        curr_pos: Tuple[float, float],
        timestamp: float,
    ) -> Optional[SpeedData]:
        """Check for line crossings and calculate speed if both lines crossed.

        Args:
            vehicle_id: Vehicle tracking ID.
            prev_pos: Previous (x, y) bottom-center position.
            curr_pos: Current (x, y) bottom-center position.
            timestamp: Current frame timestamp in seconds.

        Returns:
            SpeedData if speed was calculated, None otherwise.
        """
        # Check for line crossing
        crossing = self.roi_manager.check_line_crossing(
            vehicle_id, prev_pos, curr_pos, timestamp
        )

        if crossing:
            self.state_manager.set_line_crossing(vehicle_id, crossing, timestamp)

        # Check if both lines crossed — calculate speed
        if self.roi_manager.has_both_crossings(vehicle_id):
            time_delta = self.roi_manager.get_crossing_time_delta(vehicle_id)

            if time_delta and time_delta > 0:
                # Speed = distance / time
                distance_meters = self.roi_manager.known_distance
                speed_mps = distance_meters / time_delta
                speed_kmh = speed_mps * 3.6  # m/s to km/h

                # Sanity check: cap unrealistic speeds
                if speed_kmh > 300:
                    logger.warning(
                        f"Vehicle {vehicle_id}: unrealistic speed {speed_kmh:.1f} km/h, "
                        f"capping to 300 km/h"
                    )
                    speed_kmh = 300.0

                speed_kmh = max(0, speed_kmh)

                # Update state manager
                self.state_manager.set_speed(vehicle_id, speed_kmh)

                is_overspeed = speed_kmh > self._speed_limit

                logger.info(
                    f"Vehicle {vehicle_id}: {speed_kmh:.1f} km/h "
                    f"(Δt={time_delta:.3f}s, d={distance_meters}m) "
                    f"{'🚨 OVERSPEED' if is_overspeed else '✅ NORMAL'}"
                )

                return SpeedData(
                    vehicle_id=vehicle_id,
                    speed_kmh=speed_kmh,
                    timestamp=timestamp,
                    is_overspeed=is_overspeed,
                )

        return None

    def is_overspeeding(self, speed: float) -> bool:
        """Check if a speed value is above the limit.

        Args:
            speed: Speed in km/h.

        Returns:
            True if overspeeding.
        """
        return speed > self._speed_limit
