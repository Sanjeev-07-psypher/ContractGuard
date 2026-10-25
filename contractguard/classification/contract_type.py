"""Contract type detection by keyword scoring (HLD 6.5).

Keyword hits in the title (the first ``title_lines`` non-empty lines) count ``title_weight`` each;
hits in the first ``body_chars`` characters count ``body_weight`` each. The highest score wins; a
score under ``min_score`` gives OTHER. A user-selected type always overrides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from contractguard.config import get_contract_types


@dataclass(frozen=True)
class ContractTypeResult:
    contract_type: str
    source: str  # "user" | "auto"
    scores: dict[str, int]


def _hits(keyword: str, text: str) -> int:
    # leading word boundary only, so "master service" also matches "Master Services"
    return len(re.findall(rf"(?i)\b{re.escape(keyword)}", text))


def detect_contract_type(text: str, user_type: str | None = None) -> ContractTypeResult:
    cfg = get_contract_types()
    if user_type:
        return ContractTypeResult(user_type, "user", {})
    lines = [line for line in text.splitlines() if line.strip()]
    title = "\n".join(lines[: int(cfg["title_lines"])])
    body = text[: int(cfg["body_chars"])]
    scores = {
        name: sum(
            _hits(k, title) * int(cfg["title_weight"]) + _hits(k, body) * int(cfg["body_weight"])
            for k in keywords
        )
        for name, keywords in cfg["types"].items()
    }
    best = max(scores, key=lambda name: scores[name])
    if scores[best] < int(cfg["min_score"]):
        return ContractTypeResult("OTHER", "auto", scores)
    return ContractTypeResult(best, "auto", scores)
