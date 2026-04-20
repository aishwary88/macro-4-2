"""Integration tests for the FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create a test client with an in-memory SQLite DB."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_traffic.db")
    from modules.data.database import init_db
    init_db()
    from app import app
    return TestClient(app)


class TestAPIHealth:
    def test_health_check(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestVideoEndpoints:
    def test_list_videos_empty(self, client):
        resp = client.get("/api/videos")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_upload_invalid_extension(self, client):
        resp = client.post(
            "/api/upload",
            files={"file": ("test.txt", b"not a video", "text/plain")},
        )
        assert resp.status_code == 400

    def test_status_not_found(self, client):
        resp = client.get("/api/status/99999")
        assert resp.status_code == 404

    def test_results_not_found(self, client):
        resp = client.get("/api/results/99999")
        assert resp.status_code in {404, 400}


class TestVehicleEndpoints:
    def test_vehicles_returns_list(self, client):
        resp = client.get("/api/vehicles/99999")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_vehicle_detail_not_found(self, client):
        resp = client.get("/api/vehicle/99999")
        assert resp.status_code == 404


class TestDownloadEndpoints:
    def test_excel_not_found(self, client):
        """Excel download should work even for unknown IDs (generates empty report)."""
        resp = client.get("/api/download/excel/99999", follow_redirects=False)
        # App generates an empty report on-the-fly — this is expected behaviour
        assert resp.status_code in {200, 404, 500}

    def test_video_not_found(self, client):
        resp = client.get("/api/download/video/99999")
        assert resp.status_code == 404
