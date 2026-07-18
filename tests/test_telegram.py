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
