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


def _make_mock_session_seq(payloads: list[dict]):
    """A session whose successive ``.get`` calls return successive payloads — for
    the meter-discovery + paginated-consumption flow."""
    responses = []
    for payload in payloads:
        resp = MagicMock()
        resp.status = 200
        resp.json = AsyncMock(return_value=payload)
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        responses.append(resp)

    session = MagicMock()
    session.get.side_effect = responses
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _enable(monkeypatch):
    monkeypatch.setattr(config, "OCTOPUS_PRODUCT_CODE", "AGILE-24-10-01")
    monkeypatch.setattr(config, "OCTOPUS_REGION", "C")


def _enable_consumption(monkeypatch):
    monkeypatch.setattr(config, "OCTOPUS_API_KEY", "sk_test")
    monkeypatch.setattr(config, "OCTOPUS_ACCOUNT_NUMBER", "A-ABCD1234")
    octopus._meter = None  # reset the discovery cache between tests


_ACCOUNT_PAYLOAD = {
    "properties": [
        {
            "electricity_meter_points": [
                {"is_export": True, "mpan": "999", "meters": [{"serial_number": "EXP"}]},
                {"is_export": False, "mpan": "1200012345678", "meters": [{"serial_number": "Z18"}]},
            ]
        }
    ]
}


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


async def test_fetch_rates_deduplicates_by_start_time(monkeypatch):
    _enable(monkeypatch)
    # Octopus occasionally returns the same half-hour twice (a price
    # correction). Only one row per start time should survive, so it can't
    # render as two identical "cheapest upcoming" slots in the dashboard.
    payload = {
        "results": [
            {"valid_from": "2026-06-26T23:30:00Z", "valid_to": "2026-06-27T00:00:00Z", "value_inc_vat": 6.9},
            {"valid_from": "2026-06-26T23:30:00Z", "valid_to": "2026-06-27T00:00:00Z", "value_inc_vat": 6.9},
        ]
    }
    with patch("aiohttp.ClientSession", return_value=_make_mock_session(payload)):
        rates = await octopus.fetch_rates()

    assert len(rates) == 1
    assert rates[0]["from"] == "2026-06-26T23:30:00Z"


async def test_fetch_rates_skips_malformed_rows(monkeypatch):
    _enable(monkeypatch)
    # A non-numeric price must not propagate out of fetch_rates (it would 500
    # the /api/tariff endpoint); the bad row is dropped and good rows survive.
    payload = {
        "results": [
            {"valid_from": "2026-06-26T17:00:00Z", "valid_to": "2026-06-26T17:30:00Z", "value_inc_vat": "n/a"},
            {"valid_from": "2026-06-26T18:00:00Z", "valid_to": "2026-06-26T18:30:00Z", "value_inc_vat": 24.5},
        ]
    }
    with patch("aiohttp.ClientSession", return_value=_make_mock_session(payload)):
        rates = await octopus.fetch_rates()

    assert [r["from"] for r in rates] == ["2026-06-26T18:00:00Z"]
    assert rates[0]["pricePerKwh"] == 0.245


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


# --- cost_for_slots ---------------------------------------------------------

import datetime as _dt
from dataclasses import dataclass


@dataclass
class _Slot:
    """Minimal stand-in for ohme.utils.ChargeSlot (start/end/energy)."""

    start: _dt.datetime
    end: _dt.datetime
    energy: float


def _rate(from_h: int, to_h: int, price: float) -> dict:
    base = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    return {
        "from": base.replace(hour=from_h).isoformat(),
        "to": base.replace(hour=to_h).isoformat(),
        "pricePerKwh": price,
    }


def _slot(from_h: int, to_h: int, energy: float) -> _Slot:
    base = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    return _Slot(base.replace(hour=from_h), base.replace(hour=to_h), energy)


def test_cost_for_slots_none_without_rates_or_slots():
    assert octopus.cost_for_slots([], [_rate(0, 1, 0.10)]) is None
    assert octopus.cost_for_slots([_slot(0, 1, 5)], None) is None


def test_cost_for_slots_single_rate():
    # 10 kWh entirely inside a 0.20 £/kWh window → £2.00
    rates = [_rate(0, 4, 0.20)]
    assert octopus.cost_for_slots([_slot(0, 2, 10)], rates) == 2.0


def test_cost_for_slots_spans_multiple_rates():
    # A 2h slot of 10 kWh split across two 1h windows priced 0.10 and 0.30.
    # Energy is uniform over time, so 5 kWh in each → 0.5 + 1.5 = £2.00.
    rates = [_rate(0, 1, 0.10), _rate(1, 2, 0.30)]
    assert octopus.cost_for_slots([_slot(0, 2, 10)], rates) == 2.0


def test_cost_for_slots_returns_none_when_not_fully_covered():
    # Slot runs 0-2h but rates only cover 0-1h → can't price the tail.
    rates = [_rate(0, 1, 0.10)]
    assert octopus.cost_for_slots([_slot(0, 2, 10)], rates) is None


def test_cost_for_slots_handles_z_suffix_and_zero_length():
    rates = [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "pricePerKwh": 0.25}]
    slots = [_slot(0, 1, 8), _slot(0, 0, 0)]  # zero-length slot ignored
    assert octopus.cost_for_slots(slots, rates) == 2.0


# --- household consumption --------------------------------------------------


def _window():
    base = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    return base, base + _dt.timedelta(days=1)


def test_consumption_is_enabled_requires_both(monkeypatch):
    monkeypatch.setattr(config, "OCTOPUS_API_KEY", "sk_test")
    monkeypatch.setattr(config, "OCTOPUS_ACCOUNT_NUMBER", "")
    assert octopus.consumption_is_enabled() is False
    _enable_consumption(monkeypatch)
    assert octopus.consumption_is_enabled() is True


async def test_fetch_consumption_none_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "OCTOPUS_API_KEY", "")
    monkeypatch.setattr(config, "OCTOPUS_ACCOUNT_NUMBER", "")
    with patch("aiohttp.ClientSession") as mock_cls:
        assert await octopus.fetch_consumption(*_window()) is None
    mock_cls.assert_not_called()


async def test_discover_meter_picks_import_point(monkeypatch):
    _enable_consumption(monkeypatch)
    with patch("aiohttp.ClientSession", return_value=_make_mock_session(_ACCOUNT_PAYLOAD)):
        meter = await octopus._discover_meter()
    # The export point is skipped; the import meter's mpan + serial are returned.
    assert meter == ("1200012345678", "Z18")


async def test_discover_meter_caches(monkeypatch):
    _enable_consumption(monkeypatch)
    session = _make_mock_session(_ACCOUNT_PAYLOAD)
    with patch("aiohttp.ClientSession", return_value=session) as mock_cls:
        await octopus._discover_meter()
        await octopus._discover_meter()
    # Second call is served from the module cache, not a fresh HTTP session.
    mock_cls.assert_called_once()


async def test_fetch_consumption_discovers_then_parses(monkeypatch):
    _enable_consumption(monkeypatch)
    consumption = {
        "next": None,
        "results": [
            {"interval_start": "2026-01-01T00:30:00Z", "interval_end": "2026-01-01T01:00:00Z", "consumption": 0.2},
            {"interval_start": "2026-01-01T00:00:00Z", "interval_end": "2026-01-01T00:30:00Z", "consumption": 0.5},
        ],
    }
    # First .get is the account lookup, second is the consumption read.
    session = _make_mock_session_seq([_ACCOUNT_PAYLOAD, consumption])
    with patch("aiohttp.ClientSession", return_value=session):
        rows = await octopus.fetch_consumption(*_window())
    # Sorted chronologically; consumption carried through as importKwh.
    assert [r["from"] for r in rows] == ["2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"]
    assert rows[0]["importKwh"] == 0.5


async def test_fetch_consumption_follows_pagination(monkeypatch):
    _enable_consumption(monkeypatch)
    octopus._meter = ("1200012345678", "Z18")  # skip discovery for this test
    page1 = {
        "next": "https://api.octopus.energy/v1/.../?page=2",
        "results": [{"interval_start": "2026-01-01T00:00:00Z", "interval_end": "2026-01-01T00:30:00Z", "consumption": 0.5}],
    }
    page2 = {
        "next": None,
        "results": [{"interval_start": "2026-01-01T00:30:00Z", "interval_end": "2026-01-01T01:00:00Z", "consumption": 0.6}],
    }
    session = _make_mock_session_seq([page1, page2])
    with patch("aiohttp.ClientSession", return_value=session):
        rows = await octopus.fetch_consumption(*_window())
    assert len(rows) == 2
    assert session.get.call_count == 2  # followed the `next` link


async def test_fetch_consumption_none_on_http_error(monkeypatch):
    _enable_consumption(monkeypatch)
    octopus._meter = ("1200012345678", "Z18")
    with patch("aiohttp.ClientSession", return_value=_make_mock_session({}, status=500)):
        assert await octopus.fetch_consumption(*_window()) is None
