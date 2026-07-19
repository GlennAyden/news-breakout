from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPT = str(Path(__file__).resolve().parents[2] / "scripts" / "score_sentiment.py")


def _normalize_label(raw: str) -> str:
    r = (raw or "").lower()
    if "pos" in r:
        return "positif"
    if "neg" in r:
        return "negatif"
    if "neu" in r or "net" in r:
        return "netral"
    return ""


def _default_runner(texts: list[str]) -> list[dict]:
    """Score ``texts`` by shelling out to the model subprocess (torch isolated there)."""
    proc = subprocess.run(
        [sys.executable, _SCRIPT],
        input=json.dumps(texts),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sentiment subprocess failed: {proc.stderr[-500:]}")
    return json.loads(proc.stdout)


def classify(texts: list[str], *, runner=None, min_confidence: float = 0.6) -> list[str]:
    """Return one sentiment label per input text, aligned by index.

    Labels: "positif"/"negatif" only when confident, else "netral". On ANY runner
    failure or a length mismatch, returns all "" so callers degrade to no tag.
    """
    if not texts:
        return []
    if runner is None:
        runner = _default_runner
    try:
        raw = runner(texts)
    except Exception:  # noqa: BLE001 — model failures must never propagate
        return [""] * len(texts)
    if not isinstance(raw, list) or len(raw) != len(texts):
        return [""] * len(texts)
    out = []
    for item in raw:
        try:
            item = item or {}
            label = _normalize_label(item.get("label", ""))
            score = float(item.get("score", 0.0) or 0.0)
            if label in ("positif", "negatif") and score >= min_confidence:
                out.append(label)
            else:
                out.append("netral")
        except (AttributeError, TypeError, ValueError):  # noqa: BLE001 — malformed items degrade to netral
            out.append("netral")
    return out
