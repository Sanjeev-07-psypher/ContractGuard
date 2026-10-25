"""Tesseract OCR for scanned PDF pages (HLD 6.1).

Pages are rendered with PyMuPDF (no poppler), converted to grayscale and read with
``--oem 1 --psm 6``. One result paragraph per Tesseract paragraph keeps block structure.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from functools import lru_cache

import pymupdf
from PIL import Image

from contractguard.config import OCRSettings
from contractguard.errors import IngestionError

log = logging.getLogger(__name__)

TESSERACT_CONFIG = "--oem 1 --psm 6"


@dataclass(frozen=True)
class OcrResult:
    paragraphs: list[str]
    confidence: float | None  # mean confidence (0-100) of words with conf > 0


@lru_cache(maxsize=4)
def tesseract_available(tesseract_cmd: str | None = None) -> bool:
    """True if the Tesseract binary can be run. Cached: checked once per command."""
    try:
        import pytesseract
    except ImportError:
        return False
    # pytesseract keeps the command in module state; always set it so an earlier custom
    # path never leaks into a later default check.
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd or "tesseract"
    if not tesseract_cmd and shutil.which("tesseract") is None:
        return False
    try:
        pytesseract.get_tesseract_version()
    except Exception:  # binary missing or broken
        return False
    return True


def render_page(page: pymupdf.Page, dpi: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def ocr_image(image: Image.Image, settings: OCRSettings) -> OcrResult:
    """Read ``image`` with Tesseract. Raises IngestionError if Tesseract is not available."""
    if not tesseract_available(settings.tesseract_cmd):
        raise IngestionError(
            "This PDF contains scanned pages, but Tesseract OCR is not installed or not found. "
            "Install Tesseract 5 or set ocr.tesseract_cmd.",
            IngestionError.OCR_UNAVAILABLE,
        )
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd or "tesseract"
    data = pytesseract.image_to_data(
        image, lang=settings.lang, config=TESSERACT_CONFIG, output_type=pytesseract.Output.DICT
    )
    paragraphs: dict[tuple[int, int], dict[int, list[str]]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        if not word:
            continue
        conf = float(data["conf"][i])
        if conf > 0:
            confidences.append(conf)
        key = (data["block_num"][i], data["par_num"][i])
        paragraphs.setdefault(key, {}).setdefault(data["line_num"][i], []).append(word)
    texts = [
        "\n".join(" ".join(words) for _, words in sorted(lines.items()))
        for _, lines in sorted(paragraphs.items())
    ]
    confidence = sum(confidences) / len(confidences) if confidences else None
    return OcrResult(paragraphs=texts, confidence=confidence)


def ocr_page(page: pymupdf.Page, settings: OCRSettings) -> OcrResult:
    return ocr_image(render_page(page, settings.dpi), settings)
