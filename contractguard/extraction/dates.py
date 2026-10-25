"""Effective date, term and expiry date (HLD 7.1).

Dates are found with the ``dates.formats`` patterns and parsed with ``dateparser`` using the
organization's date order (DMY by default, for Indian contracts). The expiry date follows the
legal reading (DECISIONS D9): a term of N years from date D ends the day before the Nth
anniversary.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import dateparser

from contractguard.config import get_patterns, get_settings
from contractguard.extraction.durations import NUMBER_WORDS_RE, Duration, find_durations
from contractguard.extraction.sentences import split_sentences

_ORDINAL = re.compile(r"(?i)(\d)(st|nd|rd|th)\b")
_DAY_OF = re.compile(r"(?i)\s+day\s+of\s+")
_DUR = (
    rf"(?:(?:{NUMBER_WORDS_RE})\s*\(\s*\d{{1,3}}\s*\)|\d{{1,3}}|{NUMBER_WORDS_RE})"
    r"\s+(?:\w+\s+)?(?:day|week|month|year)s?"
)


@dataclass(frozen=True)
class FoundDate:
    value: date
    text: str
    start: int


@dataclass(frozen=True)
class Term:
    text: str  # "initial term of one (1) year"
    duration: Duration
    sentence: str
    from_effective_date: bool


@lru_cache(maxsize=1)
def _rules() -> dict:
    cfg = get_patterns()["dates"]
    return {
        "formats": [re.compile(p) for p in cfg["formats"]],
        "effective": re.compile(cfg["effective"]),
        "expiry": re.compile(cfg["expiry"]),
        "term": [re.compile(p.replace("{dur}", f"(?P<dur>{_DUR})"), re.I) for p in cfg["term"]],
        "anchor": re.compile(cfg["start_anchor"]),
    }


def parse_date(text: str, date_order: str | None = None) -> date | None:
    """ "1st day of April, 2026" -> 2026-04-01; "15/05/2026" -> 2026-05-15 with DMY."""
    order = date_order or get_settings().org.date_order
    cleaned = _DAY_OF.sub(" ", _ORDINAL.sub(r"\1", text)).replace(",", " ")
    parsed = dateparser.parse(
        cleaned,
        languages=["en"],
        settings={"DATE_ORDER": order, "REQUIRE_PARTS": ["day", "month", "year"]},
    )
    return parsed.date() if parsed else None


def find_dates(text: str, date_order: str | None = None) -> list[FoundDate]:
    found: list[FoundDate] = []
    taken: list[tuple[int, int]] = []
    for pattern in _rules()["formats"]:
        for m in pattern.finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            value = parse_date(m.group(), date_order)
            if value:
                found.append(FoundDate(value, m.group(), m.start()))
                taken.append(m.span())
    return sorted(found, key=lambda d: d.start)


def effective_date(text: str, date_order: str | None = None) -> FoundDate | None:
    """The date in the sentence that names the effective date; else the first date in ``text``."""
    cue = _rules()["effective"]
    for sentence in split_sentences(text):
        m = cue.search(sentence)
        if not m:
            continue
        dates = find_dates(sentence, date_order)
        if dates:
            return min(dates, key=lambda d: abs(d.start - m.start()))
    dates = find_dates(text, date_order)
    return dates[0] if dates else None


def explicit_expiry(text: str, date_order: str | None = None) -> FoundDate | None:
    """A date stated as the expiry ("shall expire on 31 March 2027")."""
    for sentence in split_sentences(text):
        m = _rules()["expiry"].search(sentence)
        if m:
            later = [d for d in find_dates(sentence, date_order) if d.start >= m.start()]
            if later:
                return later[0]
    return None


def find_term(text: str) -> Term | None:
    """The first term-of-agreement phrase in ``text``."""
    for sentence in split_sentences(text):
        for pattern in _rules()["term"]:
            m = pattern.search(sentence)
            if m:
                duration = find_durations(m.group("dur"))
                if duration:
                    anchored = bool(_rules()["anchor"].search(sentence))
                    return Term(m.group().strip(), duration[0], sentence, anchored)
    return None


def _months_later_minus_a_day(start: date, months: int) -> date:
    """The day before the anniversary; with no such day (29 Feb), the month's last day."""
    year, month = divmod(start.month - 1 + months, 12)
    year, month = year + start.year, month + 1
    last = calendar.monthrange(year, month)[1]
    if start.day > last:
        return date(year, month, last)
    return date(year, month, start.day) - timedelta(days=1)


def end_of_term(start: date, duration: Duration) -> date:
    """Last day of a term that starts on ``start`` (legal reading, D9)."""
    if duration.unit == "year":
        return _months_later_minus_a_day(start, 12 * duration.value)
    if duration.unit == "month":
        return _months_later_minus_a_day(start, duration.value)
    return start + timedelta(days=duration.days - 1)
