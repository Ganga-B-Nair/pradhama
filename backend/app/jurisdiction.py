"""Jurisdiction Lookup: which police station covers a PIN code.

For each PIN the lookup runs three visible steps, and every step is shown to
the officer with its inputs and outputs:

1. Google Places (Text Search, "police station near PIN <pin>, Kerala") gives
   the nearest station Google knows and its coordinates. The station's
   address is checked for the PIN.
2. The Kerala Police nearby-stations service (ps.keralapolice.gov.in/api/getps)
   is queried at those coordinates, giving official stations with distances
   and page links.
3. Cross-check: the Google station name is compared with the Kerala Police
   list. Verdict: "match" (Google's station is Kerala Police's nearest),
   "partial" (it is in the list but not nearest), "mismatch", or "unverified"
   (a source was unavailable).

TRACE only recommends; the officer chooses the stations. Results are cached
per PIN in MongoDB so a station that loses connectivity still shows the last
lookup, clearly marked with its date.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from app.config import settings
from app.db import get_db
from app.util import now_iso, parse_iso

TIMEOUT = 10
CACHE_DAYS = 7
UA = "Mozilla/5.0 (TRACE station assistant)"
PIN_RE = re.compile(r"(?<![\d.])([1-8]\d{5})(?![\d.])")


def norm_station(name: str) -> str:
    n = (name or "").lower()
    n = re.sub(r"\b(police\s+station|police|station|ps|p\.s\.)\b", " ", n)
    return re.sub(r"[^a-z]", "", n)


def google_station(pin: str) -> dict:
    if not settings.google_maps_api_key:
        raise RuntimeError("No Google Maps API key configured")
    r = requests.post(
        "https://places.googleapis.com/v1/places:searchText",
        json={"textQuery": f"police station near PIN {pin}, Kerala, India", "regionCode": "IN", "maxResultCount": 3},
        headers={"X-Goog-Api-Key": settings.google_maps_api_key,
                 "X-Goog-FieldMask": "places.displayName,places.location,places.formattedAddress"},
        timeout=TIMEOUT)
    r.raise_for_status()
    places = r.json().get("places") or []
    if not places:
        raise RuntimeError("Google returned no police station for this PIN")
    out = [{"name": p["displayName"]["text"], "lat": p["location"]["latitude"], "lon": p["location"]["longitude"],
            "address": p.get("formattedAddress", ""), "pin_in_address": pin in p.get("formattedAddress", "")} for p in places]
    best = next((p for p in out if p["pin_in_address"]), out[0])
    return {"best": best, "candidates": out}


def kerala_police_nearby(lat: float, lon: float) -> list[dict]:
    """Some of the site's servers answer with an expired certificate, so a
    failed request is tried again (certificate still checked)."""
    try:
        return _kerala_police_nearby(lat, lon)
    except requests.exceptions.SSLError:
        return _kerala_police_nearby(lat, lon)


def _kerala_police_nearby(lat: float, lon: float) -> list[dict]:
    base = settings.kerala_police_base_url.rstrip("/")
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    home = s.get(base + "/", timeout=TIMEOUT)  # starts a fresh site session (ci_session cookie)
    m = re.search(r'name="ci_csrf_token"\s+value="([^"]*)"', home.text)
    r = s.post(base + "/api/getps", data={"ci_csrf_token": m.group(1) if m else "", "lon": str(lon), "lat": str(lat)},
               headers={"X-Requested-With": "XMLHttpRequest", "Origin": base, "Referer": base + "/",
                        "Accept": "application/json, text/javascript, */*; q=0.01"}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(data.get("msg") or "Kerala Police service returned no stations")
    return [{"name": " ".join(p["ps_name"].split()), "link": p["link"], "distance_km": float(p["distance"])}
            for p in data.get("nps", [])]


def lookup(pin: str) -> dict:
    steps, g, kp = [], None, []
    try:
        g = google_station(pin)
        b = g["best"]
        steps.append({"step": "Google Maps", "ok": True,
                      "detail": f"Searched “police station near PIN {pin}, Kerala”. Nearest result: {b['name']} at "
                                f"{b['lat']:.5f}, {b['lon']:.5f} ({b['address']}). "
                                + ("The address contains the PIN." if b["pin_in_address"] else "The address does not contain the PIN; treat with care.")})
    except Exception as exc:  # noqa: BLE001 - shown to the officer
        steps.append({"step": "Google Maps", "ok": False, "detail": f"Not available: {exc}"})
    if g:
        try:
            kp = kerala_police_nearby(g["best"]["lat"], g["best"]["lon"])
            steps.append({"step": "Kerala Police", "ok": True,
                          "detail": "Nearby stations at those coordinates: " + "; ".join(f"{s['name']} ({s['distance_km']} km)" for s in kp)})
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "Kerala Police", "ok": False, "detail": f"Not available: {exc}"})
    else:
        steps.append({"step": "Kerala Police", "ok": False, "detail": "Skipped: needs the coordinates from step 1."})

    verdict, why = "unverified", "One of the two sources was unavailable, so the result could not be cross-checked."
    if g and kp:
        gname = norm_station(g["best"]["name"])
        hits = [i for i, s in enumerate(kp) if norm_station(s["name"]) and (norm_station(s["name"]) in gname or gname in norm_station(s["name"]))]
        if hits and hits[0] == 0:
            verdict, why = "match", f"Google's station ({g['best']['name']}) is Kerala Police's nearest station ({kp[0]['name']})."
        elif hits:
            verdict, why = "partial", (f"Google's station ({g['best']['name']}) is in the Kerala Police list at position {hits[0] + 1}; "
                                       f"Kerala Police's nearest is {kp[0]['name']}. Check which one covers the area.")
        else:
            verdict, why = "mismatch", (f"Google's station ({g['best']['name']}) is not in the Kerala Police list "
                                        f"({', '.join(s['name'] for s in kp)}). Confirm the jurisdiction before sending.")
    steps.append({"step": "Cross-check", "ok": verdict in ("match", "partial"), "detail": why})

    stations = [{**s, "source": "Kerala Police", "recommended": i == 0 and verdict in ("match", "partial")}
                for i, s in enumerate(kp)]
    if g and verdict in ("mismatch", "unverified"):
        stations.append({"name": g["best"]["name"], "link": None, "distance_km": None, "source": "Google Maps",
                         "recommended": False})
    return {"pin": pin, "verdict": verdict, "steps": steps, "stations": stations,
            "google": g["best"] if g else None, "looked_up_at": now_iso(), "cached": False}


def lookup_cached(pin: str, refresh: bool = False) -> dict:
    db = get_db()
    hit = db.jurisdiction_cache.find_one({"pin": pin}, {"_id": 0})
    fresh = hit and parse_iso(hit["result"]["looked_up_at"]) > datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)
    if hit and fresh and not refresh:
        return {**hit["result"], "cached": True}
    if not settings.jurisdiction_online:
        if hit:
            return {**hit["result"], "cached": True}
        return {"pin": pin, "verdict": "unverified", "stations": [], "google": None, "looked_up_at": None, "cached": False,
                "steps": [{"step": "Lookup", "ok": False, "detail": "Online lookup is switched off (JURISDICTION_ONLINE=0) and there is no saved result."}]}
    res = lookup(pin)
    if res["verdict"] != "unverified":  # both sources answered; a half result is not saved
        db.jurisdiction_cache.replace_one({"pin": pin}, {"pin": pin, "result": res}, upsert=True)
    elif hit:
        return {**hit["result"], "cached": True,
                "steps": hit["result"]["steps"] + [{"step": "Refresh", "ok": False, "detail": "A fresh lookup failed; showing the saved result."}]}
    return res


def lookup_many(pins: list[str], refresh: bool = False) -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=4) as ex:
        return dict(zip(pins, ex.map(lambda p: lookup_cached(p, refresh), pins)))
