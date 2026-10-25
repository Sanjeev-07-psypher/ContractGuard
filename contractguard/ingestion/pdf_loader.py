"""PDF loading with per-page scanned detection (HLD 6.1).

A page is scanned when its extracted text is shorter than ``ocr.min_chars_per_page`` and it
contains an image; only those pages go to OCR, so mixed PDFs work page by page.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pymupdf

from contractguard.config import OCRSettings, Settings, get_settings
from contractguard.errors import IngestionError
from contractguard.ingestion.ocr import OcrResult, ocr_page
from contractguard.models import Block, Document

log = logging.getLogger(__name__)

OcrFn = Callable[[pymupdf.Page, OCRSettings], OcrResult]
_TEXT_BLOCK = 0  # PyMuPDF block type for text (1 = image)


def _text_blocks(page: pymupdf.Page) -> list[str]:
    """Text blocks in reading order: top to bottom, then left to right."""
    blocks = [b for b in page.get_text("blocks") if b[6] == _TEXT_BLOCK and b[4].strip()]
    blocks.sort(key=lambda b: (round(b[1], 1), b[0]))
    return [b[4].rstrip("\n") for b in blocks]


def is_scanned(page: pymupdf.Page, text_chars: int, settings: OCRSettings) -> bool:
    return text_chars < settings.min_chars_per_page and bool(page.get_images())


def load_pdf(path: Path, settings: Settings | None = None, ocr_fn: OcrFn = ocr_page) -> Document:
    settings = settings or get_settings()
    try:
        pdf = pymupdf.open(path)
    except Exception as exc:  # PyMuPDF raises several types for broken files
        raise IngestionError(
            "The PDF could not be opened; it may be corrupt.", IngestionError.CORRUPT_FILE
        ) from exc
    with pdf:
        if pdf.needs_pass:
            raise IngestionError(
                "Password-protected PDFs are not supported.", IngestionError.ENCRYPTED_PDF
            )
        if pdf.page_count > settings.limits.max_pages:
            raise IngestionError(
                f"The PDF has {pdf.page_count} pages; the limit is {settings.limits.max_pages}.",
                IngestionError.TOO_MANY_PAGES,
            )
        blocks: list[Block] = []
        ocr_pages: list[int] = []
        warnings: list[str] = []
        for index in range(pdf.page_count):
            page = pdf[index]
            number = index + 1
            texts = _text_blocks(page)
            if is_scanned(page, sum(len(t.strip()) for t in texts), settings.ocr):
                result = ocr_fn(page, settings.ocr)
                ocr_pages.append(number)
                conf = result.confidence
                if conf is None or conf < settings.ocr.warn_confidence:
                    shown = "unknown" if conf is None else f"{conf:.0f}%"
                    warnings.append(f"Page {number} OCR confidence {shown} - verify manually")
                blocks.extend(
                    Block(text=t, page=number, is_ocr=True, ocr_confidence=conf)
                    for t in result.paragraphs
                    if t.strip()
                )
            else:
                blocks.extend(Block(text=t, page=number) for t in texts)
        log.info("pdf %s: %d pages, %d OCR pages", path.name, pdf.page_count, len(ocr_pages))
        return Document(
            source_path=str(path),
            file_type="pdf",
            num_pages=pdf.page_count,
            blocks=blocks,
            ocr_pages=ocr_pages,
            warnings=warnings,
        )
