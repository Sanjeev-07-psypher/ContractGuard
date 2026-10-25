"""Sentence splitting shared by segmentation and fact extraction.

Uses spaCy's rule-based sentencizer (no model download). Every returned sentence is a verbatim
substring of the input, so it can be quoted as evidence.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from contractguard.config import get_patterns


@lru_cache(maxsize=1)
def sentencizer() -> Any:
    import spacy

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


@lru_cache(maxsize=1)
def _abbreviations() -> tuple[str, ...]:
    return tuple(get_patterns()["sentences"]["abbreviations"])


def _continues(previous: str, nxt: str) -> bool:
    """True when spaCy split after an abbreviation ("ABC Pvt." | "Ltd. shall pay")."""
    return previous.endswith(_abbreviations()) or nxt[:1].islower()


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence; line breaks always end a sentence."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        line_spans: list[tuple[int, int]] = []
        for sent in sentencizer()(line).sents if line.strip() else []:
            chunk = sent.text.strip()
            if not chunk:
                continue
            start = pos + sent.start_char + (len(sent.text) - len(sent.text.lstrip()))
            end = start + len(chunk)
            if line_spans and _continues(text[slice(*line_spans[-1])], chunk):
                line_spans[-1] = (line_spans[-1][0], end)
            else:
                line_spans.append((start, end))
        spans.extend(line_spans)
        pos += len(line) + 1
    return spans


def split_sentences(text: str) -> list[str]:
    return [text[a:b] for a, b in sentence_spans(text)]
