from news_breakout.signals.daily_shift import load_daily_universe


def test_load_daily_universe_parses_and_dedupes(tmp_path):
    f = tmp_path / "idx.txt"
    f.write_text("# header comment\nANTM\nbbri\n\nANTM\n  TLKM  \n# trailing\n", encoding="utf-8")
    assert load_daily_universe(str(f)) == ["ANTM", "BBRI", "TLKM"]


def test_load_daily_universe_missing_file_returns_empty(tmp_path):
    assert load_daily_universe(str(tmp_path / "nope.txt")) == []
