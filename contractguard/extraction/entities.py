"""spaCy named entities, used as the party fallback (HLD 7.1).

``en_core_web_sm`` is loaded once, on first use. When it is not installed the fallback returns
nothing, and the parties stay empty (role-dependent rules then return NEEDS_REVIEW).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _nlp() -> Any | None:
    try:
        import spacy

        return spacy.load("en_core_web_sm", disable=["lemmatizer"])
    except OSError:
        log.warning("spaCy model en_core_web_sm is not installed; ORG fallback disabled")
        return None


def org_entities(text: str) -> list[str]:
    """Distinct ORG entity texts in order of appearance."""
    nlp = _nlp()
    if nlp is None:
        return []
    seen: list[str] = []
    for ent in nlp(text).ents:
        name = ent.text.strip(" ,.;")
        if ent.label_ == "ORG" and name and name not in seen:
            seen.append(name)
    return seen
