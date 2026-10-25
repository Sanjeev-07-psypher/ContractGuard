"""Split cleaned contract text into clauses (HLD 6.3).

A clause is a numbered section ("7") or sub-section ("7.2") with its heading and body; lettered
and roman sub-items are merged into their parent. Algorithm:

1. Scan lines. An L1 or L2 heading line (``patterns.yaml``) starts a clause; L3 lines and plain
   lines are appended. For DOCX, a paragraph with a ``Heading*`` style also starts a clause.
   Exhibit headings start EXHIBIT clauses; "IN WITNESS WHEREOF" starts the SIGNATURE block.
2. Text before the first clause is the PREAMBLE.
3. Clauses under ``min_chars`` merge into the next clause; clauses over ``max_chars`` are split
   at sentence boundaries into parts with suffixed ids (c014a, c014b).
4. With fewer than ``fallback_min_headings`` numbered headings, split on blank-line paragraphs.
"""

from __future__ import annotations

import logging
import re
import string
from dataclasses import dataclass

from contractguard.config import Settings, get_patterns, get_settings
from contractguard.extraction.sentences import sentencizer
from contractguard.models import Clause, ClauseKind, CleanedText, Document

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SegmentationRules:
    l1: list[re.Pattern[str]]
    l2: list[re.Pattern[str]]
    l3: list[re.Pattern[str]]
    parse: list[re.Pattern[str]]
    definitions: re.Pattern[str]
    exhibit: re.Pattern[str]
    signature: re.Pattern[str]
    docx_heading: re.Pattern[str]
    heading_max_words: int
    fallback_merge_chars: int
    min_chars: int
    max_chars: int
    fallback_min_headings: int

    @classmethod
    def from_config(cls, settings: Settings | None = None) -> SegmentationRules:
        settings = settings or get_settings()
        p = get_patterns()["segmentation"]

        def comp(xs: list[str]) -> list[re.Pattern[str]]:
            return [re.compile(x) for x in xs]

        return cls(
            l1=comp(p["l1"]),
            l2=comp(p["l2"]),
            l3=comp(p["l3"]),
            parse=comp(p["parse"]),
            definitions=re.compile(p["definitions_heading"]),
            exhibit=re.compile(p["exhibit_heading"]),
            signature=re.compile(p["signature"]),
            docx_heading=re.compile(p["docx_heading_style"]),
            heading_max_words=int(p["heading_max_words"]),
            fallback_merge_chars=int(p["fallback_merge_chars"]),
            min_chars=settings.segmentation.min_chars,
            max_chars=settings.segmentation.max_chars,
            fallback_min_headings=settings.segmentation.fallback_min_headings,
        )


@dataclass
class _Draft:
    """A clause under construction: [start, end) offsets into the cleaned text."""

    start: int
    end: int
    kind: ClauseKind = "BODY"
    number: str | None = None
    heading: str | None = None


# --------------------------------------------------------------------------- line scanning


def _lines(text: str) -> list[tuple[int, str]]:
    """(start offset, line) for every line of ``text``."""
    out, pos = [], 0
    for line in text.split("\n"):
        out.append((pos, line))
        pos += len(line) + 1
    return out


def _matches(patterns: list[re.Pattern[str]], line: str) -> bool:
    return any(p.match(line) for p in patterns)


_OCR_ROMAN = str.maketrans({"l": "I", "1": "I", "i": "I", "|": "I"})
_SMALL_WORDS = frozenset("a an and as at by for in of on or the to with".split())


def _roman_fix(num: str) -> str:
    """OCR reads roman I as l, 1, i or | ("ARTICLE Ill", "ARTICLE |"); restore it."""
    if not num.isdigit() and re.fullmatch(r"[IVXLCl1i|]+", num):
        return num.translate(_OCR_ROMAN)
    return num


def _title_case(text: str) -> str:
    """ "TERM AND RENEWAL" -> "Term and Renewal" (small words lower case except the first)."""
    words = [w.lower() if w.lower() in _SMALL_WORDS else w.capitalize() for w in text.split()]
    if words:
        words[0] = words[0][:1].upper() + words[0][1:]
    return " ".join(words)


def _is_heading(rest: str, max_words: int) -> bool:
    """A heading is all caps, or short Title Case text that does not end like a sentence.

    "Contract Price and Payment" is a heading; a wrapped sentence such as "On termination, the
    Contractor shall withdraw its" is not, because most of its content words are lower case.
    """
    if not rest:
        return False
    if rest.isupper():
        return True
    words = rest.split()
    if len(words) > max_words or rest.endswith((".", ";", ",")):
        return False
    content = [w for w in words if w.lower() not in _SMALL_WORDS]
    capitalized = sum(1 for w in content if w[:1].isupper() or not w[:1].isalpha())
    return bool(content) and capitalized / len(content) >= 0.6


def parse_start(line: str, rules: SegmentationRules) -> tuple[str | None, str | None]:
    """(number, heading) of a clause-start line. Heading is None when the line is a sentence."""
    stripped = line.strip()
    for pattern in rules.parse:
        m = pattern.match(stripped)
        if m:
            number, rest = _roman_fix(m.group("num")), m.group("rest").strip(" -:.")
            break
    else:
        number, rest = None, stripped
    if not _is_heading(rest, rules.heading_max_words):
        return number, None
    return number, (_title_case(rest) if rest.isupper() else rest)


def _block_style(cleaned: CleanedText, doc: Document | None, offset: int) -> str | None:
    if doc is None or doc.file_type != "docx":
        return None
    span = cleaned.span_at(offset)
    if span is None or span.start != offset:  # only the first line of a paragraph
        return None
    return doc.blocks[span.block_index].style


def _scan(cleaned: CleanedText, doc: Document | None, rules: SegmentationRules) -> list[_Draft]:
    drafts: list[_Draft] = []
    current: _Draft | None = None
    in_signature = False
    in_exhibit = False

    def start(pos: int, kind: ClauseKind, line: str) -> _Draft:
        nonlocal current
        number, heading = (None, line.strip()) if kind in ("EXHIBIT",) else parse_start(line, rules)
        if kind == "SIGNATURE":
            number, heading = None, None
        current = _Draft(pos, pos + len(line), kind=kind, number=number, heading=heading)
        drafts.append(current)
        return current

    for pos, line in _lines(cleaned.text):
        text = line.strip()
        if not text:
            continue
        style = _block_style(cleaned, doc, pos)
        numbered = not _matches(rules.l3, text) and (
            _matches(rules.l1, text) or _matches(rules.l2, text)
        )
        if rules.exhibit.match(text):
            in_exhibit, in_signature = True, False
            start(pos, "EXHIBIT", line)
        elif not in_signature and rules.signature.search(text):
            in_signature = True
            start(pos, "SIGNATURE", line)
        elif numbered or (style and rules.docx_heading.search(style) and not in_signature):
            in_signature = False
            start(pos, "EXHIBIT" if in_exhibit else "BODY", line)
            if in_exhibit and current is not None:
                current.number, current.heading = parse_start(line, rules)
        elif current is None:
            current = _Draft(pos, pos + len(line), kind="PREAMBLE")
            drafts.append(current)
        else:
            current.end = pos + len(line)
    for d in drafts:
        if d.kind == "BODY" and d.heading and rules.definitions.search(d.heading):
            d.kind = "DEFINITIONS"
    return drafts


def _count_numbered(text: str, rules: SegmentationRules) -> int:
    return sum(
        1
        for _, line in _lines(text)
        if not _matches(rules.l3, line.strip())
        and (_matches(rules.l1, line.strip()) or _matches(rules.l2, line.strip()))
    )


def _fallback(cleaned: CleanedText, rules: SegmentationRules) -> list[_Draft]:
    """Paragraph split: blank-line paragraphs, short ones merged with the next."""
    drafts: list[_Draft] = []
    pending: _Draft | None = None
    for match in re.finditer(r"[^\n](?:.|\n(?!\n))*", cleaned.text):
        para = _Draft(match.start(), match.end())
        if pending is not None:
            para.start = pending.start
            pending = None
        if para.end - para.start < rules.fallback_merge_chars:
            pending = para
            continue
        drafts.append(para)
    if pending is not None:
        if drafts:
            drafts[-1].end = pending.end
        else:
            drafts.append(pending)
    return drafts


# --------------------------------------------------------------------------- length guards


def _merge_short(drafts: list[_Draft], rules: SegmentationRules) -> list[_Draft]:
    """Clauses under min_chars merge into the next clause (or the previous one at the end)."""
    mergeable: tuple[ClauseKind, ...] = ("BODY", "DEFINITIONS", "EXHIBIT")
    out: list[_Draft] = []
    carry: _Draft | None = None
    for i, d in enumerate(drafts):
        if carry is not None:
            d.start = carry.start
            if d.heading is None:
                d.heading = carry.heading
            if d.number is None:
                d.number = carry.number
            if carry.kind != "BODY":
                d.kind = carry.kind
            carry = None
        short = d.end - d.start < rules.min_chars
        nxt = drafts[i + 1] if i + 1 < len(drafts) else None
        if short and d.kind in mergeable and nxt is not None and nxt.kind in mergeable:
            carry = d
            continue
        if short and d.kind in mergeable and out and out[-1].kind in mergeable:
            out[-1].end = d.end
            continue
        out.append(d)
    return out


def _split_long(d: _Draft, text: str, max_chars: int) -> list[tuple[int, int]]:
    """Sentence-boundary cuts so no part exceeds max_chars (a single long sentence stays whole)."""
    body = text[d.start : d.end]
    parts: list[tuple[int, int]] = []
    cur_start = d.start
    for sent in sentencizer()(body).sents:
        s_end = d.start + sent.end_char
        s_start = d.start + sent.start_char
        if s_end - cur_start > max_chars and s_start > cur_start:
            parts.append((cur_start, s_start))
            cur_start = s_start
    parts.append((cur_start, d.end))
    return parts


# --------------------------------------------------------------------------- public API


def _section_path(d: _Draft) -> str:
    if d.kind == "PREAMBLE":
        return "PREAMBLE"
    if d.kind == "SIGNATURE":
        return "SIGNATURE"
    if d.number is None:
        return d.heading or "UNNUMBERED"
    if "." in d.number:
        return f"{d.number.split('.')[0]} > {d.number}"
    return d.number


def segment(
    cleaned: CleanedText,
    doc: Document | None = None,
    rules: SegmentationRules | None = None,
) -> list[Clause]:
    """Return clauses in reading order with ids c001, c002, ... and page ranges."""
    rules = rules or SegmentationRules.from_config()
    text = cleaned.text
    if _count_numbered(text, rules) < rules.fallback_min_headings:
        log.info("fewer than %d numbered headings: paragraph fallback", rules.fallback_min_headings)
        drafts = _fallback(cleaned, rules)
    else:
        drafts = _merge_short(_scan(cleaned, doc, rules), rules)

    clauses: list[Clause] = []
    for n, d in enumerate(drafts, start=1):
        ranges = (
            _split_long(d, text, rules.max_chars)
            if d.end - d.start > rules.max_chars
            else [(d.start, d.end)]
        )
        for k, (start, end) in enumerate(ranges):
            raw = text[start:end]
            end = start + len(raw.rstrip())
            start += len(raw) - len(raw.lstrip())
            page_start, page_end = cleaned.pages_for(start, end)
            suffix = string.ascii_lowercase[k] if len(ranges) > 1 else ""
            clauses.append(
                Clause(
                    clause_id=f"c{n:03d}{suffix}",
                    number=d.number,
                    heading=d.heading,
                    text=text[start:end],
                    page_start=page_start,
                    page_end=page_end,
                    section_path=_section_path(d),
                    char_start=start,
                    char_end=end,
                    kind=d.kind,
                    is_ocr=any(s.is_ocr for s in cleaned.spans if s.start < end and s.end > start),
                )
            )
    log.info("segmented %d clauses", len(clauses))
    return clauses
