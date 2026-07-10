"""Property-based invariants for the energy and money accounting boundaries."""

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

from hypothesis import given, strategies as st
import pytest

import energy
import octopus

UTC = dt.timezone.utc


@given(
    imported=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
    attributed=st.floats(min_value=0, max_value=120, allow_nan=False, allow_infinity=False),
    uncertain=st.booleans(),
)
def test_usage_split_always_conserves_metered_import(imported, attributed, uncertain):
    key = "2026-01-01T00:00:00+00:00"
    attribution = energy.EnergyAttribution(
        car_by_slot={key: attributed}, uncertain_slots={key} if uncertain else set()
    )
    [row] = energy.merge_usage(
        [{"from": key, "to": "2026-01-01T00:30:00+00:00", "importKwh": imported}],
        attribution,
    )

    components = row["carKwh"] + row["houseKwh"] + row["unattributedKwh"]
    assert components == pytest.approx(row["importKwh"], abs=0.0001)
    assert min(row["carKwh"], row["houseKwh"], row["unattributedKwh"]) >= 0
    assert row["carKwh"] <= row["importKwh"]


@given(
    kwh=st.decimals(min_value="0.001", max_value="200", places=3),
    price=st.decimals(min_value="-0.50", max_value="2.00", places=4),
)
def test_fully_covered_bucket_has_exact_wh_and_half_up_minor_cost(kwh, price):
    start = dt.datetime(2026, 1, 1, tzinfo=UTC)
    end = start + dt.timedelta(minutes=30)
    priced = octopus.price_energy_buckets(
        {start.isoformat(): float(kwh)},
        [{"from": start.isoformat(), "to": end.isoformat(), "pricePerKwh": float(price)}],
    )

    expected_wh = int((kwh * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    expected_minor = int((kwh * price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    assert priced.energy_wh == expected_wh
    assert priced.cost_minor == expected_minor
    assert priced.coverage == 1.0


@given(
    start_minute=st.integers(min_value=0, max_value=45),
    span_seconds=st.integers(min_value=1, max_value=900),
    delta_wh=st.integers(min_value=1, max_value=1000),
)
def test_trustworthy_counter_delta_is_conserved_across_slots(
    start_minute, span_seconds, delta_wh
):
    start = dt.datetime(2026, 1, 1, 0, start_minute, tzinfo=UTC)
    end = start + dt.timedelta(seconds=span_seconds)
    rows = [
        (start, 1, 0.0, 7400.0, "charging", True),
        (end, 1, float(delta_wh), 7400.0, "charging", True),
    ]
    attributed = energy.attribute_car_kwh(rows, max_gap_seconds=900)
    plausible_wh = 25_000 * span_seconds / 3600 * 1.25 + 100

    if delta_wh <= plausible_wh:
        assert sum(attributed.car_by_slot.values()) == pytest.approx(delta_wh / 1000)
        assert attributed.issue_count == 0
    else:
        assert attributed.car_by_slot == {}
        assert attributed.issue_count == 1
