# tests/test_elliott_waves.py
import numpy as np
import pandas as pd
from datetime import datetime

from news_breakout.signals.elliott.models import Swing
from news_breakout.signals.elliott.waves import interpret, label_current

D = datetime(2024, 1, 1)


def _sw(seq):
    """seq = [(price, kind, provisional?)] -> Swings."""
    out = []
    for i, item in enumerate(seq):
        price, kind = item[0], item[1]
        prov = item[2] if len(item) > 2 else False
        out.append(Swing(i, D, float(price), kind, provisional=prov))
    return out


def test_interpret_wave3_start():
    # 1(100->140) 2(->120)  then provisional up leg breaking above 140 -> Wave-3 start
    sw = _sw([(100, "L"), (140, "H"), (120, "L"), (145, "H", True)])
    ctx = interpret(sw, scale=2.0)
    assert ctx.position == "wave_3_start"
    assert ctx.invalidation == 120.0            # the Wave-2 low
    assert "1.618" in ctx.fib_targets


def test_interpret_wave5_possible_exhaustion():
    # full 1-2-3-4 then a stretched provisional 5th far beyond
    sw = _sw([(100, "L"), (140, "H"), (120, "L"), (200, "H"), (175, "L"), (280, "H", True)])
    ctx = interpret(sw, scale=2.0)
    assert ctx.position == "wave_5_possible_exhaustion"
    assert ctx.invalidation == 175.0            # the Wave-4 low


def test_interpret_down_provisional_is_corrective():
    sw = _sw([(100, "L"), (160, "H"), (140, "L", True)])
    ctx = interpret(sw, scale=2.0)
    assert ctx.position in ("wave_2_pullback", "corrective_or_unresolved")


def test_label_current_smoke_on_synthetic_df():
    prices = list(np.linspace(100, 140, 15)) + list(np.linspace(140, 122, 8)) + \
             list(np.linspace(122, 150, 10))
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    p = np.array(prices)
    df = pd.DataFrame({"Open": p, "High": p + 0.6, "Low": p - 0.6,
                       "Close": p, "Volume": 1000.0}, index=idx)
    ctx = label_current(df, scales=(2.0, 4.0), atr_window=14)
    assert ctx.position in {
        "wave_3_start", "wave_5_possible_exhaustion", "wave_2_pullback",
        "wave_4_pullback", "impulse_mid", "corrective_or_unresolved",
        "ambiguous", "none",
    }
    assert 0.0 <= ctx.confidence <= 1.0


def test_label_current_ambiguous_when_scales_disagree(monkeypatch):
    import news_breakout.signals.elliott.waves as W
    calls = {"n": 0}

    def fake_interpret(swings, scale, fib_tol=0.06):
        calls["n"] += 1
        from news_breakout.signals.elliott.models import WaveContext
        pos = "wave_3_start" if calls["n"] == 1 else "wave_5_possible_exhaustion"
        return WaveContext(position=pos, confidence=0.6)

    monkeypatch.setattr(W, "interpret", fake_interpret)
    df = pd.DataFrame({"Open": [1]*40, "High": [1.5]*40, "Low": [0.5]*40,
                       "Close": [1]*40, "Volume": [1000]*40},
                      index=pd.date_range("2024-01-01", periods=40, freq="D"))
    ctx = W.label_current(df, scales=(2.0, 4.0))
    assert ctx.position == "ambiguous"
