"""
System-wide constants: thresholds, labels, color mappings.
These are fixed values that don't change between deployments.
"""

# ========================================
# YOLO COCO Vehicle Class IDs
# ========================================
VEHICLE_CLASS_IDS = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

# ========================================
# Vehicle Type Standardization Map
# ========================================
CLASS_MAP = {
    "car": "Car",
    "suv": "Car",
    "sedan": "Car",
    "motorcycle": "Bike",
    "motorbike": "Bike",
    "bus": "Bus",
    "truck": "Truck",
    "lorry": "Truck",
}

# ========================================
# Speed Thresholds (for visualization colors)
# ========================================
SPEED_LIMIT_KMH = 60        # km/h — configurable via .env/settings
SPEED_NORMAL_MAX = 60       # km/h — green
SPEED_WARNING_MAX = 90      # km/h — orange
# Above 90 = red (overspeed)

# ========================================
# Visualization Colors (BGR for OpenCV)
# ========================================
COLOR_GREEN = (0, 255, 0)
COLOR_ORANGE = (0, 165, 255)
COLOR_RED = (0, 0, 255)
COLOR_CYAN = (255, 255, 0)
COLOR_YELLOW = (0, 255, 255)
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_ROI_LINE = (255, 0, 255)      # Magenta for ROI lines
COLOR_TRACK_TRAIL = (255, 200, 0)   # Light cyan for tracking trail

# Renderer aliases
COLOR_OVERSPEED  = COLOR_RED        # Red for overspeeding vehicles
COLOR_NORMAL     = COLOR_GREEN      # Green for normal vehicles
COLOR_TRACK      = COLOR_TRACK_TRAIL
COLOR_PLATE_TEXT = COLOR_YELLOW     # Yellow for plate text
COLOR_HUD_BG     = (10, 10, 10)    # Near-black HUD background

# ========================================
# Excel Report Colors (Hex for OpenPyXL)
# ========================================
EXCEL_RED = "FF4444"
EXCEL_GREEN = "44FF44"
EXCEL_HEADER_BG = "1E293B"
EXCEL_HEADER_FG = "FFFFFF"

# ========================================
# Detection Defaults
# ========================================
MIN_DETECTION_AREA = 300        # Minimum bbox area in pixels (lowered for distant vehicles)
MAX_TRACKING_DISTANCE = 150     # Max pixel distance for tracking match
TRACK_HISTORY_LENGTH = 30       # Number of past positions to store

# ========================================
# Indian License Plate Regex Pattern
# ========================================
# Format: XX00XX0000 (state code + district number + series + registration)
# Examples: MH12AB1234, DL3CAY2231, KA05MG1909
PLATE_REGEX = r'^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$'

# ========================================
# Processing Status
# ========================================
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
