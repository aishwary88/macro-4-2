"""
Geometry utility functions: distance calculations, line crossing, bounding box math.
"""

import numpy as np
from typing import Tuple, Optional


def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points.

    Args:
        p1: (x, y) first point.
        p2: (x, y) second point.

    Returns:
        Distance as float.
    """
    return float(np.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2))


def bbox_center(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Calculate center point of a bounding box.

    Args:
        bbox: (x1, y1, x2, y2) bounding box.

    Returns:
        (center_x, center_y) tuple.
    """
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def bbox_bottom_center(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """Calculate bottom-center point of a bounding box.
    Useful for tracking ground contact point of vehicles.

    Args:
        bbox: (x1, y1, x2, y2) bounding box.

    Returns:
        (bottom_center_x, bottom_center_y) tuple.
    """
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, y2)


def bbox_area(bbox: Tuple[float, float, float, float]) -> float:
    """Calculate area of a bounding box.

    Args:
        bbox: (x1, y1, x2, y2) bounding box.

    Returns:
        Area in pixels.
    """
    x1, y1, x2, y2 = bbox
    return max(0, x2 - x1) * max(0, y2 - y1)


def iou(bbox1: Tuple[float, float, float, float], bbox2: Tuple[float, float, float, float]) -> float:
    """Calculate Intersection over Union (IoU) between two bounding boxes.

    Args:
        bbox1: (x1, y1, x2, y2) first bounding box.
        bbox2: (x1, y1, x2, y2) second bounding box.

    Returns:
        IoU value between 0 and 1.
    """
    x1 = max(bbox1[0], bbox2[0])
    y1 = max(bbox1[1], bbox2[1])
    x2 = min(bbox1[2], bbox2[2])
    y2 = min(bbox1[3], bbox2[3])

    inter_area = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = bbox_area(bbox1)
    area2 = bbox_area(bbox2)
    union_area = area1 + area2 - inter_area

    if union_area == 0:
        return 0.0

    return inter_area / union_area


def point_crosses_line(
    prev_pos: Tuple[float, float],
    curr_pos: Tuple[float, float],
    line_y: float,
) -> Optional[str]:
    """Check if a point crossed a horizontal line between two frames.

    Args:
        prev_pos: (x, y) previous position.
        curr_pos: (x, y) current position.
        line_y: Y-coordinate of the horizontal line.

    Returns:
        'down' if crossing downward, 'up' if crossing upward, None if no crossing.
    """
    prev_y = prev_pos[1]
    curr_y = curr_pos[1]

    if prev_y <= line_y < curr_y:
        return "down"
    elif prev_y >= line_y > curr_y:
        return "up"

    return None


def point_in_polygon(point: Tuple[float, float], polygon: list) -> bool:
    """Check if a point is inside a polygon using ray casting algorithm.

    Args:
        point: (x, y) point to check.
        polygon: List of (x, y) vertices.

    Returns:
        True if point is inside polygon.
    """
    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside
