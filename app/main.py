"""GSU Compass: the API and the web app, served by one FastAPI process."""
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import config, features, places
from .gemma import AIError, gemma

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("compass")
MAX_UPLOAD = 12 * 1024 * 1024
CATEGORIES = ["faculty", "lecture_hall", "hostel", "admin", "bank", "clinic", "cafeteria", "worship", "sports", "gate", "landmark"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await run_in_threadpool(gemma.pick_model)
    yield


app = FastAPI(title="GSU Compass", lifespan=lifespan)


@app.exception_handler(Exception)
async def friendly_errors(_req: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"error": "Something went wrong on our side. Please try again."}, status_code=500)


async def read_photo(f: UploadFile) -> bytes:
    raw = await f.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Photo is too large")
    try:
        return await run_in_threadpool(features.to_jpeg, raw)
    except AIError as e:
        raise HTTPException(400, str(e))


def fnum(v: str | None) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


# ---------------------------------------------------------------- data
@app.get("/api/config")
def get_config():
    return {"ai": gemma.ready, "model": gemma.model or None, "center": config.CENTER, "admin": bool(config.ADMIN_PIN),
            "identify_radius_m": config.IDENTIFY_RADIUS_M}


@app.get("/api/places")
def get_places():
    return places.load()


@app.get("/api/intents")
def get_intents():
    return features.intents()


@app.get("/api/geo/{name}")
def get_geo(name: str):
    if name not in ("paths", "boundary", "buildings"):
        raise HTTPException(404)
    return FileResponse(config.DATA / f"{name}.geojson", media_type="application/geo+json")


@app.get("/healthz")
def health():
    return {"ok": True, "ai": gemma.ready, "model": gemma.model}


# ---------------------------------------------------------------- search
class ResolveIn(BaseModel):
    query: str
    lang: str = "en"


@app.post("/api/resolve")
async def resolve(body: ResolveIn):
    q = body.query.strip()[:300]
    if not q:
        return {"place_id": "", "reason": "", "alternatives": [], "source": "none"}
    return await features.resolve(q, body.lang)


# ---------------------------------------------------------------- directions
class StepsIn(BaseModel):
    steps: list[str]
    destination: str
    lang: str = "en"


@app.post("/api/directions/rewrite")
async def rewrite(body: StepsIn):
    try:
        return {"steps": await features.rewrite_steps(body.steps[:30], body.destination[:120], body.lang), "source": "ai"}
    except AIError as e:
        return {"steps": body.steps, "source": "none", "error": str(e)}


# ---------------------------------------------------------------- Lens
@app.post("/api/identify")
async def identify(photo: UploadFile = File(...), lat: str = Form(""), lng: str = Form(""), lang: str = Form("en")):
    jpeg = await read_photo(photo)
    la, ln = fnum(lat), fnum(lng)
    try:
        return await features.identify(jpeg, la, ln, lang)
    except AIError as e:
        return {**features.nearest_guesses(la, ln), "error": str(e)}


# ---------------------------------------------------------------- GonaDoc
@app.post("/api/gonadoc")
async def gonadoc(photo: UploadFile = File(...), crop: str = Form(""), lang: str = Form("en")):
    jpeg = await read_photo(photo)
    try:
        return await features.diagnose(jpeg, crop, lang)
    except AIError as e:
        return JSONResponse({"error": str(e)}, status_code=503)


# ---------------------------------------------------------------- admin: add or update a place
def check_pin(pin: str) -> None:
    if not config.ADMIN_PIN:
        raise HTTPException(403, "Admin mode is off: set ADMIN_PIN in .env")
    if pin != config.ADMIN_PIN:
        time.sleep(0.5)
        raise HTTPException(403, "Wrong PIN")


class PinIn(BaseModel):
    pin: str


@app.post("/api/admin/verify")
def admin_verify(body: PinIn):
    check_pin(body.pin)
    return {"ok": True}


@app.post("/api/admin/place")
async def admin_place(pin: str = Form(...), id: str = Form(""), name: str = Form(...), aliases: str = Form(""), category: str = Form(...),
                      lat: str = Form(...), lng: str = Form(...), description: str = Form(""), opening_hours: str = Form(""),
                      photos: list[UploadFile] = File(default=[])):
    check_pin(pin)
    la, ln = fnum(lat), fnum(lng)
    if la is None or ln is None or not name.strip():
        raise HTTPException(400, "Name and location are needed")
    if category not in CATEGORIES:
        raise HTTPException(400, "Unknown category")
    pid = places.slug(id or name)
    config.USER_PHOTOS.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, f in enumerate([f for f in photos if f.filename][:3]):
        jpeg = await read_photo(f)
        fname = f"{pid}-{int(time.time())}-{i}.jpg"
        (config.USER_PHOTOS / fname).write_bytes(jpeg)
        saved.append(f"photos/user/{fname}")
    place = {"id": pid, "name": name.strip()[:120], "aliases": [a.strip() for a in aliases.split(",") if a.strip()][:20], "category": category,
             "lat": round(la, 6), "lng": round(ln, 6), "description": description.strip()[:600], "opening_hours": opening_hours.strip()[:120],
             "reference_photos": saved, "approximate": False, "source": "admin"}
    if not place["description"]:
        place.pop("description")
    if not place["opening_hours"]:
        place.pop("opening_hours")
    result = await run_in_threadpool(places.upsert, place)
    log.info("admin saved place %s with %d photos", pid, len(saved))
    return result


# ---------------------------------------------------------------- the web app
@app.get("/sw.js")
def service_worker():
    return FileResponse(config.STATIC / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=config.STATIC, html=True), name="static")
