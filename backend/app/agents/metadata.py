"""Metadata Agent — deterministic, owned by G.
docs/HACKATHON_PLAN.md §6.2.

Missing EXIF is "Not available" in neutral grey — never a warning (WhatsApp
strips it from nearly everything). Geocoding uses a small offline table of
~30 Kerala towns; no Nominatim, no network call.
"""
import math
import os
from datetime import datetime

import piexif

from app.config import settings
from app.db import get_db

# Approximate town-centre coordinates; good enough for a "near/far from the
# stated place" conflict check, not for precise mapping.
KERALA_TOWNS: list[dict] = [
    {"name": "Thiruvananthapuram", "lat": 8.5241, "lon": 76.9366},
    {"name": "Neyyattinkara", "lat": 8.4005, "lon": 77.0859},
    {"name": "Attingal", "lat": 8.6975, "lon": 76.8151},
    {"name": "Varkala", "lat": 8.7379, "lon": 76.7163},
    {"name": "Kollam", "lat": 8.8932, "lon": 76.6141},
    {"name": "Punalur", "lat": 9.0083, "lon": 76.9306},
    {"name": "Pathanamthitta", "lat": 9.2648, "lon": 76.7870},
    {"name": "Thiruvalla", "lat": 9.3833, "lon": 76.5833},
    {"name": "Chengannur", "lat": 9.3167, "lon": 76.6167},
    {"name": "Kayamkulam", "lat": 9.1759, "lon": 76.5020},
    {"name": "Alappuzha", "lat": 9.4981, "lon": 76.3388},
    {"name": "Changanassery", "lat": 9.4421, "lon": 76.5367},
    {"name": "Kottayam", "lat": 9.5916, "lon": 76.5222},
    {"name": "Ernakulam", "lat": 9.9816, "lon": 76.2999},
    {"name": "Kochi", "lat": 9.9312, "lon": 76.2673},
    {"name": "Aluva", "lat": 10.1081, "lon": 76.3522},
    {"name": "Perumbavoor", "lat": 10.1121, "lon": 76.4759},
    {"name": "Muvattupuzha", "lat": 9.9833, "lon": 76.5833},
    {"name": "Angamaly", "lat": 10.1960, "lon": 76.3860},
    {"name": "Thodupuzha", "lat": 9.8958, "lon": 76.7183},
    {"name": "Idukki", "lat": 9.8500, "lon": 76.9700},
    {"name": "Thrissur", "lat": 10.5276, "lon": 76.2144},
    {"name": "Guruvayur", "lat": 10.5944, "lon": 76.0400},
    {"name": "Chalakudy", "lat": 10.3000, "lon": 76.3333},
    {"name": "Palakkad", "lat": 10.7867, "lon": 76.6548},
    {"name": "Ottapalam", "lat": 10.7725, "lon": 76.3769},
    {"name": "Shoranur", "lat": 10.7556, "lon": 76.2694},
    {"name": "Malappuram", "lat": 11.0510, "lon": 76.0711},
    {"name": "Kozhikode", "lat": 11.2588, "lon": 75.7804},
    {"name": "Vatakara", "lat": 11.6082, "lon": 75.5912},
    {"name": "Kannur", "lat": 11.8745, "lon": 75.3704},
    {"name": "Payyanur", "lat": 12.1000, "lon": 75.2000},
    {"name": "Kanhangad", "lat": 12.3167, "lon": 75.0833},
    {"name": "Kasaragod", "lat": 12.4996, "lon": 74.9869},
    {"name": "Wayanad", "lat": 11.6854, "lon": 76.1320},
]

EDITING_SOFTWARE_KEYWORDS = ("photoshop", "snapseed", "picsart", "gimp", "lightroom", "affinity")
GPS_CONFLICT_DISTANCE_KM = 50
GEOCODE_NEAREST_RADIUS_KM = 40


def _dms_to_decimal(dms: tuple | None, ref: bytes | None) -> float | None:
    if not dms or not ref:
        return None
    degrees = dms[0][0] / dms[0][1]
    minutes = dms[1][0] / dms[1][1]
    seconds = dms[2][0] / dms[2][1]
    decimal = degrees + minutes / 60 + seconds / 3600
    if ref in (b"S", b"W"):
        decimal = -decimal
    return decimal


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def extract_exif(image_path: str) -> dict:
    """Pillow + piexif -> {capture_time, make, model, software, gps: {lat, lon} | None}.
    Any field piexif can't find is left None — "Not available" is a UI-layer
    decision, not something this function decides.
    """
    result: dict = {"capture_time": None, "make": None, "model": None, "software": None, "gps": None}
    try:
        exif_dict = piexif.load(image_path)
    except Exception:
        return result

    zeroth = exif_dict.get("0th", {})
    exif_ifd = exif_dict.get("Exif", {})
    gps_ifd = exif_dict.get("GPS", {})

    def _decode(value):
        return value.decode(errors="ignore").strip() if isinstance(value, bytes) else value

    result["make"] = _decode(zeroth.get(piexif.ImageIFD.Make))
    result["model"] = _decode(zeroth.get(piexif.ImageIFD.Model))
    result["software"] = _decode(zeroth.get(piexif.ImageIFD.Software))

    raw_dt = _decode(exif_ifd.get(piexif.ExifIFD.DateTimeOriginal))
    if raw_dt:
        try:
            result["capture_time"] = datetime.strptime(raw_dt, "%Y:%m:%d %H:%M:%S").isoformat()
        except ValueError:
            pass

    if gps_ifd:
        lat = _dms_to_decimal(gps_ifd.get(piexif.GPSIFD.GPSLatitude), gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef))
        lon = _dms_to_decimal(gps_ifd.get(piexif.GPSIFD.GPSLongitude), gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef))
        if lat is not None and lon is not None:
            result["gps"] = {"lat": lat, "lon": lon}

    return result


def _find_case_town(location_text: str | None) -> dict | None:
    if not location_text:
        return None
    lowered = location_text.lower()
    for town in KERALA_TOWNS:
        if town["name"].lower() in lowered:
            return town
    return None


def flag_conflicts(exif: dict, case: dict, upload_time: datetime) -> list[str]:
    """Editing-software tag on a claimed phone photo/screenshot; capture time
    after upload time; GPS >50km from the stated location."""
    conflicts: list[str] = []

    software = (exif.get("software") or "").lower()
    if any(keyword in software for keyword in EDITING_SOFTWARE_KEYWORDS):
        conflicts.append(f"Editing software tag found on a claimed screenshot ({exif['software']})")

    capture_time = exif.get("capture_time")
    if capture_time:
        try:
            if datetime.fromisoformat(capture_time) > upload_time:
                conflicts.append("Capture time recorded in the file is after the upload time")
        except ValueError:
            pass

    gps = exif.get("gps")
    town = _find_case_town(case.get("location"))
    if gps and town:
        distance = _haversine_km(gps["lat"], gps["lon"], town["lat"], town["lon"])
        if distance > GPS_CONFLICT_DISTANCE_KM:
            conflicts.append(
                f"GPS location is about {round(distance)} km from the stated place ({town['name']})"
            )

    return conflicts


def geocode_nearest_town(lat: float, lon: float) -> dict | None:
    """Nearest of KERALA_TOWNS within 40km, or None."""
    nearest = min(KERALA_TOWNS, key=lambda t: _haversine_km(lat, lon, t["lat"], t["lon"]))
    distance = _haversine_km(lat, lon, nearest["lat"], nearest["lon"])
    if distance > GEOCODE_NEAREST_RADIUS_KM:
        return None
    return {"name": nearest["name"], "distance_km": round(distance, 1)}


def run(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('metadata', case_id)."""
    db = get_db()
    case = db.cases.find_one({"id": case_id}) or {}
    files = list(db.files.find({"case_id": case_id, "kind": "media", "metadata": None}))

    for file_record in files:
        file_path = os.path.join(settings.evidence_dir, file_record["sha256"])
        if not os.path.exists(file_path):
            continue

        exif = extract_exif(file_path)
        conflicts = flag_conflicts(exif, case, file_record.get("uploaded_at") or datetime.utcnow())
        geo = geocode_nearest_town(exif["gps"]["lat"], exif["gps"]["lon"]) if exif.get("gps") else None

        metadata = {
            "capture_time": exif["capture_time"],
            "make": exif["make"] or "Not available",
            "model": exif["model"] or "Not available",
            "software": exif["software"] or "Not available",
            "gps": exif["gps"],
            "geo": geo,
            "conflict": conflicts[0] if conflicts else None,
            "conflicts": conflicts,
        }
        db.files.update_one({"id": file_record["id"]}, {"$set": {"metadata": metadata}})
