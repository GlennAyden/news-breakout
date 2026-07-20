# news_breakout/signals/elliott/waves.py
from __future__ import annotations

from news_breakout.signals.elliott.fibonacci import RETRACE
from news_breakout.signals.elliott.models import Swing, Wave, WaveContext, WaveCount


def _fib_fit(w1, w2, w3, w4, w5, tol: float) -> float:
    """Fraction of EW Fibonacci guidelines the count satisfies (0..1), tolerance-banded."""
    checks: list[bool] = []
    if w1.length > 0:
        r2 = w2.length / w1.length                       # W2 retrace of W1
        checks.append(any(abs(r2 - f) <= tol for f in (0.5, 0.618, 0.786)))
        e3 = w3.length / w1.length                        # W3 extension of W1
        checks.append(any(abs(e3 - f) <= tol * 3 for f in (1.618, 2.618)))
        r5 = w5.length / w1.length                        # W5 vs W1
        checks.append(any(abs(r5 - f) <= tol * 2 for f in (0.618, 1.0, 1.618)))
    if w3.length > 0:
        r4 = w4.length / w3.length                        # W4 retrace of W3
        checks.append(any(abs(r4 - f) <= tol for f in (0.382, 0.5)))
    return sum(checks) / len(checks) if checks else 0.0


def validate_impulse(pivots: list[Swing], scale: float, fib_tol: float = 0.06) -> WaveCount:
    """Validate a 6-pivot (L,H,L,H,L,H) up-impulse against the 4 hard rules + score Fib fit."""
    labels = ["1", "2", "3", "4", "5"]
    waves = [Wave(labels[k], pivots[k], pivots[k + 1]) for k in range(5)]
    w1, w2, w3, w4, w5 = waves

    p0, p1, p2, p3, p4, p5 = (s.price for s in pivots)
    kinds = [s.kind for s in pivots]

    r4 = kinds == ["L", "H", "L", "H", "L", "H"] and p1 > p0 and p3 > p2 and p5 > p4
    r1 = p2 > p0                                   # W2 doesn't retrace >100% of W1
    r3 = p4 > p1                                   # W4 doesn't overlap W1 territory
    len1, len3, len5 = w1.length, w3.length, w5.length
    r2 = not (len3 < len1 and len3 < len5)         # W3 not the shortest

    flags = {"R1": bool(r1), "R2": bool(r2), "R3": bool(r3), "R4": bool(r4)}
    rules_ok = all(flags.values())
    fib_fit = _fib_fit(w1, w2, w3, w4, w5, fib_tol) if rules_ok else 0.0
    return WaveCount(waves=waves, scale=scale, rules_ok=rules_ok,
                     rule_flags=flags, fib_fit=fib_fit)
