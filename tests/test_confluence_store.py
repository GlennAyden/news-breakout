from news_breakout.confluence.store import ConfluenceStore


def _store():
    return ConfluenceStore(":memory:")


def test_upsert_and_get_defaults_to_stage_none():
    s = _store()
    s.upsert_watch("BBRI", news_ts="2026-07-24T08:00:00+07:00",
                   catalyst_text="Kontrak baru", source="disclosure",
                   expires_at="2026-07-31T08:00:00+07:00")
    w = s.get("BBRI")
    assert w.ticker == "BBRI" and w.stage_alerted == "none"
    assert w.breakout_at is None and w.orderbook_at is None


def test_reupsert_refreshes_catalyst_without_resetting_stage():
    s = _store()
    s.upsert_watch("BBRI", news_ts="t1", catalyst_text="old", source="portal",
                   expires_at="e1")
    s.mark_stage_alerted("BBRI", "2of3")
    s.upsert_watch("BBRI", news_ts="t2", catalyst_text="new", source="portal",
                   expires_at="e2")
    w = s.get("BBRI")
    assert w.catalyst_text == "new" and w.expires_at == "e2"
    assert w.stage_alerted == "2of3"          # stage preserved


def test_mark_breakout_stores_payload_json():
    s = _store()
    s.upsert_watch("BBRI", news_ts="t", catalyst_text="c", source="portal", expires_at="e")
    s.mark_breakout("BBRI", at="2026-07-24T10:30:00+07:00", payload={"tf": "1D", "rvol": 3.2})
    w = s.get("BBRI")
    assert w.breakout_at.endswith("10:30:00+07:00")
    assert '"tf": "1D"' in w.breakout_payload


def test_active_watches_filters_by_stage():
    s = _store()
    s.upsert_watch("AAAA", news_ts="t", catalyst_text="c", source="portal", expires_at="e")
    s.upsert_watch("BBBB", news_ts="t", catalyst_text="c", source="portal", expires_at="e")
    s.mark_stage_alerted("BBBB", "2of3")
    assert {w.ticker for w in s.active_watches(stage="none")} == {"AAAA"}
    assert {w.ticker for w in s.active_watches(stage="2of3")} == {"BBBB"}
    assert {w.ticker for w in s.active_watches()} == {"AAAA", "BBBB"}


def test_prune_expired_removes_past_keeps_future():
    s = _store()
    s.upsert_watch("OLD", news_ts="t", catalyst_text="c", source="portal",
                   expires_at="2026-07-24T00:00:00+07:00")
    s.upsert_watch("NEW", news_ts="t", catalyst_text="c", source="portal",
                   expires_at="2026-08-01T00:00:00+07:00")
    removed = s.prune_expired(now_iso="2026-07-25T00:00:00+07:00")
    assert removed == ["OLD"]
    assert {w.ticker for w in s.active_watches()} == {"NEW"}
