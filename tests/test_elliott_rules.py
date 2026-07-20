from datetime import datetime

from news_breakout.signals.elliott.models import Swing
from news_breakout.signals.elliott.waves import validate_impulse

D = datetime(2024, 1, 1)


def _piv(seq):
    """seq = list of (price, kind) -> Swings with dummy index/date."""
    return [Swing(i, D, p, k, provisional=False) for i, (p, k) in enumerate(seq)]


def _ideal():
    # a textbook up-impulse: 1:100->140, 2:->120, 3:->200, 4:->170, 5:->220
    return _piv([(100, "L"), (140, "H"), (120, "L"), (200, "H"), (170, "L"), (220, "H")])


def test_ideal_impulse_passes_all_rules():
    wc = validate_impulse(_ideal(), scale=2.0)
    assert wc.rules_ok is True
    assert all(wc.rule_flags.values())
    assert [w.label for w in wc.waves] == ["1", "2", "3", "4", "5"]
    assert wc.fib_fit > 0  # some ratio alignment


def test_r1_wave2_retraces_beyond_wave1_start_fails():
    p = _piv([(100, "L"), (140, "H"), (95, "L"), (200, "H"), (170, "L"), (220, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R1"] is False
    assert wc.rules_ok is False


def test_r2_wave3_shortest_fails():
    # W1 len 40, W5 len 60, W3 len 20 (shortest)
    p = _piv([(100, "L"), (140, "H"), (120, "L"), (140, "H"), (110, "L"), (170, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R2"] is False
    assert wc.rules_ok is False


def test_r3_wave4_overlaps_wave1_fails():
    # W4 low (135) dips below W1 high (140)? here 135 < 140 -> overlap
    p = _piv([(100, "L"), (140, "H"), (120, "L"), (200, "H"), (135, "L"), (220, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R3"] is False
    assert wc.rules_ok is False


def test_r4_wrong_alternation_fails():
    # kinds not alternating L,H,L,H,L,H
    p = _piv([(100, "L"), (140, "L"), (120, "L"), (200, "H"), (170, "L"), (220, "H")])
    wc = validate_impulse(p, scale=2.0)
    assert wc.rule_flags["R4"] is False
    assert wc.rules_ok is False
