"""Background analysis jobs (HLD 10.2): one at a time, status and progress written to SQLite."""

from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, delete

from backend.tables import ClauseRow, ContractRow, FindingRow
from contractguard.errors import ContractGuardError
from contractguard.models import Report
from contractguard.pipeline import Options, Resources, run

log = logging.getLogger(__name__)

# Only one analysis at a time: avoids CPU / memory spikes and respects LLM rate limits.
JOB_SLOT = threading.Semaphore(1)


def _update(engine: Engine, contract_id: str, **fields: object) -> None:
    with Session(engine) as session:
        row = session.get(ContractRow, contract_id)
        if row is None:  # deleted while running
            return
        for k, v in fields.items():
            setattr(row, k, v)
        session.add(row)
        session.commit()


def store_report(engine: Engine, report: Report) -> None:
    with Session(engine) as session:
        row = session.get(ContractRow, report.contract_id)
        if row is None:
            return
        for c in report.clauses:
            session.add(ClauseRow(
                contract_id=report.contract_id, clause_id=c.clause_id, number=c.number,
                heading=c.heading, text=c.text, page_start=c.page_start, page_end=c.page_end,
                section_path=c.section_path, kind=c.kind, categories_json=json.dumps(c.categories),
                scores_json=json.dumps(c.scores), low_confidence=c.low_confidence,
                classified_by=c.classified_by,
            ))  # fmt: skip
        for f in report.findings:
            session.add(FindingRow(
                contract_id=report.contract_id, rule_id=f.rule_id, status=f.status,
                severity=f.severity, expected=f.expected, found=f.found, location=f.location,
                evidence_text=f.evidence_text, reason=f.reason,
                explanation_json=f.explanation.model_dump_json() if f.explanation else None,
            ))  # fmt: skip
        row.status = row.stage = "DONE"
        row.progress = 100
        row.contract_type = report.meta.contract_type
        row.policy_version = report.policy_version
        row.report_json = report.model_dump_json()
        row.counts_json = json.dumps(report.counts)
        row.finished_at = datetime.now(UTC)
        session.add(row)
        session.commit()


def run_job(
    engine: Engine, resources: Resources, contract_id: str, path: Path, options: Options
) -> None:
    with JOB_SLOT:

        def progress(stage: str, pct: int) -> None:
            if stage != "DONE":
                _update(engine, contract_id, status=stage, stage=stage, progress=pct)

        try:
            report = run(path, options, resources, progress, contract_id=contract_id,
                         filename=path.name)  # fmt: skip
        except ContractGuardError as exc:
            log.info("Contract %s failed: %s", contract_id, exc.code)
            _update(engine, contract_id, status="FAILED", error=exc.message,
                    finished_at=datetime.now(UTC))  # fmt: skip
            return
        except Exception as exc:
            log.exception("Contract %s failed unexpectedly", contract_id)
            _update(engine, contract_id, status="FAILED",
                    error=f"Internal error during analysis ({type(exc).__name__}).",
                    finished_at=datetime.now(UTC))  # fmt: skip
            return
        store_report(engine, report)


def delete_contract(engine: Engine, contract_id: str, upload_dir: Path) -> bool:
    with Session(engine) as session:
        row = session.get(ContractRow, contract_id)
        if row is None:
            return False
        session.exec(delete(ClauseRow).where(col(ClauseRow.contract_id) == contract_id))
        session.exec(delete(FindingRow).where(col(FindingRow.contract_id) == contract_id))
        session.delete(row)
        session.commit()
    shutil.rmtree(upload_dir / contract_id, ignore_errors=True)
    return True
