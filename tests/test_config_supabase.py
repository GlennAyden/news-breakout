import pytest
from news_breakout.config import load_settings, _normalize_supabase_url


@pytest.mark.parametrize("raw, expected", [
    ("https://proj.supabase.co", "https://proj.supabase.co"),
    ("https://proj.supabase.co/", "https://proj.supabase.co"),   # trailing slash stripped
    ("proj.supabase.co", "https://proj.supabase.co"),            # scheme added
    ("plqegxlzzedwwsluykxo", "https://plqegxlzzedwwsluykxo.supabase.co"),  # bare project ref
    ("  plqegxlzzedwwsluykxo  ", "https://plqegxlzzedwwsluykxo.supabase.co"),  # whitespace
    ("", ""),                                                     # empty stays empty
])
def test_normalize_supabase_url(raw, expected):
    assert _normalize_supabase_url(raw) == expected


def test_load_settings_normalizes_bare_ref(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "plqegxlzzedwwsluykxo")   # bare ref, no scheme/domain
    monkeypatch.setenv("SUPABASE_KEY", " svc-key\n")            # padded
    s = load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))
    assert s.supabase_url == "https://plqegxlzzedwwsluykxo.supabase.co"
    assert s.supabase_key == "svc-key"


def test_supabase_creds_read_from_env(tmp_path, monkeypatch):
    # minimal valid config + env, reusing the example config
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "svc-key")
    s = load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))
    assert s.supabase_url == "https://proj.supabase.co"
    assert s.supabase_key == "svc-key"


def test_supabase_creds_default_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_BREAKOUT_CHAT_ID", "1")
    monkeypatch.setenv("TELEGRAM_NEWS_CHAT_ID", "2")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    s = load_settings(config_path="config/config.example.yaml", env_path=str(tmp_path / "none.env"))
    assert s.supabase_url == ""
    assert s.supabase_key == ""
