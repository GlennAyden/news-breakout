from news_breakout.signals.elliott.models import WaveContext
from news_breakout.signals.elliott.annotate import elliott_block


def _r(v):  # stand-in for _rupiah
    return f"{v:,.0f}".replace(",", ".")


def test_wave3_block_has_label_invalidation_and_targets():
    ctx = WaveContext(position="wave_3_start", confidence=0.62, invalidation=2950.0,
                      fib_targets={"1.618": 3480.0, "2.618": 3780.0},
                      note="kemungkinan awal Wave-3")
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r)
    text = "\n".join(lines)
    assert "🌊" in text and "Wave-3" in text
    assert "0.62" in text
    assert "2.950" in text            # invalidation, thousands-formatted
    assert "3.480" in text and "3.780" in text


def test_exhaustion_block_warns():
    ctx = WaveContext(position="wave_5_possible_exhaustion", confidence=0.55,
                      invalidation=175.0, note="kemungkinan Wave-5 lelah")
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r)
    assert any("⚠️" in ln for ln in lines)


def test_low_confidence_is_omitted():
    ctx = WaveContext(position="wave_3_start", confidence=0.30)
    assert elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r) == []


def test_ambiguous_hidden_by_default_shown_when_enabled():
    ctx = WaveContext(position="ambiguous", confidence=0.0,
                      note="hitungan bertentangan antar skala")
    assert elliott_block(ctx, min_conf=0.45, show_ambiguous=False, rupiah=_r) == []
    shown = elliott_block(ctx, min_conf=0.45, show_ambiguous=True, rupiah=_r)
    assert shown and "ambigu" in shown[0].lower()


def test_none_is_omitted():
    assert elliott_block(WaveContext(position="none"), min_conf=0.0,
                         show_ambiguous=True, rupiah=_r) == []
