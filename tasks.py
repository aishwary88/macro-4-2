"""
Background task manager — runs video processing in separate threads.
Thread-safe progress tracking with in-memory dict.
"""

import threading
from typing import Dict, Optional
from modules.utils.logger import get_logger
from modules.data.database import update_video_status

logger = get_logger(__name__)

# In-memory task registry: {video_id: {"thread": Thread, "progress": int, "status": str}}
_tasks: Dict[int, dict] = {}
_lock = threading.Lock()


def start_processing(video_id: int, video_path: str) -> None:
    """
    Spawn a background thread to process the given video.
    No-op if a task for this video_id is already running.
    """
    with _lock:
        existing = _tasks.get(video_id)
        if existing and existing["status"] == "running":
            logger.warning(f"Task for video_id={video_id} is already running.")
            return

        _tasks[video_id] = {"status": "running", "progress": 0, "thread": None}

    thread = threading.Thread(
        target=_run_pipeline,
        args=(video_id, video_path),
        daemon=True,
        name=f"pipeline-{video_id}",
    )
    with _lock:
        _tasks[video_id]["thread"] = thread

    thread.start()
    logger.info(f"Background processing started for video_id={video_id}")


def get_task_progress(video_id: int) -> int:
    """Return processing progress (0–100) for the given video."""
    with _lock:
        task = _tasks.get(video_id)
        return task["progress"] if task else 0


def get_task_status(video_id: int) -> Optional[str]:
    """Return task status: 'running' | 'completed' | 'failed' | None."""
    with _lock:
        task = _tasks.get(video_id)
        return task["status"] if task else None


def _progress_callback(video_id: int, progress: int) -> None:
    """Update in-memory progress for the given video."""
    with _lock:
        if video_id in _tasks:
            _tasks[video_id]["progress"] = progress


def _run_pipeline(video_id: int, video_path: str) -> None:
    """Worker function executed in the background thread."""
    try:
        from pipeline import TrafficPipeline
        from modules.data.database import init_db

        init_db()  # ensure tables exist

        pipeline = TrafficPipeline()
        pipeline.process_video(
            video_path=video_path,
            video_id=video_id,
            progress_callback=lambda p: _progress_callback(video_id, p),
        )

        with _lock:
            if video_id in _tasks:
                _tasks[video_id]["status"] = "completed"
                _tasks[video_id]["progress"] = 100

        logger.info(f"Pipeline completed for video_id={video_id}")

    except Exception as exc:
        logger.error(f"Pipeline FAILED for video_id={video_id}: {exc}", exc_info=True)
        with _lock:
            if video_id in _tasks:
                _tasks[video_id]["status"] = "failed"
        update_video_status(video_id, "failed", error_message=str(exc))
