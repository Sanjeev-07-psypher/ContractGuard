"""Turn a Document into cleaned text with an offset map back to pages (HLD 6.2).

Steps, in order:
1. Remove repeating headers/footers (PDF only, documents of 3+ pages).
2. Remove standalone page-number lines.
3. De-hyphenate line breaks.
4. Join soft-wrapped lines, and a clause number left alone on its line with the next line.
5-6. Normalize characters, then Unicode NFKC (``normalizer.normalize_chars``).

Steps 3-6 run per block, so every block maps to one span of the output text.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass

from contractguard.config import get_patterns
from contractguard.models import CleanedText, Document, TextSpan
from contractguard.preprocessing.normalizer import normalize_chars

log = logging.getLogger(__name__)

BLOCK_SEPARATOR = "\n\n"
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class CleaningRules:
    page_number: re.Pattern[str]
    dehyphenate: re.Pattern[str]
    soft_wrap_end: re.Pattern[str]
    soft_wrap_next: re.Pattern[str]
    number_only: re.Pattern[str]
    zone_lines: int
    min_ratio: float
    min_pages: int

    @classmethod
    def from_config(cls) -> CleaningRules:
        c = get_patterns()["cleaning"]
        return cls(
            page_number=re.compile(c["page_number_line"]),
            dehyphenate=re.compile(c["dehyphenate"]),
            soft_wrap_end=re.compile(c["soft_wrap_end"]),
            soft_wrap_next=re.compile(c["soft_wrap_next"]),
            number_only=re.compile(c["number_only_line"]),
            zone_lines=int(c["header_footer_lines"]),
            min_ratio=float(c["header_footer_min_ratio"]),
            min_pages=int(c["header_footer_min_pages"]),
        )


def _line_key(line: str) -> str:
    """A line's identity for header/footer matching: digits stripped, spaces collapsed."""
    return _WS.sub(" ", _DIGITS.sub("", line)).strip().lower()


def find_repeating_lines(doc: Document, rules: CleaningRules) -> set[tuple[int, int]]:
    """(block index, line index) of header/footer lines to drop.

    A line counts when, after stripping digits, it sits in the same zone (the top or the bottom
    ``zone_lines`` lines) of at least ``min_ratio`` of the pages. Only lines inside those zones
    are dropped. Keeping top and bottom apart stops a sentence that wraps across a page break
    ("... fifteen" | "(15) days' notice" at the foot of one page and "(30) days' notice" at the
    head of the next) from being taken for a running header (DECISIONS D23).
    """
    pages = sorted({b.page for b in doc.blocks if b.page is not None})
    if doc.file_type != "pdf" or len(pages) < rules.min_pages:
        return set()
    zones: dict[int, list[tuple[int, int, str, str]]] = {}
    n = rules.zone_lines
    for page in pages:
        lines = [
            (bi, li, line)
            for bi, block in enumerate(doc.blocks)
            if block.page == page
            for li, line in enumerate(block.text.split("\n"))
            if line.strip()
        ]
        top = [(*x, "top") for x in lines[:n]]
        bottom = [(*x, "bottom") for x in lines[n:][-n:]]
        zones[page] = top + bottom
    seen = Counter(
        key
        for page in pages
        for key in {(zone, _line_key(t)) for _, _, t, zone in zones[page]}
        if key[1]
    )
    repeating = {k for k, count in seen.items() if count / len(pages) >= rules.min_ratio}
    return {
        (bi, li)
        for page in pages
        for bi, li, t, zone in zones[page]
        if (zone, _line_key(t)) in repeating
    }


def _join_lines(lines: list[str], rules: CleaningRules) -> list[str]:
    out: list[str] = []
    for line in lines:
        if out and (
            rules.number_only.match(out[-1].strip())
            or (
                not rules.soft_wrap_end.search(out[-1])
                and rules.soft_wrap_next.match(line.lstrip())
            )
        ):
            out[-1] = f"{out[-1].rstrip()} {line.lstrip()}"
        else:
            out.append(line)
    return out


def clean_block(lines: list[str], rules: CleaningRules) -> str:
    """Steps 2-6 for one block's remaining lines."""
    lines = [ln for ln in lines if ln.strip() and not rules.page_number.match(ln)]
    text = rules.dehyphenate.sub(r"\1\2", "\n".join(ln.rstrip() for ln in lines))
    text = "\n".join(_join_lines(text.split("\n"), rules))
    return normalize_chars(text).strip()


def clean_document(doc: Document, rules: CleaningRules | None = None) -> CleanedText:
    rules = rules or CleaningRules.from_config()
    drop = find_repeating_lines(doc, rules)
    removed: list[str] = []
    parts: list[str] = []
    spans: list[TextSpan] = []
    offset = 0
    for bi, block in enumerate(doc.blocks):
        kept = []
        for li, line in enumerate(block.text.split("\n")):
            if (bi, li) in drop:
                removed.append(line.strip())
            else:
                kept.append(line)
        text = clean_block(kept, rules)
        if not text:
            continue
        if parts:
            offset += len(BLOCK_SEPARATOR)
        parts.append(text)
        spans.append(
            TextSpan(
                start=offset,
                end=offset + len(text),
                block_index=bi,
                page=block.page,
                para_index=block.para_index,
                is_ocr=block.is_ocr,
            )
        )
        offset += len(text)
    log.debug("cleaned %d blocks, removed %d header/footer lines", len(spans), len(removed))
    return CleanedText(
        text=BLOCK_SEPARATOR.join(parts),
        spans=spans,
        file_type=doc.file_type,
        removed_lines=sorted(set(removed)),
    )
