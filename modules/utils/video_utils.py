"""
Video utility functions: frame extraction, FPS handling, video info.
"""

import cv2
from dataclasses import dataclass
from typing import Generator, Tuple, Optional
from modules.utils.logger import get_logger

logger = get_logger("video_utils")


@dataclass
class Frame:
    """Represents a single video frame with metadata."""
    frame_id: int
    timestamp: float       # seconds since video start
    image: object          # numpy ndarray (cv2 frame)


@dataclass
class VideoInfo:
    """Video metadata."""
    fps: float
    width: int
    height: int
    total_frames: int
    duration: float        # seconds


def get_video_info(video_path: str) -> Optional[VideoInfo]:
    """Extract video metadata.

    Args:
        video_path: Path to video file.

    Returns:
        VideoInfo object or None if video can't be opened.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Cannot open video: {video_path}")
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0

    cap.release()

    info = VideoInfo(
        fps=fps,
        width=width,
        height=height,
        total_frames=total_frames,
        duration=duration,
    )
    logger.info(f"Video info: {width}x{height} @ {fps:.1f}fps, {total_frames} frames, {duration:.1f}s")
    return info


def extract_frames(video_path: str, skip: int = 0) -> Generator[Frame, None, None]:
    """Extract frames from video as a generator.

    Args:
        video_path: Path to video file.
        skip: Process every Nth frame (0 = no skip, 1 = every other frame).

    Yields:
        Frame objects with frame_id, timestamp, and image.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Cannot open video: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_id = 0

    while True:
        ret, image = cap.read()
        if not ret:
            break

        if skip > 0 and frame_id % (skip + 1) != 0:
            frame_id += 1
            continue

        timestamp = frame_id / fps

        yield Frame(
            frame_id=frame_id,
            timestamp=timestamp,
            image=image,
        )

        frame_id += 1

    cap.release()
    logger.info(f"Extracted {frame_id} frames from {video_path}")


def create_video_writer(
    output_path: str,
    fps: float,
    size: Tuple[int, int],
    codec: str = "mp4v",
) -> cv2.VideoWriter:
    """Create a video writer for output.

    Args:
        output_path: Path for output video.
        fps: Frames per second.
        size: (width, height) tuple.
        codec: FourCC codec string.

    Returns:
        cv2.VideoWriter object.
    """
    fourcc = cv2.VideoWriter_fourcc(*codec)
    writer = cv2.VideoWriter(output_path, fourcc, fps, size)
    logger.info(f"Video writer created: {output_path} ({size[0]}x{size[1]} @ {fps:.1f}fps)")
    return writer
