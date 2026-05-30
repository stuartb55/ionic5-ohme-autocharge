import os
from dotenv import load_dotenv

load_dotenv()

HYUNDAI_USERNAME = os.environ["HYUNDAI_USERNAME"]
HYUNDAI_PASSWORD = os.environ["HYUNDAI_PASSWORD"]
HYUNDAI_PIN = os.environ["HYUNDAI_PIN"]

OHME_EMAIL = os.environ["OHME_EMAIL"]
OHME_PASSWORD = os.environ["OHME_PASSWORD"]

CHARGE_TARGET = int(os.getenv("CHARGE_TARGET", "80"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "180"))

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
NTFY_URL = os.getenv("NTFY_URL", "https://ntfy.sh")
NTFY_TOKEN = os.getenv("NTFY_TOKEN", "")
