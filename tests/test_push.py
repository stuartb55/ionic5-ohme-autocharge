from unittest.mock import MagicMock, patch

import pytest

import config
import push


@pytest.fixture
def subs_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUSH_SUBSCRIPTIONS_PATH", str(tmp_path / "subs.json"))
    return tmp_path / "subs.json"


def _enable(monkeypatch):
    monkeypatch.setattr(config, "VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "priv")
    monkeypatch.setattr(config, "VAPID_SUBJECT", "mailto:a@b.c")


def _sub(endpoint):
    return {"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}}


def test_is_enabled_requires_both_keys(monkeypatch):
    monkeypatch.setattr(config, "VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", "")
    assert push.is_enabled() is False
    _enable(monkeypatch)
    assert push.is_enabled() is True


def test_add_and_remove_subscription_round_trip(subs_file):
    assert push.add_subscription(_sub("https://e/1")) is True
    assert push.add_subscription(_sub("https://e/2")) is True
    # Re-adding the same endpoint replaces rather than duplicates.
    push.add_subscription(_sub("https://e/1"))
    import json
    assert len(json.loads(subs_file.read_text())) == 2

    push.remove_subscription("https://e/1")
    remaining = [s["endpoint"] for s in json.loads(subs_file.read_text())]
    assert remaining == ["https://e/2"]


def test_add_subscription_rejects_missing_endpoint(subs_file):
    assert push.add_subscription({"keys": {}}) is False


async def test_send_noop_when_disabled(monkeypatch, subs_file):
    monkeypatch.setattr(config, "VAPID_PUBLIC_KEY", "")
    with patch("pywebpush.webpush") as mock_wp:
        await push.send("hello")
    mock_wp.assert_not_called()


def test_send_all_delivers_to_each_subscription(subs_file, monkeypatch):
    _enable(monkeypatch)
    push.add_subscription(_sub("https://e/1"))
    push.add_subscription(_sub("https://e/2"))
    with patch("pywebpush.webpush") as mock_wp:
        push._send_all("hello", "Title")
    assert mock_wp.call_count == 2
    # Payload is JSON with title + body.
    import json
    payload = json.loads(mock_wp.call_args.kwargs["data"])
    assert payload == {"title": "Title", "body": "hello"}


def test_send_all_prunes_gone_subscriptions(subs_file, monkeypatch):
    _enable(monkeypatch)
    push.add_subscription(_sub("https://gone"))
    push.add_subscription(_sub("https://ok"))

    from pywebpush import WebPushException

    def fake_webpush(*, subscription_info, **_):
        if subscription_info["endpoint"] == "https://gone":
            raise WebPushException("gone", response=MagicMock(status_code=410))
        return "ok"

    with patch("pywebpush.webpush", side_effect=fake_webpush):
        push._send_all("hi", None)

    import json
    remaining = [s["endpoint"] for s in json.loads(subs_file.read_text())]
    assert remaining == ["https://ok"]  # the 410 endpoint was pruned


def test_send_all_keeps_subscription_on_transient_error(subs_file, monkeypatch):
    _enable(monkeypatch)
    push.add_subscription(_sub("https://e/1"))
    from pywebpush import WebPushException
    with patch("pywebpush.webpush", side_effect=WebPushException("boom", response=MagicMock(status_code=500))):
        push._send_all("hi", None)
    import json
    assert len(json.loads(subs_file.read_text())) == 1  # kept (not a 404/410)
