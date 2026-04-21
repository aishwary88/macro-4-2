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

    Pipeline:
      1. Upscale to standard height (keeps aspect ratio)
      2. Grayscale
      3. CLAHE (contrast limited adaptive histogram equalization)
      4. Bilateral filter (noise reduction, edge preserving)
      5. Adaptive threshold → clean binary image

    Args:
        image: Plate region image (BGR).

    Returns:
        Preprocessed grayscale image ready for OCR.
    """
    if image is None or image.size == 0:
        return image

    # 1. Upscale — OCR works much better on larger images
    h, w = image.shape[:2]
    target_h = 64  # standard plate height for OCR
    if h < target_h:
        scale = target_h / h
        new_w = int(w * scale)
        image = cv2.resize(image, (new_w, target_h), interpolation=cv2.INTER_CUBIC)

    # 2. Grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()

    # 3. CLAHE — improves contrast on uneven lighting
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)

    # 4. Bilateral filter — removes noise while keeping text edges sharp
    filtered = cv2.bilateralFilter(enhanced, 9, 75, 75)

    # 5. Adaptive threshold — handles varying illumination across the plate
    binary = cv2.adaptiveThreshold(
        filtered, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15, 8
    )

    # 6. Morphological close — fills small gaps in characters
    kernel  = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    return cleaned


def preprocess_plate_variants(image: np.ndarray) -> list:
    """Return multiple preprocessed variants of a plate image.

    OCR is run on all variants and results are combined.
    Returns list of images: [original_resized, binary, inverted_binary, gray_enhanced]
    """
    if image is None or image.size == 0:
        return []

    variants = []

    # Upscale
    h, w = image.shape[:2]
    if h < 64:
        scale = 64 / h
        image = cv2.resize(image, (int(w * scale), 64), interpolation=cv2.INTER_CUBIC)

    # Variant 1: original resized (color)
    variants.append(image)

    # Variant 2: standard binary
    variants.append(preprocess_plate(image))

    # Variant 3: inverted binary (white text on black bg)
    binary = preprocess_plate(image)
    variants.append(cv2.bitwise_not(binary))

    # Variant 4: grayscale with CLAHE only (no threshold)
    gray   = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
    clahe  = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    variants.append(clahe.apply(gray))

    return variants


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
