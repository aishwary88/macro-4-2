"""Tests for the vehicle tracking module."""

import pytest
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class MockDetection:
    bbox: Tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str


@pytest.fixture
def dummy_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def mock_detections():
    return [
        MockDetection((100, 100, 200, 200), 0.9, 2, "car"),
        MockDetection((300, 150, 450, 280), 0.85, 7, "truck"),
    ]


class TestVehicleTracker:

    def test_tracker_initializes(self):
        from modules.tracking.tracker import VehicleTracker
        tracker = VehicleTracker()
        assert tracker is not None

    def test_update_returns_list(self, mock_detections, dummy_frame):
        from modules.tracking.tracker import VehicleTracker
        tracker = VehicleTracker()
        result = tracker.update(mock_detections, dummy_frame)
        assert isinstance(result, list)

    def test_tracked_vehicles_have_ids(self, mock_detections, dummy_frame):
        from modules.tracking.tracker import VehicleTracker
        tracker = VehicleTracker()
        tracked = tracker.update(mock_detections, dummy_frame)
        for v in tracked:
            assert hasattr(v, 'vehicle_id')
            assert isinstance(v.vehicle_id, int)

    def test_id_stability_across_frames(self, mock_detections, dummy_frame):
        """Same object detected in two consecutive frames should retain ID."""
        from modules.tracking.tracker import VehicleTracker
        tracker = VehicleTracker()
        first  = tracker.update(mock_detections, dummy_frame)
        second = tracker.update(mock_detections, dummy_frame)

        first_ids  = {v.vehicle_id for v in first}
        second_ids = {v.vehicle_id for v in second}
        # At least some IDs should persist
        assert len(first_ids & second_ids) > 0, "No IDs persisted across frames"
