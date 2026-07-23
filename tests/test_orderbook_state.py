from news_breakout.orderbook.state import PhaseStore


def test_set_and_get_phase():
    s = PhaseStore(":memory:")
    assert s.get_last_phase("ANTM", "2026-07-20") is None
    s.set_phase("ANTM", "2026-07-20", "A")
    assert s.get_last_phase("ANTM", "2026-07-20") == "A"
    s.close()


def test_set_phase_overwrites_same_day():
    s = PhaseStore(":memory:")
    s.set_phase("ANTM", "2026-07-20", "A")
    s.set_phase("ANTM", "2026-07-20", "RM")
    assert s.get_last_phase("ANTM", "2026-07-20") == "RM"
    s.close()


def test_phase_is_isolated_per_day():
    s = PhaseStore(":memory:")
    s.set_phase("ANTM", "2026-07-20", "RM")
    assert s.get_last_phase("ANTM", "2026-07-21") is None
    s.close()
