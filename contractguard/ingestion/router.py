"""Pick the loader for an uploaded file (HLD 6.1).

The extension and the file's magic bytes must agree, so a renamed file is rejected.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from contractguard.config import Settings, get_settings
from contractguard.errors import IngestionError
from contractguard.models import Document

log = logging.getLogger(__name__)

FileType = Literal["pdf", "docx"]
_MAGIC: dict[FileType, bytes] = {"pdf": b"%PDF", "docx": b"PK\x03\x04"}
_EXTENSIONS: dict[str, FileType] = {".pdf": "pdf", ".docx": "docx"}


def detect_file_type(path: Path) -> FileType:
    """Return "pdf" or "docx", or raise IngestionError if the type is unsupported or spoofed."""
    file_type = _EXTENSIONS.get(path.suffix.lower())
    if file_type is None:
        raise IngestionError(
            f"Unsupported file type '{path.suffix or '(none)'}'. Upload a PDF or DOCX file.",
            IngestionError.UNSUPPORTED_FILE_TYPE,
        )
    with path.open("rb") as fh:
        head = fh.read(8)
    if not head.startswith(_MAGIC[file_type]):
        raise IngestionError(
            f"The file content does not match its .{file_type} extension. "
            "It may be renamed or corrupt.",
            IngestionError.UNSUPPORTED_FILE_TYPE,
        )
    return file_type


def check_size(path: Path, settings: Settings) -> None:
    limit = settings.limits.max_file_mb
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > limit:
        raise IngestionError(
            f"The file is {size_mb:.1f} MB; the limit is {limit} MB.",
            IngestionError.FILE_TOO_LARGE,
        )


def load_document(path: str | Path, settings: Settings | None = None) -> Document:
    """Validate ``path`` and load it into a Document."""
    settings = settings or get_settings()
    path = Path(path)
    if not path.is_file():
        raise IngestionError(f"File not found: {path.name}", IngestionError.CORRUPT_FILE)
    file_type = detect_file_type(path)
    check_size(path, settings)
    log.info("loading %s as %s", path.name, file_type)
    if file_type == "pdf":
        from contractguard.ingestion.pdf_loader import load_pdf

        doc = load_pdf(path, settings)
    else:
        from contractguard.ingestion.docx_loader import load_docx

        doc = load_docx(path, settings)
    if not any(b.text.strip() for b in doc.blocks):
        raise IngestionError(
            "No text could be extracted from the file.", IngestionError.EMPTY_DOCUMENT
        )
    return doc
