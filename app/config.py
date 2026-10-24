"""Settings, read once from the environment (and .env when present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
# Leave empty to pick the best Gemma 4 model the key can use at startup. Set it to skip the lookup.
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "").strip()
# Order of preference when picking: the 26B mixture-of-experts answers fastest of the big ones, then 31B, then E4B.
GEMMA_PREFERENCE = ["26b", "31b", "e4b", "e2b"]
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "30"))
# seconds to wait for the main model before also asking the backup model
HEDGE_AFTER = float(os.getenv("HEDGE_AFTER", "6"))
ADMIN_PIN = os.getenv("ADMIN_PIN", "").strip()

DATA = ROOT / "data"
STATIC = ROOT / "static"
PLACES_FILE = DATA / "places.json"
USER_PHOTOS = STATIC / "photos" / "user"

# Gombe State University, from Nominatim ("Gombe State University"), 2026-10-24
CENTER = {"lat": 10.304549, "lng": 11.174468}
IDENTIFY_RADIUS_M = 250
