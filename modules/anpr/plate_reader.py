"""
License plate reader using EasyOCR.
Extracts text from plate images with post-processing for Indian plate format.
"""

import re
import numpy as np
from dataclasses import dataclass
from typing import Optional
from modules.utils.image_utils import preprocess_plate
from modules.utils.logger import get_logger
from core.constants import PLATE_REGEX

logger = get_logger("plate_reader")


@dataclass
class PlateData:
    """License plate reading result."""
    plate_number: str
    confidence: float
    raw_text: str


class PlateReader:
    """EasyOCR-based license plate text reader.

    Features:
    - Image preprocessing pipeline for better OCR
    - Post-processing with regex matching for Indian plates
    - Confidence thresholding
    """

    def __init__(self, min_confidence: float = 0.3):
        """Initialize plate reader.

        Args:
            min_confidence: Minimum OCR confidence threshold.
        """
        from core.dependencies import get_ocr_reader
        self.reader = get_ocr_reader()
        self.min_confidence = min_confidence
        self._plate_pattern = re.compile(PLATE_REGEX)
        logger.info(f"PlateReader initialized (min_confidence={min_confidence})")

    def read_plate(self, plate_image: np.ndarray) -> Optional[PlateData]:
        """Read text from a plate image.

        Args:
            plate_image: Cropped plate region (BGR).

        Returns:
            PlateData with plate text and confidence, or None.
        """
        if plate_image is None or plate_image.size == 0:
            return None

        try:
            # Preprocess for better OCR
            preprocessed = preprocess_plate(plate_image)

            # Run OCR on both original and preprocessed
            results = self.reader.readtext(plate_image)
            results_preprocessed = self.reader.readtext(preprocessed)

            # Combine results
            all_results = results + results_preprocessed

            if not all_results:
                return None

            # Find best result
            best_text = ""
            best_confidence = 0.0

            for result in all_results:
                if len(result) < 3:
                    continue

                _, text, confidence = result

                if confidence < self.min_confidence:
                    continue

                # Clean text: remove spaces and special chars
                cleaned = self._clean_plate_text(text)

                if len(cleaned) < 3:
                    continue

                if confidence > best_confidence:
                    best_text = cleaned
                    best_confidence = confidence

            if not best_text:
                return None

            plate_data = PlateData(
                plate_number=best_text,
                confidence=best_confidence,
                raw_text=best_text,
            )

            logger.debug(f"Plate read: {best_text} (confidence: {best_confidence:.2f})")
            return plate_data

        except Exception as e:
            logger.debug(f"Plate reading error: {e}")
            return None

    def _clean_plate_text(self, text: str) -> str:
        """Clean and normalize plate text.

        Args:
            text: Raw OCR output.

        Returns:
            Cleaned plate text.
        """
        # Remove spaces and non-alphanumeric characters
        cleaned = re.sub(r'[^A-Za-z0-9]', '', text.upper().strip())

        # Common OCR corrections
        corrections = {
            'O': '0',  # O to 0 (in number positions)
            'I': '1',  # I to 1
            'S': '5',  # S to 5
            'B': '8',  # B to 8
        }

        # Apply corrections only to likely-numeric positions
        # Indian format: XX00XX0000 — positions 2-3 and 6-9 are numbers
        result = list(cleaned)
        for i, char in enumerate(result):
            if i in [2, 3] and char in corrections:
                result[i] = corrections[char]

        return ''.join(result)

    def validate_plate(self, plate_text: str) -> bool:
        """Validate if plate text matches Indian plate format.

        Args:
            plate_text: Plate text to validate.

        Returns:
            True if valid format.
        """
        return bool(self._plate_pattern.match(plate_text))
