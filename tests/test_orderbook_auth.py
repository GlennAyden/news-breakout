import pytest

from news_breakout.orderbook.auth import StockbitAuth, _extract_token


def test_extract_token_nested_access_shape():
    token, exp = _extract_token(
        {"data": {"access": {"token": "abc", "expired_time": 9_000_000_000}}}, now=1000.0
    )
    assert token == "abc"
    assert exp == 9_000_000_000


def test_extract_token_flat_expires_in_is_relative():
    token, exp = _extract_token({"access_token": "xyz", "expires_in": 3600}, now=1000.0)
    assert token == "xyz"
    assert exp == 1000 + 3600   # relative TTL added to the given clock


def test_extract_token_raises_when_missing():
    with pytest.raises(ValueError):
        _extract_token({"nope": 1}, now=1000.0)


def _auth(tmp_path, posts, clock):
    return StockbitAuth(
        "refresh-abc",
        token_path=str(tmp_path / "tok.json"),
        http_post=posts,
        clock=clock,
        skew_seconds=60,
    )


def test_refresh_then_cache_hit_avoids_second_post(tmp_path):
    t = [1000.0]
    calls = []

    def posts(url, payload, headers):
        calls.append(payload)
        return 200, {"access_token": "tok1", "expires_in": 3600}

    auth = _auth(tmp_path, posts, lambda: t[0])
    assert auth.get_access_token() == "tok1"
    assert auth.get_access_token() == "tok1"   # within expiry -> no new post
    assert len(calls) == 1
    assert calls[0] == {"refresh_token": "refresh-abc"}


def test_expiry_triggers_new_refresh(tmp_path):
    t = [1000.0]
    seq = iter([
        (200, {"access_token": "tok1", "expires_in": 3600}),
        (200, {"access_token": "tok2", "expires_in": 3600}),
    ])

    def posts(url, payload, headers):
        return next(seq)

    auth = _auth(tmp_path, posts, lambda: t[0])
    assert auth.get_access_token() == "tok1"
    t[0] = 1000.0 + 3600  # past expiry - skew
    assert auth.get_access_token() == "tok2"


def test_refresh_failure_raises(tmp_path):
    auth = _auth(tmp_path, lambda u, p, h: (401, {}), lambda: 1000.0)
    with pytest.raises(RuntimeError):
        auth.get_access_token()


def test_empty_refresh_token_raises(tmp_path):
    auth = StockbitAuth("", token_path=str(tmp_path / "t.json"),
                        http_post=lambda u, p, h: (200, {}), clock=lambda: 0.0)
    with pytest.raises(RuntimeError):
        auth.refresh()


def test_bootstrap_access_token_used_without_refresh(tmp_path):
    def posts(url, payload, headers):
        raise AssertionError("should not refresh when a bootstrap token is set")

    auth = StockbitAuth("r", access_token="pasted-tok", token_path=str(tmp_path / "t.json"),
                        http_post=posts, clock=lambda: 1000.0)
    assert auth.get_access_token() == "pasted-tok"


def test_token_is_persisted_and_reloaded(tmp_path):
    t = [1000.0]
    calls = []

    def posts(url, payload, headers):
        calls.append(1)
        return 200, {"access_token": "tokP", "expires_in": 3600}

    path = str(tmp_path / "tok.json")
    a1 = StockbitAuth("r", token_path=path, http_post=posts, clock=lambda: t[0])
    assert a1.get_access_token() == "tokP"
    # fresh instance loads the cached token -> no new post while still valid
    a2 = StockbitAuth("r", token_path=path, http_post=posts, clock=lambda: t[0])
    assert a2.get_access_token() == "tokP"
    assert len(calls) == 1
