"""Startup validation of required environment variables.

config.py is imported once with valid stub vars (set in conftest) by the rest of
the suite; these tests re-import it in a controlled way to exercise the missing-
variable path, then restore the original module object.
"""

import importlib
import sys

import pytest

REQUIRED = ["HYUNDAI_USERNAME", "HYUNDAI_PASSWORD", "HYUNDAI_PIN", "OHME_EMAIL", "OHME_PASSWORD"]


@pytest.fixture
def reimport_config(monkeypatch, tmp_path):
    """Yield a callable that re-imports config; restores the real module after."""
    # chdir away from the repo so load_dotenv can't pick up a developer's .env.
    monkeypatch.chdir(tmp_path)
    original = sys.modules.pop("config")
    try:
        yield lambda: importlib.import_module("config")
    finally:
        sys.modules["config"] = original


def test_missing_vars_produce_one_clear_message(monkeypatch, reimport_config):
    for var in REQUIRED:
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(SystemExit) as excinfo:
        reimport_config()

    message = str(excinfo.value)
    for var in REQUIRED:
        assert var in message
    assert ".env.example" in message  # points the user at the fix


def test_empty_value_counts_as_missing(monkeypatch, reimport_config):
    monkeypatch.setenv("OHME_EMAIL", "")

    with pytest.raises(SystemExit) as excinfo:
        reimport_config()

    message = str(excinfo.value)
    assert "OHME_EMAIL" in message
    assert "HYUNDAI_USERNAME" not in message  # still set via conftest stubs


def test_all_vars_present_imports_cleanly(reimport_config):
    config = reimport_config()
    assert config.OHME_EMAIL  # conftest stubs are in effect


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("CHARGE_TARGET", "101"),
        ("POLL_INTERVAL", "0"),
        ("UPSTREAM_TIMEOUT", "nope"),
        ("CONSUMPTION_BACKFILL_DAYS", "0"),
        ("DAILY_STATS_INTERVAL", "30"),
        ("TELEMETRY_RETENTION_DAYS", "-1"),
    ],
)
def test_invalid_numeric_settings_fail_fast(monkeypatch, reimport_config, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit, match=name):
        reimport_config()


def test_invalid_timezone_fails_fast(monkeypatch, reimport_config):
    monkeypatch.setenv("TIMEZONE", "Not/A_Real_Zone")
    with pytest.raises(SystemExit, match="TIMEZONE"):
        reimport_config()
