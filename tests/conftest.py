import os
import tempfile

# Set required env vars before any module imports config.py
os.environ.setdefault("HYUNDAI_USERNAME", "test_user")
os.environ.setdefault("HYUNDAI_PASSWORD", "test_pass")
os.environ.setdefault("HYUNDAI_PIN", "0000")
os.environ.setdefault("OHME_EMAIL", "test@example.com")
os.environ.setdefault("OHME_PASSWORD", "test_pass")

# Construct the FastAPI app without spawning the background poll loop.
os.environ.setdefault("AUTOCHARGE_DISABLE_POLLING", "1")

# Persist runtime settings to a throwaway temp file so tests never touch the real
# /app/data path (which would also create stray dirs on dev machines).
os.environ.setdefault(
    "SETTINGS_PATH", os.path.join(tempfile.gettempdir(), "autocharge-test-settings.json")
)
