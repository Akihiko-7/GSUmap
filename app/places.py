"""The places list: read from data/places.json, written back by the admin mode."""
import json
import math
import os
import re
import threading

from . import config

_lock = threading.Lock()


def load() -> list[dict]:
    return json.loads(config.PLACES_FILE.read_text(encoding="utf-8"))


def save(places: list[dict]) -> None:
    tmp = config.PLACES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(places, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, config.PLACES_FILE)


def upsert(place: dict) -> dict:
    with _lock:
        places = load()
        for i, p in enumerate(places):
            if p["id"] == place["id"]:
                place["reference_photos"] = p.get("reference_photos", []) + place.get("reference_photos", [])
                places[i] = {**p, **place}
                save(places)
                return places[i]
        places.append(place)
        save(places)
        return place


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "place"


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
