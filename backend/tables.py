"""SQLite tables (HLD 10.3). The whole report is stored as JSON for the UI; clauses and findings
are also stored row by row for filtering."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class ContractRow(SQLModel, table=True):
    __tablename__ = "contracts"

    id: str = Field(primary_key=True)
    filename: str
    file_type: str
    status: str = "QUEUED"
    stage: str = "QUEUED"
    progress: int = 0
    error: str | None = None
    contract_type: str | None = None
    our_org_name: str | None = None
    policy_id: str
    policy_version: str | None = None
    use_llm: bool = True
    created_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    report_json: str | None = None
    counts_json: str | None = None


class ClauseRow(SQLModel, table=True):
    __tablename__ = "clauses"

    id: int | None = Field(default=None, primary_key=True)
    contract_id: str = Field(foreign_key="contracts.id", index=True)
    clause_id: str
    number: str | None = None
    heading: str | None = None
    text: str
    page_start: int | None = None
    page_end: int | None = None
    section_path: str
    kind: str
    categories_json: str
    scores_json: str
    low_confidence: bool
    classified_by: str


class FindingRow(SQLModel, table=True):
    __tablename__ = "findings"

    id: int | None = Field(default=None, primary_key=True)
    contract_id: str = Field(foreign_key="contracts.id", index=True)
    rule_id: str
    status: str
    severity: str | None = None
    expected: str | None = None
    found: str | None = None
    location: str | None = None
    evidence_text: str | None = None
    reason: str
    explanation_json: str | None = None


class LLMCacheRow(SQLModel, table=True):
    """Same schema as ``contractguard.llm.explainer.LLMCache``, which reads and writes it."""

    __tablename__ = "llm_cache"

    key: str = Field(primary_key=True)
    response_json: str
    model: str | None = None
    created_at: str
