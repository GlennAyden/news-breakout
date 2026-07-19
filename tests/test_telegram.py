from news_breakout.alerts.telegram import send_message


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json})
        return FakeResponse(200)


def test_dry_run_does_not_call_network(capsys):
    fake = FakeClient()
    ok = send_message("tok", "-100", "hello", dry_run=True, client=fake)
    assert ok is True
    assert fake.calls == []  # no network in dry-run
    assert "hello" in capsys.readouterr().out


def test_real_send_posts_to_telegram():
    fake = FakeClient()
    ok = send_message("tok", "-100", "hello", dry_run=False, client=fake)
    assert ok is True
    assert len(fake.calls) == 1
    assert fake.calls[0]["url"].endswith("/bottok/sendMessage")
    assert fake.calls[0]["json"]["chat_id"] == "-100"
    assert fake.calls[0]["json"]["text"] == "hello"


class FlakyThenOkClient:
    """Raises on the first post (simulating e.g. httpx.ReadTimeout), then succeeds."""

    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json})
        if len(self.calls) == 1:
            raise TimeoutError("simulated network timeout")
        return FakeResponse(200)


class AlwaysFailingClient:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json})
        raise TimeoutError("simulated network timeout")


def test_send_message_retries_after_transient_failure_then_succeeds():
    fake = FlakyThenOkClient()
    ok = send_message("tok", "-100", "hello", dry_run=False, client=fake, sleeper=lambda s: None)
    assert ok is True
    assert len(fake.calls) == 2


def test_send_message_never_raises_and_returns_false_after_exhausting_retries():
    fake = AlwaysFailingClient()
    ok = send_message("tok", "-100", "hello", dry_run=False, client=fake,
                      retries=2, sleeper=lambda s: None)
    assert ok is False
    assert len(fake.calls) == 3


def test_send_message_includes_parse_mode_and_disable_preview():
    fake = FakeClient()
    ok = send_message("tok", "-100", "<b>hi</b>", dry_run=False, client=fake,
                      parse_mode="HTML", disable_preview=True)
    assert ok is True
    payload = fake.calls[0]["json"]
    assert payload["parse_mode"] == "HTML"
    assert payload["disable_web_page_preview"] is True


def test_send_message_omits_parse_mode_by_default():
    fake = FakeClient()
    send_message("tok", "-100", "hi", dry_run=False, client=fake)
    payload = fake.calls[0]["json"]
    assert "parse_mode" not in payload
    assert "disable_web_page_preview" not in payload
