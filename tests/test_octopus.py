from unittest.mock import AsyncMock, MagicMock, patch

import config
import octopus


def _make_mock_session(payload: dict, status: int = 200):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get.return_value = resp
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _enable(monkeypatch):
    monkeypatch.setattr(config, "OCTOPUS_PRODUCT_CODE", "AGILE-24-10-01")
    monkeypatch.setattr(config, "OCTOPUS_REGION", "C")


def test_is_enabled_requires_both(monkeypatch):
    monkeypatch.setattr(config, "OCTOPUS_PRODUCT_CODE", "AGILE-24-10-01")
    monkeypatch.setattr(config, "OCTOPUS_REGION", "")
    assert octopus.is_enabled() is False
    _enable(monkeypatch)
    assert octopus.is_enabled() is True


async def test_fetch_rates_none_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "OCTOPUS_PRODUCT_CODE", "")
    with patch("aiohttp.ClientSession") as mock_cls:
        assert await octopus.fetch_rates() is None
    mock_cls.assert_not_called()


async def test_fetch_rates_parses_and_sorts(monkeypatch):
    _enable(monkeypatch)
    payload = {
        "results": [
            {"valid_from": "2026-06-26T18:00:00Z", "valid_to": "2026-06-26T18:30:00Z", "value_inc_vat": 24.5},
            {"valid_from": "2026-06-26T17:00:00Z", "valid_to": "2026-06-26T17:30:00Z", "value_inc_vat": 15.3},
        ]
    }
    with patch("aiohttp.ClientSession", return_value=_make_mock_session(payload)):
        rates = await octopus.fetch_rates()

    # Sorted ascending by time; pence converted to pounds.
    assert [r["from"] for r in rates] == ["2026-06-26T17:00:00Z", "2026-06-26T18:00:00Z"]
    assert rates[0]["pricePerKwh"] == 0.153
    assert rates[1]["pricePerKwh"] == 0.245


async def test_fetch_rates_uses_correct_url(monkeypatch):
    _enable(monkeypatch)
    session = _make_mock_session({"results": []})
    with patch("aiohttp.ClientSession", return_value=session):
        await octopus.fetch_rates()
    url = session.get.call_args[0][0]
    assert "products/AGILE-24-10-01/" in url
    assert "E-1R-AGILE-24-10-01-C/standard-unit-rates" in url


async def test_fetch_rates_none_on_http_error(monkeypatch):
    _enable(monkeypatch)
    with patch("aiohttp.ClientSession", return_value=_make_mock_session({}, status=500)):
        assert await octopus.fetch_rates() is None


async def test_fetch_rates_swallows_connection_error(monkeypatch):
    _enable(monkeypatch)
    with patch("aiohttp.ClientSession", side_effect=Exception("boom")):
        assert await octopus.fetch_rates() is None  # must not raise
