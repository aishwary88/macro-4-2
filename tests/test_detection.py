"""Tests for the vehicle detection module."""

import pytest
import numpy as np
import os


@pytest.fixture
def dummy_frame():
    """Create a blank test frame (480x640 BGR)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


class TestVehicleDetector:

    def test_detector_initializes(self):
        """VehicleDetector should initialize without raising."""
        from modules.detection.detector import VehicleDetector
        from core.config import settings

        if not os.path.exists(settings.YOLO_MODEL_PATH):
            pytest.skip("YOLO model file not present; skipping live model test.")

        detector = VehicleDetector(settings.YOLO_MODEL_PATH, 0.5)
        assert detector is not None

    def test_detect_returns_list(self, dummy_frame):
        """detect() must return a list (possibly empty on blank frame)."""
        from modules.detection.detector import VehicleDetector
        from core.config import settings

        if not os.path.exists(settings.YOLO_MODEL_PATH):
            pytest.skip("YOLO model file not present.")

        detector = VehicleDetector(settings.YOLO_MODEL_PATH, 0.5)
        results = detector.detect(dummy_frame)
        assert isinstance(results, list)

    def test_vehicle_class_filtering(self, dummy_frame):
        """Only vehicle COCO class IDs should pass through."""
        from modules.detection.detector import VehicleDetector
        from core.constants import VEHICLE_CLASS_IDS
        from core.config import settings

        if not os.path.exists(settings.YOLO_MODEL_PATH):
            pytest.skip("YOLO model file not present.")

        detector = VehicleDetector(settings.YOLO_MODEL_PATH, 0.1)
        detections = detector.detect(dummy_frame)
        for d in detections:
            assert d.class_id in VEHICLE_CLASS_IDS, f"Non-vehicle class {d.class_id} slipped through"
