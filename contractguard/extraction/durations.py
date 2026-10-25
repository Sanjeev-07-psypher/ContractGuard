"""Duration and number normalization (HLD 7.2).

Handles "thirty (30) days", "30 days", "thirty days", "one (1) month", "2 weeks",
"ninety calendar days", "15 business days", "1 year", "forty-five (45) days" and "Net 30".
When a word and a digit both appear, the digit wins. Conversion to days uses the multipliers in
``patterns.yaml`` (days x1, weeks x7, months x30, years x365); business or working days become
``ceil(n * 7 / 5)`` calendar days.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache

from contractguard.config import get_patterns

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}  # fmt: skip
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}  # fmt: skip
_NUMBER_WORD = "|".join(sorted([*_UNITS, *_TENS, "hundred"], key=len, reverse=True))
NUMBER_WORDS_RE = rf"(?:{_NUMBER_WORD})(?:(?:[\s-]+and)?[\s-]+(?:{_NUMBER_WORD}))*"


@dataclass(frozen=True)
class Duration:
    value: int  # the number as written ("thirty (30)" -> 30)
    unit: str  # day | week | month | year
    days: int  # converted to calendar days
    business: bool  # business or working days
    text: str  # the exact matched span
    start: int
    end: int


def words_to_number(text: str) -> int | None:
    """ "forty-five" -> 45, "one hundred and twenty" -> 120. None if not a number up to 999."""
    total = 0
    for token in re.split(r"[\s-]+", text.lower().strip()):
        if token == "and" or not token:
            continue
        if token in _UNITS:
            total += _UNITS[token]
        elif token in _TENS:
            total += _TENS[token]
        elif token == "hundred":
            total = max(total, 1) * 100
        else:
            return None
    return total if 0 <= total <= 999 else None


@lru_cache(maxsize=1)
def _config() -> tuple[re.Pattern[str], re.Pattern[str], dict[str, int], frozenset[str]]:
    cfg = get_patterns()["durations"]
    unit_days: dict[str, int] = {k: int(v) for k, v in cfg["unit_days"].items()}
    business = frozenset(q.lower() for q in cfg["business_qualifiers"])
    qualifiers = "|".join([*cfg["business_qualifiers"], *cfg["other_qualifiers"]])
    units = "|".join(unit_days)
    pattern = re.compile(
        rf"(?:\b(?P<w1>{NUMBER_WORDS_RE})\s*\(\s*(?P<d1>\d{{1,3}})\s*\)"
        rf"|\(\s*(?P<d2>\d{{1,3}})\s*\)|\b(?P<d3>\d{{1,3}})"
        rf"|\b(?P<w3>{NUMBER_WORDS_RE}))"
        rf"\s+(?:(?P<qual>{qualifiers})\s+)?(?P<unit>{units})s?\b",
        re.IGNORECASE,
    )
    return pattern, re.compile(cfg["net"]), unit_days, business


def to_days(value: int, unit: str, business: bool = False) -> int:
    days = value * _config()[2][unit]
    return math.ceil(days * 7 / 5) if business else days


def find_durations(text: str) -> list[Duration]:
    """Every duration in ``text`` in order, including "Net 30" payment terms."""
    pattern, net, _, business_words = _config()
    found: list[Duration] = []
    for m in pattern.finditer(text):
        digits = m.group("d1") or m.group("d2") or m.group("d3")
        value = int(digits) if digits else words_to_number(m.group("w3") or "")
        if value is None:
            continue
        unit = m.group("unit").lower()
        business = (m.group("qual") or "").lower() in business_words
        found.append(
            Duration(value, unit, to_days(value, unit, business), business, m.group(), *m.span())
        )
    for m in net.finditer(text):
        if not any(d.start <= m.start() < d.end for d in found):
            n = int(m.group("n"))
            found.append(Duration(n, "day", n, False, m.group(), *m.span()))
    return sorted(found, key=lambda d: d.start)


def parse_duration(text: str) -> Duration | None:
    """The first duration in ``text``, or None."""
    durations = find_durations(text)
    return durations[0] if durations else None
