import pytest
from news_breakout.data.ajaib_auth import AjaibAuth, _extract_tokens


def test_extract_tokens_reads_access_refresh_and_ttl():
    body = {"data": {"access": {"token": "AT", "expires_in": 1200}, "refresh_token": "RT2"}}
    at, rt, exp = _extract_tokens(body, now=1000)
    assert at == "AT" and rt == "RT2" and exp == 1000 + 1200


def test_extract_tokens_tolerates_flat_shape_and_absolute_expiry():
    body = {"access_token": "AT", "expired_time": 5000}
    at, rt, exp = _extract_tokens(body, now=1000)
    assert at == "AT" and rt is None and exp == 5000


def test_extract_tokens_raises_when_no_access_token():
    with pytest.raises(ValueError):
        _extract_tokens({"nope": 1}, now=0)


def test_refresh_posts_and_caches_token():
    calls = []
    def post(url, payload, headers):
        calls.append((url, payload))
        return 200, {"access_token": "AT", "expires_in": 3600}
    auth = AjaibAuth("RT", http_post=post, clock=lambda: 1000)
    assert auth.get_access_token() == "AT"
    # cached: second call does not re-post
    assert auth.get_access_token() == "AT"
    assert len(calls) == 1
    assert auth.auth_headers()["Authorization"] == "Bearer AT"


def test_refresh_persists_rotated_refresh_token():
    saved = []
    def post(url, payload, headers):
        return 200, {"access_token": "AT", "refresh_token": "RT2", "expires_in": 3600}
    auth = AjaibAuth("RT", token_writer=saved.append, http_post=post, clock=lambda: 0)
    auth.refresh()
    assert saved == ["RT2"]


def test_refresh_raises_on_non_200():
    def post(url, payload, headers):
        return 401, {}
    auth = AjaibAuth("RT", http_post=post, clock=lambda: 0)
    with pytest.raises(RuntimeError):
        auth.refresh()


def test_get_access_token_refreshes_after_expiry():
    seq = [{"access_token": "A1", "expires_in": 100}, {"access_token": "A2", "expires_in": 100}]
    t = {"now": 0}
    def post(url, payload, headers):
        return 200, seq.pop(0)
    auth = AjaibAuth("RT", http_post=post, clock=lambda: t["now"], skew_seconds=0)
    assert auth.get_access_token() == "A1"
    t["now"] = 200  # past expiry
    assert auth.get_access_token() == "A2"
