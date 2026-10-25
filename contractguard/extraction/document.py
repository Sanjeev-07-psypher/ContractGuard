"""Document-level metadata: title, type, parties, dates, term and governing law (HLD 6.5, 7.1)."""

from __future__ import annotations

from contractguard.classification.contract_type import detect_contract_type
from contractguard.extraction.dates import effective_date, end_of_term, explicit_expiry, find_term
from contractguard.extraction.facts import governing_law
from contractguard.extraction.parties import extract_parties
from contractguard.models import Clause, ContractMeta

PREAMBLE_FALLBACK_CHARS = 1500  # used when segmentation found no PREAMBLE


def _preamble(clauses: list[Clause]) -> str:
    pre = [c.text for c in clauses if c.kind == "PREAMBLE"]
    if pre:
        return "\n".join(pre)
    return "\n".join(c.text for c in clauses)[:PREAMBLE_FALLBACK_CHARS]


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def extract_meta(
    clauses: list[Clause],
    our_org: str | None,
    contract_type: str | None = None,
    date_order: str | None = None,
) -> ContractMeta:
    """``contract_type`` given by the user overrides detection (source "user")."""
    full_text = "\n\n".join(c.text for c in clauses)
    preamble = _preamble(clauses)
    detected = detect_contract_type(full_text, contract_type)
    title = next((line.strip() for line in preamble.splitlines() if line.strip()), None)

    effective = effective_date(preamble, date_order)
    body = "\n\n".join(c.text for c in clauses if c.kind in ("BODY", "DEFINITIONS"))
    term = find_term(body)
    expiry = explicit_expiry(body, date_order)
    expiry_date = expiry.value if expiry else None
    if expiry_date is None and term and term.from_effective_date and effective:
        expiry_date = end_of_term(effective.value, term.duration)

    return ContractMeta(
        contract_type=detected.contract_type,
        contract_type_source="user" if detected.source == "user" else "auto",
        parties=extract_parties(preamble, our_org),
        effective_date=effective.value if effective else None,
        expiry_date=expiry_date,
        term_text=term.text if term else None,
        governing_law=_as_str(governing_law(clauses).value),
        title=title,
    )
