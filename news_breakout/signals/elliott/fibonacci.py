from __future__ import annotations

RETRACE = (0.382, 0.5, 0.618, 0.786)
EXTEND = (1.272, 1.618, 2.0, 2.618)


def retracements(low: float, high: float) -> dict[float, float]:
    span = high - low
    return {f: high - f * span for f in RETRACE}


def extensions(low: float, high: float) -> dict[float, float]:
    span = high - low
    return {f: low + f * span for f in EXTEND}


def projection(a: float, b: float, c: float, f: float) -> float:
    return c + f * (b - a)


def nearest_ratio(price, low, high, ratios, tol=0.05):
    """Return the ratio whose retracement level is within tol*(high-low) of price."""
    span = high - low
    if span <= 0:
        return None
    best, best_d = None, None
    for f in ratios:
        level = high - f * span
        d = abs(price - level) / span
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = f, d
    return best


def confluence(level, *, structure=None, sma=None, round_step=None,
               other_levels=(), tol=0.0) -> tuple[int, list[str]]:
    """Weighted confluence score for a candidate price zone + contributing factors."""
    score = 0
    factors: list[str] = []
    if structure is not None and abs(level - structure) <= tol:
        score += 2; factors.append("structure")
    if sma is not None and abs(level - sma) <= tol:
        score += 2; factors.append("sma")
    if round_step:
        nearest_round = round(level / round_step) * round_step
        if abs(level - nearest_round) <= tol:
            score += 1; factors.append("round")
    if any(abs(level - o) <= tol for o in other_levels):
        score += 2; factors.append("cluster")
    return score, factors
