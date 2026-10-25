"""Category-specific fact extractors (HLD 7.3).

Each extractor sees only the clauses of its category and returns one ``Fact``. A fact whose
category has no clause has value None and no evidence; the policy engine decides what that means
(MISSING or NOT_APPLICABLE). Conflicting values give ``ambiguous=True`` and value None, unless the
HLD names a tie-break (termination notice: the minimum). Evidence is the full sentence that
matched, a verbatim substring of the clause text, so explanations can quote it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from contractguard.config import get_patterns
from contractguard.extraction.durations import Duration, find_durations
from contractguard.extraction.sentences import split_sentences
from contractguard.models import Clause, Fact, Party

FACT_KEYS: tuple[str, ...] = (
    "termination.notice_days",
    "termination.counterparty_unilateral",
    "liability.has_cap",
    "liability.is_uncapped",
    "renewal.is_automatic",
    "payment.due_days",
    "governing_law.jurisdiction",
)
_TOKEN = re.compile(r"\S+")


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns]


@lru_cache(maxsize=1)
def _rules() -> dict:
    f = get_patterns()["facts"]
    t, li, r, p = f["termination"], f["liability"], f["renewal"], f["payment"]
    gl = get_patterns()["governing_law"]
    return {
        "negation": _compile(f["negation_cues"]),
        "negation_window": int(f["negation_window_tokens"]),
        "term_kw": re.compile(t["keyword"]),
        "notice": re.compile(t["notice"]),
        "notice_window": int(t["window_tokens"]),
        "cure": re.compile(t["cure"]),
        "subject_end": re.compile(t["subject_end"]),
        "convenience": _compile(t["convenience"]),
        "mutual": _compile(t["mutual"]),
        "cap": _compile(li["cap"]),
        "uncapped": _compile(li["uncapped"]),
        "exclusions": _compile(li["exclusions"]),
        "carve_out": re.compile(li["carve_out"]),
        "auto": _compile(r["automatic"]),
        "manual": _compile(r["manual"]),
        "pay_sentence": re.compile(p["sentence"]),
        "pay_trigger": re.compile(p["trigger"]),
        "law": re.compile(gl["jurisdiction"]),
        "law_aliases": dict(gl["aliases"]),
    }


@dataclass(frozen=True)
class _Sentence:
    text: str
    clause_id: str


def _sentences(clauses: list[Clause], category: str) -> list[_Sentence]:
    return [
        _Sentence(s, c.clause_id)
        for c in clauses
        if category in c.categories
        for s in split_sentences(c.text)
    ]


def _ids(clauses: list[Clause], category: str) -> list[str]:
    return [c.clause_id for c in clauses if category in c.categories]


def _token_index(text: str, offset: int) -> int:
    """Index of the token that contains (or follows) character ``offset``."""
    return sum(1 for m in _TOKEN.finditer(text) if m.end() <= offset)


def _any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


# --------------------------------------------------------------------------- termination


@dataclass(frozen=True)
class _Notice:
    sentence: _Sentence
    duration: Duration
    convenience: bool


def _notice_periods(sentences: list[_Sentence]) -> list[_Notice]:
    """Durations within ``window`` tokens of "notice" in sentences about termination.

    A duration introduced by "within" is a cure period ("fails to cure within 30 days of
    notice"), not a notice period, and is skipped (DECISIONS D22).
    """
    r = _rules()
    found: list[_Notice] = []
    for s in sentences:
        if not r["term_kw"].search(s.text):
            continue
        notices = [_token_index(s.text, m.start()) for m in r["notice"].finditer(s.text)]
        if not notices:
            continue
        convenience = _any(r["convenience"], s.text)
        for d in find_durations(s.text):
            if r["cure"].search(s.text[: d.start]):
                continue
            at = _token_index(s.text, d.start)
            if any(abs(at - n) <= r["notice_window"] for n in notices):
                found.append(_Notice(s, d, convenience))
    return found


def _chosen_notices(sentences: list[_Sentence]) -> tuple[list[_Notice], bool]:
    """Convenience notices if any exist, else all notices; and whether they are convenience."""
    notices = _notice_periods(sentences)
    convenience = [n for n in notices if n.convenience]
    return (convenience, True) if convenience else (notices, False)


def termination_notice(clauses: list[Clause]) -> Fact:
    key = "termination.notice_days"
    notices, _ = _chosen_notices(_sentences(clauses, "TERMINATION"))
    if not notices:
        note = "no notice period found" if _ids(clauses, "TERMINATION") else None
        return Fact(key=key, clause_ids=_ids(clauses, "TERMINATION"), note=note)
    best = min(notices, key=lambda n: n.duration.days)
    values = sorted({n.duration.days for n in notices})
    return Fact(
        key=key,
        value=best.duration.days,
        unit="days",
        clause_ids=[best.sentence.clause_id],
        evidence_text=best.sentence.text,
        note=f"minimum of {values}" if len(values) > 1 else None,
    )


def _names(parties: list[Party], role: str) -> list[str]:
    out: list[str] = []
    for p in parties:
        if p.role == role:
            out += [x for x in (p.alias, p.name) if x]
    return out


def _mentions(text: str, names: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(n)}\b", text) for n in names)


def counterparty_unilateral(clauses: list[Clause], parties: list[Party]) -> Fact:
    """True only if every convenience-termination right belongs to the counterparty."""
    key = "termination.counterparty_unilateral"
    r = _rules()
    ours, theirs = _names(parties, "OUR_ORG"), _names(parties, "COUNTERPARTY")
    notices, convenience = _chosen_notices(_sentences(clauses, "TERMINATION"))
    if not notices:
        return Fact(key=key, clause_ids=_ids(clauses, "TERMINATION"))
    holders: list[tuple[str, _Notice]] = []
    for n in notices:
        text = n.sentence.text
        if _any(r["mutual"], text):
            holders.append(("mutual", n))
            continue
        end = r["subject_end"].search(text)
        subject = text[: end.start()] if end else text
        if ours and _mentions(subject, ours):
            holders.append(("ours", n))
        elif theirs and _mentions(subject, theirs):
            holders.append(("theirs", n))
        else:
            holders.append(("unknown", n))
    kinds = {k for k, _ in holders}
    evidence = holders[0][1]
    value: bool | None = None
    note = None
    if kinds & {"mutual", "ours"}:
        evidence = next(n for k, n in holders if k in ("mutual", "ours"))
        value = False
    elif not (ours and theirs):
        note = "party roles unknown"
    elif kinds == {"theirs"} and convenience:
        value = True
    return Fact(
        key=key,
        value=value,
        clause_ids=[evidence.sentence.clause_id],
        evidence_text=evidence.sentence.text,
        note=note,
    )


# --------------------------------------------------------------------------- liability


def _excluded(text: str, span: tuple[int, int]) -> bool:
    """True if ``span`` lies inside an "including but not limited to" phrase."""
    return any(
        m.start() < span[1] and span[0] < m.end()
        for p in _rules()["exclusions"]
        for m in p.finditer(text)
    )


def _negated(text: str, start: int) -> bool:
    """A negation cue within ``negation_window`` tokens before ``start`` in the sentence."""
    window = _rules()["negation_window"]
    before = list(_TOKEN.finditer(text[:start]))[-window:]
    if not before:
        return False
    chunk = text[before[0].start() : start]
    return _any(_rules()["negation"], chunk)


def _first_match(
    sentences: list[_Sentence], patterns: list[re.Pattern[str]], check_negation: bool
) -> _Sentence | None:
    for s in sentences:
        for p in patterns:
            for m in p.finditer(s.text):
                if _excluded(s.text, m.span()):
                    continue
                if check_negation and _negated(s.text, m.start()):
                    continue
                return s
    return None


def liability(clauses: list[Clause]) -> tuple[Fact, Fact]:
    """(liability.has_cap, liability.is_uncapped)."""
    sentences = _sentences(clauses, "LIABILITY")
    ids = _ids(clauses, "LIABILITY")
    if not ids:
        return Fact(key="liability.has_cap"), Fact(key="liability.is_uncapped")
    cap = _first_match(sentences, _rules()["cap"], check_negation=False)
    uncapped = _first_match(sentences, _rules()["uncapped"], check_negation=True)
    carve = next((s for s in sentences if _rules()["carve_out"].search(s.text)), None)
    has_cap = Fact(
        key="liability.has_cap",
        value=cap is not None,
        clause_ids=[cap.clause_id] if cap else ids,
        evidence_text=cap.text if cap else None,
        note="cap has carve-outs" if cap and carve else None,
    )
    is_uncapped = Fact(
        key="liability.is_uncapped",
        value=uncapped is not None and cap is None,
        clause_ids=[uncapped.clause_id] if uncapped else ids,
        evidence_text=uncapped.text if uncapped else None,
        note="uncapped wording found, but a cap is also present" if uncapped and cap else None,
    )
    return has_cap, is_uncapped


# --------------------------------------------------------------------------- renewal, payment


def renewal(clauses: list[Clause]) -> Fact:
    key = "renewal.is_automatic"
    sentences = _sentences(clauses, "RENEWAL")
    auto = next((s for s in sentences if _any(_rules()["auto"], s.text)), None)
    manual = next((s for s in sentences if _any(_rules()["manual"], s.text)), None)
    if auto and manual:
        return Fact(
            key=key,
            clause_ids=sorted({auto.clause_id, manual.clause_id}),
            evidence_text=auto.text,
            ambiguous=True,
            note="both automatic and mutual-agreement renewal wording found",
        )
    hit = auto or manual
    if hit is None:
        return Fact(key=key, clause_ids=_ids(clauses, "RENEWAL"))
    return Fact(key=key, value=hit is auto, clause_ids=[hit.clause_id], evidence_text=hit.text)


def payment_due(clauses: list[Clause]) -> Fact:
    """Days after "within" / "net" / "no later than" in sentences about invoices or payment."""
    key = "payment.due_days"
    r = _rules()
    hits: list[tuple[_Sentence, Duration]] = []
    for s in _sentences(clauses, "PAYMENT"):
        if not r["pay_sentence"].search(s.text):
            continue
        durations = find_durations(s.text)
        for t in r["pay_trigger"].finditer(s.text):
            following = [
                d for d in durations if 0 <= d.start - t.end() <= 2 or d.start == t.start()
            ]
            hits += [(s, d) for d in following[:1]]
    if not hits:
        return Fact(key=key, clause_ids=_ids(clauses, "PAYMENT"))
    values = sorted({d.days for _, d in hits})
    first, duration = hits[0]
    if len(values) > 1:
        return Fact(
            key=key,
            clause_ids=sorted({s.clause_id for s, _ in hits}),
            evidence_text=first.text,
            ambiguous=True,
            note=f"different payment periods found: {values} days",
        )
    return Fact(
        key=key, value=values[0], unit="days", clause_ids=[first.clause_id],
        evidence_text=first.text,
    )  # fmt: skip


# --------------------------------------------------------------------------- governing law


def normalize_jurisdiction(raw: str) -> str:
    """'Karnataka' -> 'India (Karnataka)'. Unknown names are returned as written."""
    aliases: dict[str, str] = _rules()["law_aliases"]
    name = " ".join(raw.split())
    lowered = {k.lower(): v for k, v in aliases.items()}
    if name.lower() in lowered:
        return lowered[name.lower()]
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?i)\b{re.escape(alias)}\b", name):
            return aliases[alias]
    return name


def governing_law(clauses: list[Clause]) -> Fact:
    key = "governing_law.jurisdiction"
    found: list[tuple[_Sentence, str]] = []
    for s in _sentences(clauses, "GOVERNING_LAW"):
        for m in _rules()["law"].finditer(s.text):
            found.append((s, normalize_jurisdiction(m.group("j"))))
    if not found:
        return Fact(key=key, clause_ids=_ids(clauses, "GOVERNING_LAW"))
    values = sorted({v for _, v in found})
    s, value = found[0]
    if len(values) > 1:
        return Fact(
            key=key,
            clause_ids=sorted({x.clause_id for x, _ in found}),
            evidence_text=s.text,
            ambiguous=True,
            note=f"several governing laws found: {values}",
        )
    return Fact(key=key, value=value, clause_ids=[s.clause_id], evidence_text=s.text)


# --------------------------------------------------------------------------- all facts


def extract_facts(clauses: list[Clause], parties: list[Party]) -> dict[str, Fact]:
    """All V1 facts keyed by fact key, in ``FACT_KEYS`` order."""
    has_cap, is_uncapped = liability(clauses)
    facts = [
        termination_notice(clauses),
        counterparty_unilateral(clauses, parties),
        has_cap,
        is_uncapped,
        renewal(clauses),
        payment_due(clauses),
        governing_law(clauses),
    ]
    return {f.key: f for f in facts}
