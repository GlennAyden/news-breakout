from news_breakout.signals.elliott.models import WaveContext
from news_breakout.signals.elliott.annotate import elliott_block


def test_wave3_block_has_label_and_conf_only():
    # invalidation lives in the trade-plan Stop line and fib targets carry no
    # backtest edge -- neither belongs in the Elliott line anymore.
    ctx = WaveContext(position="wave_3_start", confidence=0.62, invalidation=2950.0,
                      fib_targets={"1.618": 3480.0, "2.618": 3780.0},
                      note="kemungkinan awal Wave-3")
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False)
    text = "\n".join(lines)
    assert "🌊" in text and "Wave-3" in text
    assert "0.62" in text
    assert "2.950" not in text
    assert "📐" not in text and "3.480" not in text


def test_exhaustion_block_warns():
    ctx = WaveContext(position="wave_5_possible_exhaustion", confidence=0.55,
                      invalidation=175.0, note="kemungkinan Wave-5 lelah")
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False)
    assert any("⚠️" in ln for ln in lines)


def test_low_confidence_is_omitted():
    ctx = WaveContext(position="wave_3_start", confidence=0.30)
    assert elliott_block(ctx, min_conf=0.45, show_ambiguous=False) == []


def test_ambiguous_hidden_by_default_shown_when_enabled():
    ctx = WaveContext(position="ambiguous", confidence=0.0,
                      note="hitungan bertentangan antar skala")
    assert elliott_block(ctx, min_conf=0.45, show_ambiguous=False) == []
    shown = elliott_block(ctx, min_conf=0.45, show_ambiguous=True)
    assert shown and "ambigu" in shown[0].lower()


def test_none_is_omitted():
    assert elliott_block(WaveContext(position="none"), min_conf=0.0,
                         show_ambiguous=True) == []


def test_ctx_none_returns_empty_list():
    assert elliott_block(None, min_conf=0.0, show_ambiguous=True) == []


def test_from_abc_appends_caution_alongside_main_block():
    ctx = WaveContext(position="wave_3_start", confidence=0.6, from_abc=True)
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False)
    text = "\n".join(lines)
    assert "Wave-3" in text
    assert any("koreksi ABC" in ln for ln in lines)


def test_from_abc_with_ambiguous_hidden_returns_only_caution():
    ctx = WaveContext(position="ambiguous", confidence=0.0, from_abc=True)
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False)
    assert len(lines) == 1
    assert "koreksi ABC" in lines[0]


def test_from_abc_false_adds_no_caution():
    assert elliott_block(WaveContext(position="none", from_abc=False), min_conf=0.0,
                         show_ambiguous=True) == []
    assert elliott_block(None, min_conf=0.0, show_ambiguous=True) == []
    ctx = WaveContext(position="wave_3_start", confidence=0.62, invalidation=2950.0,
                      fib_targets={"1.618": 3480.0}, from_abc=False)
    lines = elliott_block(ctx, min_conf=0.45, show_ambiguous=False)
    assert not any("koreksi ABC" in ln for ln in lines)
