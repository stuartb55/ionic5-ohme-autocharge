from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import config
import notify


def _make_mock_session(status: int = 200):
    resp = MagicMock()
    resp.status = status
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post.return_value = resp
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


async def test_no_op_when_topic_not_configured(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "")
    with patch("aiohttp.ClientSession") as mock_cls:
        await notify.send("hello")
    mock_cls.assert_not_called()


async def test_sends_correct_url_and_body(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "my-topic")
    monkeypatch.setattr(config, "NTFY_URL", "https://ntfy.example.com")
    monkeypatch.setattr(config, "NTFY_TOKEN", "")

    session = _make_mock_session()
    with patch("aiohttp.ClientSession", return_value=session):
        await notify.send("test message")

    session.post.assert_called_once()
    call_kwargs = session.post.call_args
    assert call_kwargs[0][0] == "https://ntfy.example.com/my-topic"
    assert call_kwargs[1]["data"] == b"test message"


async def test_sends_bearer_token_when_configured(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "my-topic")
    monkeypatch.setattr(config, "NTFY_URL", "https://ntfy.example.com")
    monkeypatch.setattr(config, "NTFY_TOKEN", "secret-token")

    session = _make_mock_session()
    with patch("aiohttp.ClientSession", return_value=session):
        await notify.send("test")

    headers = session.post.call_args[1]["headers"]
    assert headers == {"Authorization": "Bearer secret-token"}


async def test_no_auth_header_when_token_not_set(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "my-topic")
    monkeypatch.setattr(config, "NTFY_URL", "https://ntfy.example.com")
    monkeypatch.setattr(config, "NTFY_TOKEN", "")

    session = _make_mock_session()
    with patch("aiohttp.ClientSession", return_value=session):
        await notify.send("test")

    headers = session.post.call_args[1]["headers"]
    assert "Authorization" not in headers


async def test_logs_warning_on_non_200_but_does_not_raise(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "my-topic")
    monkeypatch.setattr(config, "NTFY_URL", "https://ntfy.example.com")
    monkeypatch.setattr(config, "NTFY_TOKEN", "")

    session = _make_mock_session(status=403)
    with patch("aiohttp.ClientSession", return_value=session):
        await notify.send("test")  # must not raise


async def test_logs_warning_on_connection_error_but_does_not_raise(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "my-topic")
    monkeypatch.setattr(config, "NTFY_TOKEN", "")

    with patch("aiohttp.ClientSession", side_effect=Exception("connection refused")):
        await notify.send("test")  # must not raise
