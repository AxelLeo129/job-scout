"""Tests for the Telegram notifier (no network)."""

import pytest

from jobscout import notifier


class FakeResponse:
    def __init__(self, status_code: int, data: dict | None = None):
        self.status_code = status_code
        self.ok = status_code == 200
        self._data = data or {}
        self.text = ""

    def json(self):
        return self._data


@pytest.fixture
def sleeps(monkeypatch):
    """Record time.sleep calls instead of sleeping."""
    recorded = []
    monkeypatch.setattr(notifier.time, "sleep", recorded.append)
    return recorded


def test_retries_after_429(monkeypatch, sleeps):
    responses = [FakeResponse(429, {"parameters": {"retry_after": 3}}), FakeResponse(200)]
    monkeypatch.setattr(notifier.requests, "post", lambda *a, **kw: responses.pop(0))

    notifier.TelegramNotifier("token", "chat").send("hello")

    assert responses == []
    assert 3 in sleeps


def test_error_includes_description(monkeypatch, sleeps):
    monkeypatch.setattr(
        notifier.requests,
        "post",
        lambda *a, **kw: FakeResponse(400, {"description": "chat not found"}),
    )
    with pytest.raises(RuntimeError, match="chat not found"):
        notifier.TelegramNotifier("token", "chat").send("hello")


def test_waits_between_messages(monkeypatch, sleeps):
    monkeypatch.setattr(notifier.requests, "post", lambda *a, **kw: FakeResponse(200))
    telegram = notifier.TelegramNotifier("token", "chat")
    telegram.send("one")
    telegram.send("two")
    assert sleeps and sleeps[-1] > 1.0
