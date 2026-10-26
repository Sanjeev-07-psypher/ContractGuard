"""Errors that carry a stable code and a message a reviewer can read.

The API turns these into ``{error_code, message}`` responses (HLD 10.2); the CLI prints the message.
"""

from __future__ import annotations


class ContractGuardError(Exception):
    """Base class. ``code`` is stable for clients; ``message`` is shown to users."""

    code = "CONTRACTGUARD_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class IngestionError(ContractGuardError):
    """The file cannot be turned into a Document (type, size, encryption, corruption, OCR)."""

    code = "INGESTION_ERROR"

    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    TOO_MANY_WORDS = "TOO_MANY_WORDS"
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    CORRUPT_FILE = "CORRUPT_FILE"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"


class PolicyError(ContractGuardError):
    """A policy file is missing, unreadable or fails schema validation."""

    code = "POLICY_ERROR"

    NOT_FOUND = "POLICY_NOT_FOUND"
    INVALID = "POLICY_INVALID"


class ModelArtifactError(ContractGuardError):
    """A trained artifact (classifier, thresholds, prototypes) is missing or unreadable."""

    code = "MODEL_ARTIFACT_ERROR"
