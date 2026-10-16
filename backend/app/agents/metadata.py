"""Metadata Agent — deterministic. docs/HACKATHON_PLAN.md §6.2.

Extracts EXIF (capture time, make/model, software, GPS) with Pillow. Flags a
conflict when an editing-software tag sits on a claimed phone photo or
screenshot, the capture time is after the upload time, or GPS is more than
50 km from the place stated in the case.

Missing EXIF is "Not available" in neutral grey (WhatsApp strips it) — never a
warning. Geocoding is an offline table of Kerala towns; no network call.
"""
import math
import os
from datetime import datetime

from PIL import Image

from app import storage
from app.db import get_db
from app.util import IST, parse_iso

KERALA_TOWNS = [
    ("Thiruvananthapuram", 8.5241, 76.9366), ("Neyyattinkara", 8.4005, 77.0859), ("Attingal", 8.6975, 76.8151),
    ("Varkala", 8.7379, 76.7163), ("Kollam", 8.8932, 76.6141), ("Punalur", 9.0083, 76.9306),
    ("Pathanamthitta", 9.2648, 76.7870), ("Thiruvalla", 9.3833, 76.5833), ("Kayamkulam", 9.1759, 76.5020),
    ("Alappuzha", 9.4981, 76.3388), ("Changanassery", 9.4421, 76.5367), ("Kottayam", 9.5916, 76.5222),
    ("Thodupuzha", 9.8958, 76.7183), ("Muvattupuzha", 9.9833, 76.5833), ("Kochi", 9.9312, 76.2673),
    ("Ernakulam", 9.9816, 76.2999), ("Kakkanad", 10.0159, 76.3419), ("Edappally", 10.0261, 76.3083),
    ("Kalamassery", 10.0511, 76.3153), ("Aluva", 10.1081, 76.3522), ("Perumbavoor", 10.1121, 76.4759),
    ("Angamaly", 10.1960, 76.3860), ("Chalakudy", 10.3000, 76.3333), ("Thrissur", 10.5276, 76.2144),
    ("Guruvayur", 10.5944, 76.0400), ("Palakkad", 10.7867, 76.6548), ("Ottapalam", 10.7725, 76.3769),
    ("Malappuram", 11.0510, 76.0711), ("Kozhikode", 11.2588, 75.7804), ("Kalpetta", 11.6085, 76.0830),
    ("Vatakara", 11.6082, 75.5912), ("Kannur", 11.8745, 75.3704), ("Payyanur", 12.1000, 75.2000),
    ("Kasaragod", 12.4996, 74.9869),
]
EDITING_SOFTWARE = ("photoshop", "snapseed", "picsart", "gimp", "lightroom", "affinity", "canva", "pixlr")
GPS_CONFLICT_KM = 50
GEOCODE_RADIUS_KM = 40
NO_EXIF_WHY = "No EXIF data in this file. Messaging apps usually remove it when sharing; this is normal and not a concern."


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def _ratio(v) -> float:
    try:
        return float(v)
    except TypeError:
        return v[0] / v[1] if v[1] else 0.0


def extract_exif(sha: str) -> dict:
    out = {"capture_time": None, "make": None, "model": None, "software": None, "gps": None}
    try:
        with Image.open(storage.stream(sha)) as img:
            exif = img.getexif()
    except Exception:
        return out
    if not exif:
        return out
    s = lambda v: v.strip("\x00 ").strip() if isinstance(v, str) else None  # noqa: E731
    out["make"], out["model"], out["software"] = s(exif.get(0x010F)), s(exif.get(0x0110)), s(exif.get(0x0131))
    raw_dt = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)
    if raw_dt:
        try:
            out["capture_time"] = datetime.strptime(raw_dt.strip("\x00"), "%Y:%m:%d %H:%M:%S").replace(tzinfo=IST).isoformat()
        except ValueError:
            pass
    gps = exif.get_ifd(0x8825)
    if gps.get(2) and gps.get(4):
        dms = lambda a: _ratio(a[0]) + _ratio(a[1]) / 60 + _ratio(a[2]) / 3600  # noqa: E731
        lat, lon = dms(gps[2]), dms(gps[4])
        if gps.get(1) == "S":
            lat = -lat
        if gps.get(3) == "W":
            lon = -lon
        out["gps"] = {"lat": lat, "lon": lon}
    return out


def nearest_town(lat: float, lon: float) -> tuple[str, float] | None:
    name, tlat, tlon = min(KERALA_TOWNS, key=lambda t: _km(lat, lon, t[1], t[2]))
    d = _km(lat, lon, tlat, tlon)
    return (name, d) if d <= GEOCODE_RADIUS_KM else None


def stated_town(text: str | None):
    low = (text or "").lower()
    return next((t for t in KERALA_TOWNS if t[0].lower() in low), None)


def analyse(f: dict, case: dict) -> dict:
    exif = extract_exif(f["sha256"])
    if not any(exif.values()):
        return {"status": "Not available", "fields": {}, "geo": None, "conflicts": [], "why": NO_EXIF_WHY}
    fields, conflicts = {}, []
    if exif["capture_time"]:
        fields["Capture time"] = datetime.fromisoformat(exif["capture_time"]).strftime("%d %b %Y, %H:%M")
    if exif["make"] or exif["model"]:
        fields["Device"] = " ".join(x for x in (exif["make"], exif["model"]) if x)
    if exif["software"]:
        fields["Software"] = exif["software"]
    geo = None
    if exif["gps"]:
        lat, lon = exif["gps"]["lat"], exif["gps"]["lon"]
        fields["GPS"] = f"{lat:.4f}, {lon:.4f}"
        near = nearest_town(lat, lon)
        geo = f"{near[0]} (about {near[1]:.0f} km, offline gazetteer)" if near else "Outside the offline gazetteer (Kerala towns only)"
        town = stated_town(case.get("complainant", {}).get("address"))
        if town:
            d = _km(lat, lon, town[1], town[2])
            if d > GPS_CONFLICT_KM:
                conflicts.append(f"GPS position is about {d:.0f} km from the place stated in the case ({town[0]})")
    sw = (exif["software"] or "").lower()
    if any(k in sw for k in EDITING_SOFTWARE):
        conflicts.append(f"Editing-software tag ({exif['software']}) does not fit a phone camera or screenshot source")
    cap, up = parse_iso(exif["capture_time"]), parse_iso(f.get("uploaded_at"))
    if cap and up and cap > up:
        conflicts.append("Capture time is later than the upload time")
    return {"status": "Conflict" if conflicts else "Available", "fields": fields, "geo": geo, "conflicts": conflicts,
            "capture_time": exif["capture_time"], "gps": exif["gps"], "device": fields.get("Device")}


def run(case_id: str) -> str:
    db = get_db()
    case = db.cases.find_one({"id": case_id}) or {}
    for f in db.files.find({"case_id": case_id, "status": "accepted"}):
        if f.get("meta") is not None:
            continue
        if f.get("sniff") in ("jpg", "png", "webp"):
            meta = analyse(f, case)
        elif f.get("sniff") == "pdf":
            meta = {"status": "Not available", "fields": {}, "geo": None, "conflicts": [],
                    "why": "PDF document properties are not read in v1."}
        else:
            meta = {"status": "Not available", "fields": {}, "geo": None, "conflicts": [],
                    "why": "This file type carries no camera metadata."}
        db.files.update_one({"id": f["id"]}, {"$set": {"meta": meta}})
    files = list(db.files.find({"case_id": case_id, "status": "accepted"}, {"meta.status": 1}))
    count = lambda s: sum(1 for f in files if (f.get("meta") or {}).get("status") == s)  # noqa: E731
    return f"{count('Available')} with metadata, {count('Not available')} not available, {count('Conflict')} conflict"
