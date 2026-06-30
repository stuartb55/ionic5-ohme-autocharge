"""Tests for the pure household-vs-car energy helpers in ``energy.py``."""

import datetime as dt

import energy

UTC = dt.timezone.utc


def _t(hour, minute):
    return dt.datetime(2026, 1, 1, hour, minute, tzinfo=UTC)


def test_attribute_car_kwh_single_slot():
    # 1 kWh added entirely within the 00:00–00:30 slot.
    rows = [(_t(0, 0), 0.0), (_t(0, 30), 1000.0)]
    result = energy.attribute_car_kwh(rows)
    assert result == {_t(0, 0).isoformat(): 1.0}


def test_attribute_car_kwh_splits_across_slots():
    # 2 kWh added over a full hour spanning two half-hour slots → 1 kWh each.
    rows = [(_t(0, 0), 0.0), (_t(1, 0), 2000.0)]
    result = energy.attribute_car_kwh(rows)
    assert result[_t(0, 0).isoformat()] == 1.0
    assert result[_t(0, 30).isoformat()] == 1.0


def test_attribute_car_kwh_proportional_when_reading_mid_slot():
    # A reading at 00:45 means the 00:30 slot only gets the 00:30–00:45 portion.
    # 0->00:15 (0.5 kWh into slot 0), then 00:15->00:45 1 kWh split: 15min in
    # slot 0, 15min in slot 1 → 0.5 kWh each.
    rows = [(_t(0, 0), 0.0), (_t(0, 15), 500.0), (_t(0, 45), 1500.0)]
    result = energy.attribute_car_kwh(rows)
    assert round(result[_t(0, 0).isoformat()], 4) == 1.0  # 0.5 + 0.5
    assert round(result[_t(0, 30).isoformat()], 4) == 0.5


def test_attribute_car_kwh_handles_session_reset():
    # session_energy_wh drops (new session started) — the later reading is the
    # energy since reset, not a negative delta.
    rows = [(_t(0, 0), 5000.0), (_t(0, 30), 800.0)]
    result = energy.attribute_car_kwh(rows)
    assert result == {_t(0, 0).isoformat(): 0.8}


def test_attribute_car_kwh_ignores_flat_and_empty():
    assert energy.attribute_car_kwh([]) == {}
    # No energy added between readings → no buckets.
    assert energy.attribute_car_kwh([(_t(0, 0), 1000.0), (_t(0, 30), 1000.0)]) == {}


def test_merge_usage_breaks_out_house_remainder():
    imports = [
        {"from": _t(0, 0).isoformat(), "to": _t(0, 30).isoformat(), "importKwh": 1.5},
        {"from": _t(0, 30).isoformat(), "to": _t(1, 0).isoformat(), "importKwh": 0.4},
    ]
    car = {_t(0, 0).isoformat(): 1.0}
    out = energy.merge_usage(imports, car)
    assert out[0]["carKwh"] == 1.0
    assert out[0]["houseKwh"] == 0.5
    # No car energy in the second slot → all of it is house.
    assert out[1]["carKwh"] == 0.0
    assert out[1]["houseKwh"] == 0.4


def test_merge_usage_clamps_car_to_import_and_house_non_negative():
    # Car attribution slightly exceeds the metered import (timing skew); car is
    # capped at the import and house can't go negative.
    imports = [{"from": _t(0, 0).isoformat(), "to": _t(0, 30).isoformat(), "importKwh": 0.9}]
    car = {_t(0, 0).isoformat(): 1.2}
    out = energy.merge_usage(imports, car)
    assert out[0]["carKwh"] == 0.9
    assert out[0]["houseKwh"] == 0.0


def test_merge_usage_matches_keys_across_timezone_offsets():
    # Octopus may report interval_start with a +01:00 (BST) offset; the car
    # buckets are keyed in UTC. The same instant must still line up.
    bst = "2026-06-01T01:00:00+01:00"  # == 00:00:00Z
    utc_key = dt.datetime(2026, 6, 1, 0, 0, tzinfo=UTC).isoformat()
    imports = [{"from": bst, "to": "2026-06-01T01:30:00+01:00", "importKwh": 2.0}]
    out = energy.merge_usage(imports, {utc_key: 1.0})
    assert out[0]["carKwh"] == 1.0
    assert out[0]["houseKwh"] == 1.0
