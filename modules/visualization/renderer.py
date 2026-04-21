"""
Frame annotation renderer — draws bounding boxes, speed, plate, ROI lines,
tracking trails, and HUD onto each video frame.
"""

import cv2
import numpy as np
from datetime import datetime
from typing import Optional

from core.constants import (
    COLOR_OVERSPEED, COLOR_NORMAL, COLOR_ROI_LINE, COLOR_TRACK,
    COLOR_PLATE_TEXT, COLOR_HUD_BG, SPEED_LIMIT_KMH
)
from modules.utils.logger import get_logger

logger = get_logger(__name__)


class FrameRenderer:
    """Annotates raw frames with tracking, speed, plate, and ROI overlays."""

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_small = 0.5
        self.font_medium = 0.65
        self.font_large = 0.85
        self.thickness = 2

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def draw(
        self,
        frame: np.ndarray,
        state_manager,
        roi_manager=None,
        frame_number: int = 0,
        video_fps: float = 25.0,
        bbox_scale: float = 1.0,
    ) -> np.ndarray:
        """
        Main render call.  Returns a new annotated copy of *frame*.

        Args:
            bbox_scale: Scale factor to apply to bboxes (use when detection
                        was done on a resized frame but rendering on original).
        """
        annotated = frame.copy()

        # ROI lines (always visible) — scale Y positions if needed
        if roi_manager is not None:
            self._draw_roi_lines(annotated, roi_manager, bbox_scale)

        # Per-vehicle overlays
        vehicles = state_manager.get_all_vehicles()
        for vid, vs in vehicles.items():
            if vs.current_bbox is None:
                continue
            self._draw_vehicle(annotated, vid, vs, bbox_scale)
            if self.debug:
                self._draw_track_trail(annotated, vs, bbox_scale)

        # HUD overlay (top-right)
        self._draw_hud(annotated, state_manager, frame_number, video_fps)

        return annotated

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _draw_vehicle(self, frame: np.ndarray, vehicle_id: int, vs, scale: float = 1.0) -> None:
        """Draw bounding box, ID label, speed, and plate for one vehicle."""
        x1, y1, x2, y2 = [int(c * scale) for c in vs.current_bbox]

        # Clamp to frame bounds
        fh, fw = frame.shape[:2]
        x1 = max(0, min(x1, fw - 1))
        y1 = max(0, min(y1, fh - 1))
        x2 = max(0, min(x2, fw - 1))
        y2 = max(0, min(y2, fh - 1))

        if x2 <= x1 or y2 <= y1:
            return

        is_over = vs.overspeed
        color = COLOR_OVERSPEED if is_over else COLOR_NORMAL

        # Thick box — 2px border + 1px inner highlight for visibility
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 0), self.thickness + 2)  # black outline
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, self.thickness)           # colored box

        # Speed label — always show (even if 0, show "--")
        speed_txt = f"{vs.speed:.1f} km/h" if vs.speed is not None else "-- km/h"
        if is_over:
            speed_txt += " OVER"
        self._put_label(frame, speed_txt, (x1, max(y1 - 6, 20)), color, self.font_medium)

        # ID + type label below speed
        label = f"ID:{vehicle_id} {vs.vehicle_type or 'Vehicle'}"
        self._put_label(frame, label, (x1, max(y1 - 26, 40)), (200, 200, 200), self.font_small)

        # Plate label below box
        if vs.plate and vs.plate_confidence >= 0.4:
            self._put_label(frame, vs.plate, (x1, min(y2 + 16, fh - 4)), COLOR_PLATE_TEXT, self.font_small)

    def _draw_track_trail(self, frame: np.ndarray, vs, scale: float = 1.0) -> None:
        """Draw historical centroid path as a faded polyline (debug mode)."""
        positions = vs.positions
        pts = [(int(p[0] * scale), int(p[1] * scale)) for p in positions[-30:]]
        if len(pts) < 2:
            return
        for i in range(1, len(pts)):
            alpha = i / len(pts)
            c = (int(COLOR_TRACK[0]*alpha), int(COLOR_TRACK[1]*alpha), int(COLOR_TRACK[2]*alpha))
            cv2.line(frame, pts[i-1], pts[i], c, 1)

    def _draw_roi_lines(self, frame: np.ndarray, roi_manager, scale: float = 1.0) -> None:
        """Draw Line A / Line B as dashed horizontal lines."""
        h, w = frame.shape[:2]
        line_a_y = int(roi_manager.line_a_y * scale)
        line_b_y = int(roi_manager.line_b_y * scale)

        if line_a_y is not None:
            self._draw_dashed_line(frame, (0, line_a_y), (w, line_a_y), COLOR_ROI_LINE, label="Line A")
        if line_b_y is not None:
            self._draw_dashed_line(frame, (0, line_b_y), (w, line_b_y), COLOR_ROI_LINE, label="Line B")

    def _draw_dashed_line(
        self,
        frame: np.ndarray,
        pt1: tuple,
        pt2: tuple,
        color: tuple,
        dash_len: int = 20,
        gap_len: int = 10,
        label: str = "",
    ) -> None:
        """Draw a dashed line between two points."""
        x1, y1 = pt1
        x2, y2 = pt2
        total = x2 - x1
        x = x1
        draw = True
        while x < x2:
            seg = dash_len if draw else gap_len
            xe = min(x + seg, x2)
            if draw:
                cv2.line(frame, (x, y1), (xe, y2), color, 2)
            x = xe
            draw = not draw

        if label:
            cv2.putText(
                frame,
                label,
                (x1 + 4, y1 - 6),
                self.font,
                self.font_small,
                color,
                1,
                cv2.LINE_AA,
            )

    def _draw_hud(
        self,
        frame: np.ndarray,
        state_manager,
        frame_number: int,
        video_fps: float,
    ) -> None:
        """Top-left HUD with vehicle count, avg speed, overspeed count, timestamp."""
        vehicles   = state_manager.get_all_vehicles()
        active     = {vid: v for vid, v in vehicles.items() if v.current_bbox is not None}
        total      = len(active)
        overspeeding = sum(1 for v in active.values() if v.overspeed)
        speeds     = [v.speed for v in active.values() if v.speed is not None and v.speed > 0]
        avg_spd    = round(sum(speeds) / len(speeds), 1) if speeds else 0.0

        now = datetime.now().strftime("%H:%M:%S")

        lines = [
            f"Vehicles: {total}",
            f"Avg Speed: {avg_spd} km/h",
            f"Overspeed: {overspeeding}",
            f"Time: {now}",
        ]

        pad   = 6
        box_w = 210
        box_h = len(lines) * 22 + pad * 2
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (box_w, box_h), COLOR_HUD_BG, -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        for i, line in enumerate(lines):
            cv2.putText(
                frame, line,
                (pad, pad + (i + 1) * 20),
                self.font, self.font_small,
                (220, 220, 220), 1, cv2.LINE_AA,
            )

    def _put_label(
        self,
        frame: np.ndarray,
        text: str,
        pos: tuple,
        color: tuple,
        scale: float,
    ) -> None:
        """Draw text with a semi-transparent dark background box."""
        (tw, th), bl = cv2.getTextSize(text, self.font, scale, 1)
        x, y = pos
        # clip to frame
        x = max(x, 0)
        y = max(y, th + 2)
        # background
        cv2.rectangle(frame, (x - 2, y - th - 2), (x + tw + 2, y + bl), (0, 0, 0), -1)
        cv2.putText(frame, text, (x, y), self.font, scale, color, 1, cv2.LINE_AA)
