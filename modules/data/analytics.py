"""
Post-processing analytics: computes summary statistics from vehicle data.
"""

from typing import Dict, List
from modules.data.database import get_vehicles_by_video, get_video
from modules.utils.logger import get_logger

logger = get_logger("analytics")


def compute_analytics(video_id: int) -> dict:
    """Compute comprehensive analytics for a processed video.

    Args:
        video_id: Video ID.

    Returns:
        Dict with analytics data.
    """
    vehicles = get_vehicles_by_video(video_id)
    video = get_video(video_id)

    total = len(vehicles)
    overspeed_count = sum(1 for v in vehicles if v.get("overspeed_flag", False))

    # Type distribution
    types = {}
    for v in vehicles:
        vtype = v.get("vehicle_type", "Unknown")
        types[vtype] = types.get(vtype, 0) + 1

    # Speed stats
    speeds = [v.get("avg_speed", 0) for v in vehicles if v.get("avg_speed", 0) > 0]
    avg_speed = round(sum(speeds) / len(speeds), 2) if speeds else 0
    max_speed = round(max(speeds), 2) if speeds else 0
    min_speed = round(min(speeds), 2) if speeds else 0

    analytics = {
        "video_id": video_id,
        "video_filename": video.get("filename", "Unknown") if video else "Unknown",
        "total_vehicles": total,
        "vehicle_types": types,
        "cars": types.get("Car", 0),
        "trucks": types.get("Truck", 0),
        "buses": types.get("Bus", 0),
        "bikes": types.get("Bike", 0),
        "overspeed_count": overspeed_count,
        "overspeed_percentage": round(
            (overspeed_count / total * 100) if total > 0 else 0, 1
        ),
        "avg_speed": avg_speed,
        "max_speed": max_speed,
        "min_speed": min_speed,
        "duration": video.get("duration", 0) if video else 0,
        "vehicles_with_plates": sum(
            1 for v in vehicles if v.get("plate_number") and v.get("plate_number") != "N/A"
        ),
    }

    logger.info(
        f"Analytics for video {video_id}: "
        f"{total} vehicles, {overspeed_count} overspeeding, "
        f"avg speed {avg_speed} km/h"
    )

    return analytics


def compute_analytics_from_state(state_manager) -> dict:
    """Compute analytics directly from VehicleStateManager (during processing).

    Args:
        state_manager: VehicleStateManager instance.

    Returns:
        Analytics dict.
    """
    return state_manager.get_stats()
