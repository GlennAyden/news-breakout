from __future__ import annotations

import pandas as pd


def filter_liquid_universe(
    candidates: list[str],
    daily_data: dict[str, pd.DataFrame],
    min_price: float,
    min_daily_value: float,
    value_window: int = 20,
) -> list[str]:
    out: list[str] = []
    for t in candidates:
        df = daily_data.get(t)
        if df is None or df.empty:
            continue
        if float(df["Close"].iloc[-1]) < min_price:
            continue
        recent = df.iloc[-value_window:]
        avg_value = float((recent["Close"] * recent["Volume"]).mean())
        if avg_value < min_daily_value:
            continue
        out.append(t)
    return out
