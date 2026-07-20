# news_breakout/signals/elliott/waves.py
from __future__ import annotations

from collections import Counter

from news_breakout.signals.elliott.models import Swing, Wave, WaveContext, WaveCount
from news_breakout.signals.elliott.swings import multi_scale_swings


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


_UP_POS = {"wave_3_start", "wave_5_possible_exhaustion", "impulse_mid"}


def interpret(swings: list[Swing], scale: float, fib_tol: float = 0.06) -> WaveContext:
    """Infer the current wave position from one scale's swing list."""
    if len(swings) < 3:
        return WaveContext(position="none")
    cur = swings[-1]
    confirmed = swings[:-1]

    # Down provisional leg after an up move -> a pullback / correction.
    if cur.kind == "L":
        return WaveContext(position="wave_2_pullback" if len(confirmed) <= 2
                           else "corrective_or_unresolved", confidence=0.3)

    # Up provisional leg with a full 1-2-3-4 behind it -> possible 5th (exhaustion?).
    # NOTE: this 5-swing check must run before the 3-swing Wave-3 check below,
    # because the last 3 swings of a genuine L,H,L,H,L run also look like a
    # valid "1-2 + breakout" shape and would otherwise shadow it.
    tail5 = confirmed[-5:]
    if len(tail5) == 5 and [s.kind for s in tail5] == ["L", "H", "L", "H", "L"]:
        wc = validate_impulse(tail5 + [cur], scale, fib_tol)
        if wc.rules_ok:
            p0, p1 = tail5[0].price, tail5[1].price
            p4 = tail5[4].price
            w1 = p1 - p0
            stretched = cur.price >= p4 + 1.618 * w1
            pos = "wave_5_possible_exhaustion" if stretched else "impulse_mid"
            targets = {"0.618": p4 + 0.618 * w1, "1.0": p4 + w1}
            note = ("kemungkinan Wave-5 lelah" if stretched else "impuls berjalan")
            return WaveContext(position=pos, confidence=0.4 + 0.4 * wc.fib_fit,
                               primary=wc, invalidation=p4, fib_targets=targets, note=note)

    # Up provisional leg: try Wave-3 start (need ...L,H,L then breaking the H).
    tail = confirmed[-3:]
    if len(tail) == 3 and [s.kind for s in tail] == ["L", "H", "L"]:
        p0, p1, p2 = (s.price for s in tail)
        if p1 > p0 and p2 > p0 and cur.price > p1:          # valid 1-2 + breakout
            w1 = p1 - p0
            targets = {"1.618": p2 + 1.618 * w1, "2.618": p2 + 2.618 * w1}
            r2 = (p1 - p2) / w1 if w1 else 0.0
            fit = 1.0 if any(abs(r2 - f) <= fib_tol for f in (0.5, 0.618, 0.786)) else 0.4
            return WaveContext(position="wave_3_start", confidence=0.5 + 0.3 * fit,
                               invalidation=p2, fib_targets=targets,
                               note="kemungkinan awal Wave-3")

    return WaveContext(position="impulse_mid" if cur.kind == "H" else
                       "corrective_or_unresolved", confidence=0.2)


def label_current(df, *, scales=(2.0, 3.5, 5.0), atr_window=14,
                  max_pivots=9, fib_tol=0.06) -> WaveContext:
    """Label the current wave across scales; disagreement -> 'ambiguous'."""
    scale_swings = multi_scale_swings(df, tuple(scales), atr_window)
    ctxs: list[WaveContext] = []
    for scale, sw in scale_swings.items():
        ctxs.append(interpret(sw[-(max_pivots + 1):], scale, fib_tol))
    ctxs = [c for c in ctxs if c.position != "none"]
    if not ctxs:
        return WaveContext(position="none")

    positions = [c.position for c in ctxs]
    counts = Counter(positions)
    top, count = counts.most_common(1)[0]

    # Directional disagreement (some up-position, some pullback/corrective) -> ambiguous.
    up = any(p in _UP_POS for p in positions)
    down = any(p in ("wave_2_pullback", "wave_4_pullback", "corrective_or_unresolved")
               for p in positions)
    # A genuine tie for the top spot (e.g. two scales each report a different
    # position, with no scale-count majority) is also disagreement, even when
    # every reported position happens to fall on the same up/down side.
    tied_for_top = len(counts) > 1 and sum(1 for c in counts.values() if c == count) > 1
    if (up and down) or tied_for_top:
        return WaveContext(position="ambiguous", confidence=0.0,
                           note="hitungan bertentangan antar skala")

    agree = count / len(ctxs)
    best = max((c for c in ctxs if c.position == top), key=lambda c: c.confidence)
    best.confidence = min(1.0, best.confidence * (0.6 + 0.4 * agree))
    best.alternates = [c.primary for c in ctxs if c is not best and c.primary]
    return best
