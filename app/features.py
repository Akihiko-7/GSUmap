"""The four things Gemma does: resolve a question to a place, rewrite directions, identify a building, diagnose a leaf."""
import io
import json
import logging
import re
from functools import lru_cache
from typing import Literal

from PIL import Image, ImageOps
from pydantic import BaseModel, Field, field_validator

from . import config, places
from .gemma import AIError, gemma, image_part, language_rule

log = logging.getLogger("features")


# ---------------------------------------------------------------- images
def to_jpeg(raw: bytes, max_side: int = 1024) -> bytes:
    """Any uploaded image to an upright RGB JPEG no larger than max_side. Raises AIError if it is not an image."""
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        raise AIError("That file is not a photo we can read")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82)
    return out.getvalue()


@lru_cache(maxsize=256)
def reference_jpeg(rel: str) -> bytes | None:
    path = (config.STATIC / rel).resolve()
    if not path.is_file() or config.STATIC.resolve() not in path.parents:
        return None
    return to_jpeg(path.read_bytes(), 448)


# ---------------------------------------------------------------- search: question to place
class Resolved(BaseModel):
    place_id: str = Field(description="id of the best place from the list, or an empty string if none fits")
    reason: str = Field(description="one short sentence telling the student why this place")
    alternatives: list[str] = Field(default_factory=list, description="up to 2 other place ids that could also help")


@lru_cache(maxsize=1)
def intents() -> list[dict]:
    return json.loads((config.DATA / "intents.json").read_text(encoding="utf-8"))


def resolve_by_rules(query: str, lang: str) -> dict | None:
    words = set(re.findall(r"[\w']+", query.lower()))
    best, score = None, 0
    for it in intents():
        s = sum(1 for w in it["words"] if (w in words if " " not in w else w in query.lower()))
        if s > score:
            best, score = it, s
    if not best:
        return None
    return {"place_id": best["places"][0], "reason": best["reason_ha" if lang == "ha" else "reason"], "alternatives": best["places"][1:3], "source": "rules"}


async def resolve(query: str, lang: str) -> dict:
    ps = places.load()
    ids = {p["id"] for p in ps}
    listing = "\n".join(f'{p["id"]} | {p["name"]} | {p["category"]} | aliases: {", ".join(p["aliases"][:6])} | {p["description"][:140]}' for p in ps)
    prompt = (
        "You help new students at Gombe State University (GSU), Nigeria, find the right place on campus.\n"
        f'A student asked: "{query}"\n'
        "Pick the single best place from this list (id | name | category | aliases | description). "
        "Think about what office or service handles the request (for example school fees go to the Bursary, course registration "
        "to the Registry or their department, illness to the Clinic). Only use ids from the list.\n"
        f"{listing}\n{language_rule(lang)}"
    )
    try:
        r = await gemma.ask([prompt], Resolved, timeout=min(config.AI_TIMEOUT, 12))
        if r.place_id in ids:
            return {"place_id": r.place_id, "reason": r.reason, "alternatives": [a for a in r.alternatives if a in ids and a != r.place_id][:2], "source": "ai"}
        log.info("AI found no place for %r", query)
    except AIError as e:
        log.info("resolve falling back to rules: %s", e)
    return resolve_by_rules(query, lang) or {"place_id": "", "reason": "", "alternatives": [], "source": "none"}


# ---------------------------------------------------------------- directions in friendly words
class Steps(BaseModel):
    steps: list[str]

    @field_validator("steps")
    @classmethod
    def not_looping(cls, v: list[str]) -> list[str]:
        # a model stuck in a loop writes very long steps or the same word over and over: reject so the other model is tried
        for step in v:
            words = re.findall(r"\w+", step.lower())
            if len(step) > 240 or (len(words) > 8 and len(set(words)) < len(words) / 2):
                raise ValueError("step looks broken")
        return v


async def rewrite_steps(steps: list[str], destination: str, lang: str) -> list[str]:
    target = "Hausa" if lang == "ha" else "simple, friendly English"
    prompt = (
        f"Rewrite these {len(steps)} walking directions to {destination} so they are short and warm, in {target}. "
        "One step for each step below, same order, same distances, place names unchanged.\n"
        + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    )
    r = await gemma.ask([prompt], Steps, max_tokens=80 * len(steps) + 200)
    if len(r.steps) != len(steps):
        raise AIError("The AI changed the number of steps")
    return r.steps


# ---------------------------------------------------------------- Lens: which building is this?
class Guess(BaseModel):
    place_id: str
    confidence: float = Field(ge=0, le=1)


class Identified(BaseModel):
    place_id: str = Field(description="id of the candidate shown in the user's photo, or an empty string if none")
    confidence: float = Field(ge=0, le=1, description="0 to 1")
    explanation: str = Field(description="one line: what in the photo matches")
    top3: list[Guess] = Field(default_factory=list, description="the three most likely candidates, best first")


def candidates_for(lat: float | None, lng: float | None) -> list[dict]:
    ps = places.load()
    if lat is None or lng is None:
        return [p for p in ps if p["reference_photos"]][:10]
    for p in ps:
        p["_d"] = places.distance_m(lat, lng, p["lat"], p["lng"])
    ps.sort(key=lambda p: p["_d"])
    near = [p for p in ps if p["_d"] <= config.IDENTIFY_RADIUS_M]
    with_photos = [p for p in near if p["reference_photos"]]
    if len(with_photos) < 3:  # too few photographed places close by: widen to the nearest photographed ones
        extra = [p for p in ps if p["reference_photos"] and p not in near and p["_d"] <= 800][: 3 - len(with_photos)]
        near += extra
    return near[:10] or ps[:6]


async def identify(photo: bytes, lat: float | None, lng: float | None, lang: str) -> dict:
    cands = candidates_for(lat, lng)
    parts: list = [
        "You identify buildings on the Gombe State University campus, Nigeria. The FIRST image is the user's photo. "
        "Then come the candidate places near the user, each with an id, a description and, when we have one, a reference photo. "
        "Compare architecture, wall colour, number of storeys, roof, entrance and signage. If the photo does not show any candidate, "
        "return an empty place_id and low confidence. " + language_rule(lang),
        image_part(photo),
    ]
    images = 1
    for c in cands:
        dist = f', about {round(c["_d"])} m from the user' if "_d" in c else ""
        parts.append(f'Candidate id={c["id"]}: {c["name"]} ({c["category"]}){dist}. {c["description"]}')
        for rel in c["reference_photos"][:1]:
            if images >= 9:
                break
            jpg = reference_jpeg(rel)
            if jpg:
                parts.append(image_part(jpg))
                images += 1
    r = await gemma.ask(parts, Identified)
    ids = {c["id"] for c in cands}
    top = [g.model_dump() for g in r.top3 if g.place_id in ids][:3]
    best = r.place_id if r.place_id in ids else ""
    if best and not any(g["place_id"] == best for g in top):
        top.insert(0, {"place_id": best, "confidence": r.confidence})
    return {"place_id": best, "confidence": round(r.confidence, 2) if best else 0, "explanation": r.explanation, "top3": top[:3],
            "candidates": [c["id"] for c in cands], "source": "ai"}


def nearest_guesses(lat: float | None, lng: float | None) -> dict:
    """When the AI cannot answer: the closest places, so the user still gets something useful."""
    cands = candidates_for(lat, lng)[:3]
    return {"place_id": "", "confidence": 0, "explanation": "", "top3": [{"place_id": c["id"], "confidence": 0} for c in cands], "candidates": [c["id"] for c in cands], "source": "nearby"}


# ---------------------------------------------------------------- GonaDoc: what is wrong with this leaf?
class Diagnosis(BaseModel):
    is_crop_leaf: bool = Field(description="false if the photo is not a crop plant")
    crop: str
    healthy: bool
    problem: str = Field(description="likely disease, pest or deficiency; empty if healthy")
    problem_type: Literal["disease", "pest", "nutrient", "water", "none", "unknown"]
    local_name: str = Field(description="common Hausa name for the problem if one is widely known, else empty")
    confidence: float = Field(ge=0, le=1)
    symptoms_seen: list[str]
    treatment: list[str] = Field(description="low-cost, locally available options first; chemical options last with safety advice")
    prevention: list[str]
    see_extension_officer: str = Field(description="when the farmer should see an agricultural extension officer")


CROPS = ["maize", "tomato", "groundnut", "sorghum", "rice", "beans"]


async def diagnose(photo: bytes, crop_hint: str, lang: str) -> dict:
    hint = f"The farmer says the crop is {crop_hint}. " if crop_hint in CROPS else ""
    prompt = (
        "You are GonaDoc, a careful crop doctor for smallholder farmers in Gombe State, northern Nigeria. "
        f"Look at this leaf photo. Crops grown here: {', '.join(CROPS)}. {hint}"
        "Name the crop, the most likely disease, pest or deficiency, and how sure you are. List what you can actually see. "
        "For treatment put cheap, locally available options first (removing and burning infected leaves, wood ash, neem leaf extract, "
        "crop rotation, resistant local varieties, spacing, weeding), then approved chemical options sold in Nigerian agro-dealer shops "
        "with safety advice (gloves, mask, follow the label, keep from children). Never invent product brand names. "
        "If the photo is unclear or not a crop, say so and keep confidence low. "
        "'problem' must name the specific disease, pest or deficiency with its common English name and the pathogen or pest in brackets, "
        "for example 'Early blight (Alternaria solani)', even when the rest of the answer is in Hausa; never just 'disease'. "
        + language_rule(lang)
    )
    r = await gemma.ask([prompt, image_part(photo)], Diagnosis)
    return {**r.model_dump(), "confidence": round(r.confidence, 2), "source": "ai"}
