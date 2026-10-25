"""Pydantic data models passed between pipeline stages (HLD Section 5).

Stages exchange these models only; never raw dicts.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

CATEGORIES: tuple[str, ...] = (
    "CONFIDENTIALITY",
    "TERMINATION",
    "PAYMENT",
    "LIABILITY",
    "INDEMNIFICATION",
    "IP",
    "GOVERNING_LAW",
    "RENEWAL",
    "SLA",
    "OTHER",
)
CONTRACT_TYPES: tuple[str, ...] = ("VENDOR_SERVICE", "NDA", "SAAS_LICENSE", "OTHER")

ClauseKind = Literal["BODY", "DEFINITIONS", "PREAMBLE", "SIGNATURE", "EXHIBIT"]
Status = Literal["COMPLIANT", "NON_COMPLIANT", "MISSING", "NEEDS_REVIEW", "NOT_APPLICABLE"]
Severity = Literal["HIGH", "MEDIUM", "LOW"]
PipelineStage = Literal[
    "QUEUED",
    "EXTRACTING",
    "SEGMENTING",
    "CLASSIFYING",
    "EVALUATING",
    "EXPLAINING",
    "DONE",
    "FAILED",
]


class Block(BaseModel):
    text: str
    page: int | None = None  # 1-based; None for DOCX
    para_index: int | None = None  # DOCX paragraph index; None for PDF
    is_ocr: bool = False
    ocr_confidence: float | None = None  # 0-100 mean word confidence
    style: str | None = None  # DOCX paragraph style, e.g. "Heading 2" (segmentation hint)


class Document(BaseModel):
    source_path: str
    file_type: Literal["pdf", "docx"]
    num_pages: int | None = None
    blocks: list[Block]
    ocr_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TextSpan(BaseModel):
    """Where a stretch of cleaned text came from: [start, end) offsets into CleanedText.text."""

    start: int
    end: int
    block_index: int  # index into Document.blocks
    page: int | None = None
    para_index: int | None = None
    is_ocr: bool = False


class CleanedText(BaseModel):
    """Cleaned full text plus the offset map back to pages / paragraphs (HLD 6.2).

    Blocks are separated by a blank line ("\n\n"); lines inside a block by "\n".
    """

    text: str
    spans: list[TextSpan]
    file_type: Literal["pdf", "docx"]
    removed_lines: list[str] = Field(default_factory=list)  # repeating headers/footers dropped

    def span_at(self, offset: int) -> TextSpan | None:
        """The span containing ``offset``, or the nearest one before it (offsets in separators)."""
        best: TextSpan | None = None
        for span in self.spans:
            if span.start <= offset:
                best = span
            if span.start <= offset < span.end:
                return span
        return best

    def pages_for(self, start: int, end: int) -> tuple[int | None, int | None]:
        """First and last page touched by the character range [start, end)."""
        pages = [
            s.page for s in self.spans if s.page is not None and s.start < end and s.end > start
        ]
        return (min(pages), max(pages)) if pages else (None, None)


class Clause(BaseModel):
    clause_id: str  # "c001", "c002", ... in reading order
    number: str | None = None  # "7", "7.2", None if unnumbered
    heading: str | None = None
    text: str  # heading + body, cleaned
    page_start: int | None = None
    page_end: int | None = None
    section_path: str  # "7 > 7.2"; always set, used as location for DOCX
    char_start: int
    char_end: int
    kind: ClauseKind = "BODY"
    is_ocr: bool = False
    categories: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    low_confidence: bool = False
    classified_by: Literal["classifier", "embedding_fallback", "rule", "none"] = "none"


class Party(BaseModel):
    name: str
    alias: str | None = None
    role: Literal["OUR_ORG", "COUNTERPARTY", "UNKNOWN"] = "UNKNOWN"


class ContractMeta(BaseModel):
    contract_type: str
    contract_type_source: Literal["user", "auto"]
    parties: list[Party] = Field(default_factory=list)
    effective_date: date | None = None
    expiry_date: date | None = None
    term_text: str | None = None
    governing_law: str | None = None
    title: str | None = None


class Fact(BaseModel):
    key: str  # e.g. "termination.notice_days"
    value: bool | int | float | str | None = None
    unit: str | None = None
    clause_ids: list[str] = Field(default_factory=list)
    evidence_text: str | None = None
    ambiguous: bool = False
    note: str | None = None


class Explanation(BaseModel):
    summary: str
    explanation: str
    why_it_matters: str
    suggested_review_action: str
    quoted_evidence: str  # verbatim substring of clause text ("" for MISSING)
    source: Literal["llm", "template"]
    model: str | None = None
    prompt_version: str


class Finding(BaseModel):
    rule_id: str
    rule_name: str
    category: str
    status: Status
    severity: Severity | None = None  # None when COMPLIANT / NOT_APPLICABLE
    expected: str | None = None
    found: str | None = None
    clause_ids: list[str] = Field(default_factory=list)
    location: str | None = None
    evidence_text: str | None = None
    reason: str
    explanation: Explanation | None = None


class Report(BaseModel):
    contract_id: str
    filename: str
    meta: ContractMeta
    clauses: list[Clause]
    clause_checklist: dict[str, bool]
    findings: list[Finding]
    counts: dict[str, int]
    executive_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    policy_id: str
    policy_version: str
    pipeline_version: str
    generated_at: datetime
    disclaimer: str
    # Additive fields (D41): shown on the UI overview card and used for E8 timing.
    file_type: Literal["pdf", "docx"] | None = None
    num_pages: int | None = None
    ocr_pages: list[int] = Field(default_factory=list)
    llm_used: bool = False
    timings_s: dict[str, float] = Field(default_factory=dict)
