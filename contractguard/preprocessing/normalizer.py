"""Character-level normalization (HLD 6.2 steps 5-6).

Stored text keeps its case, stopwords and punctuation: words like "not", "unless" and "except"
change legal meaning. Lowercasing happens only inside the TF-IDF vectorizer.
"""

from __future__ import annotations

import re
import unicodedata

_CHAR_MAP = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
        "―": "-", "−": "-",
        " ": " ", " ": " ", " ": " ", "\t": " ",
        "­": "",  # soft hyphen
    }
)  # fmt: skip
_SPACES = re.compile(r" {2,}")


def normalize_chars(text: str) -> str:
    """Straight quotes, ASCII dashes, plain spaces, single spaces per line, then Unicode NFKC."""
    text = text.translate(_CHAR_MAP)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return unicodedata.normalize("NFKC", "\n".join(lines))
