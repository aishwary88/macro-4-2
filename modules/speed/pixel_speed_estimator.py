"""
Pixel-displacement speed estimator for live camera mode.

How it works:
  1. Track vehicle center position every N frames
  2. Calculate pixel distance moved between frames
  3. Convert pixels → meters using PIXEL_SCALE
  4. Convert meters/second → km/h
  5. Apply smoothing window (last N readings averaged)
  6. Apply noise filter (ignore tiny movements)

This runs continuously — no need for vehicles to cross specific lines.
Works for any camera angle and any road setup.
"""

import math
from collections import deque
from typing import Dict, Optional, Tuple
from core.config import settings
from modules.utils.logger import get_logger

logger = get_logger("pixel_speed")


class PixelSpeedEstimator:
    """Continuous pixel-displacement based speed estimator.

    Designed for live camera mode where ROI line-crossing may not
    be reliable. Uses frame-by-frame position tracking with smoothing.
    """

    def __init__(
        self,
        fps: float,
        pixel_scale: float = None,
        min_pixel_move: float = None,
        smooth_window: int = None,
        update_interval: int = None,
    ):
        """
        Args:
            fps: Camera/video frames per second.
            pixel_scale: Meters per pixel (e.g. 0.05 means 1px = 5cm).
            min_pixel_move: Minimum pixel movement to count as real motion.
            smooth_window: Number of recent speed samples to average.
            update_interval: Update speed every N frames.
        """
        self.fps             = max(fps, 1.0)
        self.pixel_scale     = pixel_scale     or settings.PIXEL_SCALE
        self.min_pixel_move  = min_pixel_move  or settings.SPEED_MIN_PIXEL_MOVE
        self.smooth_window   = smooth_window   or settings.SPEED_SMOOTH_WINDOW
        self.update_interval = update_interval or settings.SPEED_UPDATE_INTERVAL

        # Per-vehicle state
        # { vehicle_id: { 'last_pos': (x,y), 'last_frame': int, 'samples': deque } }
        self._state: Dict[int, dict] = {}

        logger.info(
            f"PixelSpeedEstimator: fps={self.fps:.1f}, "
            f"scale={self.pixel_scale} m/px, "
            f"min_move={self.min_pixel_move}px, "
            f"smooth={self.smooth_window} samples"
        )

    def update(
        self,
        vehicle_id: int,
        position: Tuple[float, float],
        frame_num: int,
    ) -> Optional[float]:
        """Update position and return smoothed speed in km/h, or None.

        Args:
            vehicle_id: Unique vehicle tracking ID.
            position: Current (x, y) center position in pixels.
            frame_num: Current frame number.

        Returns:
            Smoothed speed in km/h, or None if not enough data yet.
        """
        if vehicle_id not in self._state:
            self._state[vehicle_id] = {
                'last_pos':   position,
                'last_frame': frame_num,
                'samples':    deque(maxlen=self.smooth_window),
            }
            return None

        state = self._state[vehicle_id]

        # Only update every N frames for stability
        frames_elapsed = frame_num - state['last_frame']
        if frames_elapsed < self.update_interval:
            # Return current smoothed speed without updating
            return self._smoothed(state)

        # Calculate pixel displacement
        dx = position[0] - state['last_pos'][0]
        dy = position[1] - state['last_pos'][1]
        pixel_dist = math.sqrt(dx * dx + dy * dy)

        # Noise filter — ignore tiny jitter
        if pixel_dist < self.min_pixel_move:
            state['last_pos']   = position
            state['last_frame'] = frame_num
            return self._smoothed(state)

        # Time elapsed in seconds
        time_elapsed = frames_elapsed / self.fps
        if time_elapsed <= 0:
            return self._smoothed(state)

        # Speed calculation
        # pixel_dist px * pixel_scale m/px = meters
        # meters / time_elapsed s = m/s
        # m/s * 3.6 = km/h
        meters   = pixel_dist * self.pixel_scale
        speed_ms = meters / time_elapsed
        speed_kmh = speed_ms * 3.6

        # Sanity cap — no vehicle goes faster than 200 km/h on a road
        speed_kmh = min(speed_kmh, 200.0)
        speed_kmh = max(speed_kmh, 0.0)

        # Add to smoothing window
        state['samples'].append(speed_kmh)

        # Update state
        state['last_pos']   = position
        state['last_frame'] = frame_num

        smoothed = self._smoothed(state)
        logger.debug(
            f"Vehicle {vehicle_id}: raw={speed_kmh:.1f} km/h "
            f"smooth={smoothed:.1f} km/h "
            f"(px={pixel_dist:.1f}, t={time_elapsed:.3f}s)"
        )
        return smoothed

    def _smoothed(self, state: dict) -> Optional[float]:
        """Return average of recent speed samples."""
        samples = state['samples']
        if not samples:
            return None
        return round(sum(samples) / len(samples), 1)

    def remove(self, vehicle_id: int):
        """Remove tracking state for a vehicle."""
        self._state.pop(vehicle_id, None)

    def reset(self):
        """Clear all vehicle states."""
        self._state.clear()
