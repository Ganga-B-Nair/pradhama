"""Metadata Agent — deterministic, owned by G.
docs/HACKATHON_PLAN.md §6.2.

Missing EXIF is "Not available" in neutral grey — never a warning (WhatsApp
strips it from nearly everything). Geocoding uses a small offline table of
~30 Kerala towns; no Nominatim, no network call.
"""

KERALA_TOWNS: list[dict] = []  # TODO(G): ~30 rows of {name, lat, lon}


def extract_exif(image_path: str) -> dict:
    """Pillow + piexif -> {capture_time, make, model, software, gps: {lat, lon} | None}."""
    raise NotImplementedError


def flag_conflicts(exif: dict, case: dict, upload_time) -> list[str]:
    """Editing-software tag on a claimed phone photo/screenshot; capture time
    after upload time; GPS >50km from the stated location."""
    raise NotImplementedError


def geocode_nearest_town(lat: float, lon: float) -> dict | None:
    """Nearest of KERALA_TOWNS within 40km, or None."""
    raise NotImplementedError


def run(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('metadata', case_id)."""
    raise NotImplementedError
