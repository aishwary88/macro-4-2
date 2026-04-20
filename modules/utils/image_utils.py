"""
Image utility functions: cropping, resizing, preprocessing.
"""

import cv2
import numpy as np
from typing import Tuple, Optional


def crop_region(image: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
    """Crop a region from an image using bounding box.

    Args:
        image: Source image (numpy array).
        bbox: (x1, y1, x2, y2) bounding box coordinates.

    Returns:
        Cropped image or None if region is invalid.
    """
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = image.shape[:2]

    # Clamp to image bounds
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(w, x2)
    y2 = min(h, y2)

    if x2 <= x1 or y2 <= y1:
        return None

    return image[y1:y2, x1:x2].copy()


def resize_image(image: np.ndarray, size: Tuple[int, int]) -> np.ndarray:
    """Resize image to specified size.

    Args:
        image: Source image.
        size: (width, height) target size.

    Returns:
        Resized image.
    """
    return cv2.resize(image, size, interpolation=cv2.INTER_LINEAR)


def preprocess_plate(image: np.ndarray) -> np.ndarray:
    """Preprocess a license plate image for better OCR accuracy.

    Pipeline: grayscale → bilateral filter → adaptive threshold → morphology.

    Args:
        image: Plate region image (BGR).

    Returns:
        Preprocessed grayscale image ready for OCR.
    """
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Bilateral filter (noise reduction while preserving edges)
    filtered = cv2.bilateralFilter(gray, 11, 17, 17)

    # Adaptive threshold
    thresh = cv2.adaptiveThreshold(
        filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

    # Morphological operations to clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    return cleaned


def draw_text_with_bg(
    frame: np.ndarray,
    text: str,
    position: Tuple[int, int],
    font_scale: float = 0.6,
    color: Tuple[int, int, int] = (255, 255, 255),
    bg_color: Tuple[int, int, int] = (0, 0, 0),
    thickness: int = 1,
    padding: int = 5,
) -> np.ndarray:
    """Draw text with a background rectangle for readability.

    Args:
        frame: Image to draw on.
        text: Text string.
        position: (x, y) top-left position.
        font_scale: Font scale.
        color: Text color (BGR).
        bg_color: Background color (BGR).
        thickness: Text thickness.
        padding: Background padding in pixels.

    Returns:
        Frame with text drawn.
    """
    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    x, y = position
    # Draw background rectangle
    cv2.rectangle(
        frame,
        (x - padding, y - text_h - padding),
        (x + text_w + padding, y + baseline + padding),
        bg_color,
        -1,
    )

    # Draw text
    cv2.putText(frame, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)

    return frame
