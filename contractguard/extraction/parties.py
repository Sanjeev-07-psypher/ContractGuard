"""Parties, aliases and roles from the preamble (HLD 7.1).

1. The ``parties.preamble`` pattern finds `between <A> (... "<Alias A>") and <B> (... "<Alias B>")`.
   Fallback: the first two spaCy ORG entities in the preamble (no aliases).
2. Roles: a name that fuzzy-matches our organization (token_set_ratio >= 85) is OUR_ORG and the
   other party is the COUNTERPARTY. Otherwise the alias lists decide; otherwise UNKNOWN.
"""

from __future__ import annotations

import re
from functools import lru_cache

from rapidfuzz import fuzz
from rapidfuzz.utils import default_process

from contractguard.config import get_patterns
from contractguard.extraction.entities import org_entities
from contractguard.models import Party


@lru_cache(maxsize=1)
def _rules() -> dict:
    cfg = get_patterns()["parties"]
    return {
        "preamble": re.compile(cfg["preamble"]),
        "name_end": re.compile(cfg["name_end"]),
        "threshold": int(cfg["fuzzy_threshold"]),
        "ours": {a.lower() for a in cfg["our_org_aliases"]},
        "theirs": {a.lower() for a in cfg["counterparty_aliases"]},
    }


def _clean_name(raw: str) -> str:
    name = _rules()["name_end"].split(raw, maxsplit=1)[0]
    return " ".join(name.split()).strip(" ,;:")


_ALIAS_LEAD = re.compile(r"(?i)^.*\b(?:as|the)\s+")


def _clean_alias(raw: str) -> str:
    """Collapse whitespace; 'the Provider' (OCR lost the opening quote) -> 'Provider'."""
    return _ALIAS_LEAD.sub("", " ".join(raw.split()))


def find_parties(preamble: str) -> list[Party]:
    m = _rules()["preamble"].search(preamble)
    if m:
        return [
            Party(name=_clean_name(m.group("a")), alias=_clean_alias(m.group("alias_a"))),
            Party(name=_clean_name(m.group("b")), alias=_clean_alias(m.group("alias_b"))),
        ]
    return [Party(name=name) for name in org_entities(preamble)[:2]]


def is_our_org(name: str, our_org: str | None) -> bool:
    if not our_org:
        return False
    score = fuzz.token_set_ratio(name, our_org, processor=default_process)
    return score >= _rules()["threshold"]


def resolve_roles(parties: list[Party], our_org: str | None) -> list[Party]:
    """Return copies of ``parties`` with roles set."""
    rules = _rules()
    ours = [i for i, p in enumerate(parties) if is_our_org(p.name, our_org)]
    if len(ours) == 1:
        return [
            p.model_copy(update={"role": "OUR_ORG" if i == ours[0] else "COUNTERPARTY"})
            for i, p in enumerate(parties)
        ]
    resolved = []
    for p in parties:
        alias = (p.alias or "").lower()
        role = (
            "OUR_ORG"
            if alias in rules["ours"]
            else "COUNTERPARTY"
            if alias in rules["theirs"]
            else "UNKNOWN"
        )
        resolved.append(p.model_copy(update={"role": role}))
    return resolved


def extract_parties(preamble: str, our_org: str | None) -> list[Party]:
    return resolve_roles(find_parties(preamble), our_org)
