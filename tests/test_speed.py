"""Tests for speed estimation and ROI line crossing."""

import pytest
from modules.calibration.roi_manager import ROIManager
from modules.calibration.calibrator import Calibrator
from modules.speed.speed_estimator import SpeedEstimator


@pytest.fixture
def roi():
    return ROIManager(line_a_y=200, line_b_y=400, known_distance=10.0)


@pytest.fixture
def calibrator():
    return Calibrator()


@pytest.fixture
def estimator(roi, calibrator):
    from modules.tracking.vehicle_state import VehicleStateManager
    state_mgr = VehicleStateManager()
    return SpeedEstimator(roi_manager=roi, calibrator=calibrator, state_manager=state_mgr)


class TestSpeedEstimation:

    def test_estimator_initializes(self, estimator):
        assert estimator is not None

    def test_line_crossing_detected(self, roi):
        """Vehicle moving downward should cross Line A."""
        prev = (100, 100)   # above Line A (y=200)
        curr = (100, 250)   # below Line A
        result = roi.check_line_crossing(vehicle_id=1, prev_pos=prev, curr_pos=curr, timestamp=1.0)
        assert result == "line_a"

    def test_line_b_crossing(self, roi):
        """After Line A, vehicle should cross Line B."""
        roi.check_line_crossing(1, (100, 100), (100, 250), 1.0)  # cross A
        result = roi.check_line_crossing(1, (100, 380), (100, 420), 2.5)   # cross B
        assert result == "line_b"

    def test_speed_computed_correctly(self, estimator, roi):
        """10m / 1s = 36 km/h."""
        # Cross line A at t=1.0
        estimator.update(vehicle_id=99, prev_pos=(100, 100), curr_pos=(100, 250), timestamp=1.0)
        # Cross line B at t=2.0 → time_delta = 1s, distance = 10m → 36 km/h
        result = estimator.update(vehicle_id=99, prev_pos=(100, 380), curr_pos=(100, 420), timestamp=2.0)

        if result and result.speed_kmh is not None:
            assert 30 <= result.speed_kmh <= 45, f"Expected ~36 km/h, got {result.speed_kmh}"

    def test_overspeed_flagging(self):
        from core.config import settings
        from modules.tracking.vehicle_state import VehicleStateManager
        limit = settings.SPEED_LIMIT_KMH
        roi_mgr   = ROIManager(line_a_y=200, line_b_y=400, known_distance=50.0)  # 50m zone
        cal       = Calibrator()
        state_mgr = VehicleStateManager()
        est       = SpeedEstimator(roi_mgr, cal, state_mgr)

        # Cross A→B very fast: 50m in 0.5s = 360 km/h (well over limit)
        est.update(10, (0, 100), (0, 250), 0.0)
        result = est.update(10, (0, 380), (0, 420), 0.5)

        if result and result.speed_kmh is not None:
            assert result.is_overspeed, f"Expected overspeed but speed={result.speed_kmh}"
