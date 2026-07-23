from __future__ import annotations

import re

# Small Indonesian function-word list; enough to keep headline token sets meaningful.
_STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "untuk", "pada", "dengan", "ini", "itu",
    "akan", "ada", "adalah", "atau", "dalam", "juga", "tak", "tidak", "bagi",
    "para", "saat", "usai", "kata", "soal",
}


def normalize_title(title: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", (title or "").lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_duplicate(tokens: set[str], seen: list[set[str]], threshold: float) -> bool:
    if threshold <= 0 or not tokens:
        return False
    return any(jaccard(tokens, s) >= threshold for s in seen)
