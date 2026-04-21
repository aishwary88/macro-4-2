"""
License plate OCR using EasyOCR.

Pipeline:
  1. Run OCR on multiple preprocessed image variants
  2. Clean and normalize each result
  3. Apply position-aware character corrections
  4. Validate against Indian plate format regex
  5. Return best result by confidence
"""

import re
import numpy as np
from collections import Counter
from dataclasses import dataclass
from typing import Optional, List, Tuple
from modules.utils.image_utils import preprocess_plate_variants
from modules.utils.logger import get_logger
from core.constants import PLATE_REGEX

logger = get_logger("plate_reader")


@dataclass
class PlateData:
    """License plate reading result."""
    plate_number: str
    confidence: float
    raw_text: str
    is_valid: bool = False   # True if matches Indian plate format


class PlateReader:
    """EasyOCR-based license plate text reader with multi-variant OCR."""

    def __init__(self, min_confidence: float = 0.3):
        from core.dependencies import get_ocr_reader
        self.reader         = get_ocr_reader()
        self.min_confidence = min_confidence
        self._plate_pattern = re.compile(PLATE_REGEX)
        logger.info(f"PlateReader initialized (min_confidence={min_confidence})")

    # ------------------------------------------------------------------
    def read_plate(self, plate_image: np.ndarray) -> Optional[PlateData]:
        """Read text from a plate image using multi-variant OCR.

        Args:
            plate_image: Cropped plate region (BGR).

        Returns:
            PlateData with best plate text and confidence, or None.
        """
        if plate_image is None or plate_image.size == 0:
            return None

        try:
            variants = preprocess_plate_variants(plate_image)
            if not variants:
                return None

            all_candidates: List[Tuple[str, float]] = []

            for variant in variants:
                results = self.reader.readtext(variant, detail=1, paragraph=False)
                for item in results:
                    if len(item) < 3:
                        continue
                    _, text, conf = item
                    if conf < self.min_confidence:
                        continue
                    cleaned = self._clean_plate_text(text)
                    if len(cleaned) >= 4:
                        all_candidates.append((cleaned, float(conf)))

            if not all_candidates:
                return None

            # Prefer valid-format plates; fall back to best confidence
            valid = [(p, c) for p, c in all_candidates if self._is_valid(p)]
            pool  = valid if valid else all_candidates

            # Pick highest confidence
            best_plate, best_conf = max(pool, key=lambda x: x[1])

            return PlateData(
                plate_number=best_plate,
                confidence=best_conf,
                raw_text=best_plate,
                is_valid=self._is_valid(best_plate),
            )

        except Exception as e:
            logger.debug(f"Plate reading error: {e}")
            return None

    # ------------------------------------------------------------------
    def _clean_plate_text(self, text: str) -> str:
        """Clean OCR output and apply position-aware character corrections.

        Indian plate format: XX 00 XX 0000
          pos 0-1  : state code  → letters only
          pos 2-3  : district    → digits only
          pos 4-6  : series      → letters only
          pos 7-10 : number      → digits only
        """
        # Remove everything except alphanumeric
        cleaned = re.sub(r'[^A-Za-z0-9]', '', text.upper().strip())

        if len(cleaned) < 4:
            return cleaned

        chars = list(cleaned)

        # Letter → digit corrections (for digit positions)
        L2D = {'O': '0', 'I': '1', 'Z': '2', 'S': '5', 'B': '8', 'G': '6', 'T': '7'}
        # Digit → letter corrections (for letter positions)
        D2L = {'0': 'O', '1': 'I', '5': 'S', '8': 'B', '6': 'G'}

        # Apply corrections based on expected position in Indian plate
        for i, ch in enumerate(chars):
            if i < 2:
                # State code: must be letters
                if ch.isdigit():
                    chars[i] = D2L.get(ch, ch)
            elif i < 4:
                # District number: must be digits
                if ch.isalpha():
                    chars[i] = L2D.get(ch, ch)
            elif i < 7:
                # Series: must be letters
                if ch.isdigit():
                    chars[i] = D2L.get(ch, ch)
            else:
                # Registration number: must be digits
                if ch.isalpha():
                    chars[i] = L2D.get(ch, ch)

        return ''.join(chars)

    # ------------------------------------------------------------------
    def _is_valid(self, plate: str) -> bool:
        """Check if plate matches Indian registration format."""
        return bool(self._plate_pattern.match(plate))

    # ------------------------------------------------------------------
    def validate_plate(self, plate_text: str) -> bool:
        return self._is_valid(plate_text)
