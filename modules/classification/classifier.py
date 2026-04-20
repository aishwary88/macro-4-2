"""
Vehicle type classification: standardizes YOLO labels into clean categories.
"""

from core.constants import CLASS_MAP
from modules.utils.logger import get_logger

logger = get_logger("classification")


class VehicleClassifier:
    """Standardizes vehicle type labels.

    Maps raw YOLO class names to clean, consistent categories:
    - car, suv, sedan → Car
    - truck, lorry → Truck
    - bus → Bus
    - motorcycle, motorbike → Bike
    """

    def __init__(self):
        self._class_map = CLASS_MAP
        logger.info(f"VehicleClassifier initialized with {len(self._class_map)} mappings")

    def classify(self, yolo_class_name: str) -> str:
        """Map a YOLO class name to a standardized vehicle type.

        Args:
            yolo_class_name: Raw class name from YOLO (e.g., 'car', 'truck').

        Returns:
            Standardized type string (e.g., 'Car', 'Truck').
        """
        normalized = yolo_class_name.lower().strip()
        result = self._class_map.get(normalized, "Unknown")
        return result

    def get_categories(self) -> list:
        """Get all possible standardized categories.

        Returns:
            List of unique category names.
        """
        return list(set(self._class_map.values()))
