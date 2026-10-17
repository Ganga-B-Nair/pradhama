"""Jurisdiction Lookup: reading IP trace reports, the Google / Kerala Police
cross-check, and the officer -> SHO -> dispatch flow for notices.

No network: both lookup sources are replaced with fixed answers.
Runs against a separate database (`trace_test_j`), dropped before and after.

    docker compose run --rm backend pytest -q
"""
import os

os.environ["MONGO_DB"] = "trace_test_j"  # before app.db is imported anywhere

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import jurisdiction  # noqa: E402
from app.agents import parsers  # noqa: E402
from app.db import get_client  # noqa: E402

REPORT = b"""IP ADDRESS TRACE REPORT (SAMPLE FORMAT)
IP Address | Date/Time (IST) | ISP | PIN Code | Area
203.0.113.24 | 01-10-2026 10:20 | Example Telecom | 682304 | Maradu, Ernakulam
198.51.100.77 | 01-10-2026 14:40 | Sample Broadband | 682030 | Kakkanad, Ernakulam
"""
GOOGLE = {"best": {"name": "Maradu Police Station", "lat": 9.934, "lon": 76.318, "address": "Maradu, Kerala 682304",
                   "pin_in_address": True}, "candidates": []}
KP = [{"name": "Maradu", "link": "https://ps.keralapolice.gov.in/maradu-ps", "distance_km": 1.07},
      {"name": "Panangad", "link": "https://ps.keralapolice.gov.in/panangad-ps", "distance_km": 2.89}]


def test_parser_reads_rows_with_ip_and_pin():
    rows = parsers.parse_ip_traces({"ev_id": "EV-001"}, REPORT.decode().splitlines(), 2026)
    assert [(r["ip"], r["pin"], r["area"]) for r in rows] == [("203.0.113.24", "682304", "Maradu, Ernakulam"),
                                                             ("198.51.100.77", "682030", "Kakkanad, Ernakulam")]
    assert rows[0]["src"] == {"f": "EV-001", "l": 3} and rows[0]["at"].startswith("2026-10-01T10:20")


def test_parser_ignores_lines_without_a_pin():
    assert parsers.parse_ip_traces({"ev_id": "x"}, ["Login from 203.0.113.24 at 10:20"], 2026) == []


@pytest.mark.parametrize("google,kerala,same", [
    ("Maradu Police Station", "Maradu", True),
    ("Kasaba Police Station, Kozhikode", "Kozhikode City Kasaba", True),  # word order differs
    ("Thrikkakara Janamaithri Police Station", "Thrikkakara", True),
    ("Thampanoor Police Station Thiruvananthapuram", "Thiruvananthapuram Railway", False),
    ("Kasaba Police Station, Kozhikode", "Kozhikode City Vanitha", False),
    ("Town Police Station", "Kozhikode City Town", True),  # only a generic word to go on
    ("Thrissur East Police Station", "THRISSUR TOWN EAST", True),
    ("Police Station", "Maradu", False),  # nothing distinctive to compare
])
def test_station_names_compare_by_distinctive_words(google, kerala, same):
    assert jurisdiction.same_station(google, kerala) is same


@pytest.mark.parametrize("kp,verdict,recommended", [
    (KP, "match", ["Maradu"]),
    (list(reversed(KP)), "partial", ["Panangad"]),
    ([{"name": "Hill Palace", "link": "x", "distance_km": 1.0}], "mismatch", []),
])
def test_cross_check_verdicts(monkeypatch, kp, verdict, recommended):
    monkeypatch.setattr(jurisdiction, "google_station", lambda pin: GOOGLE)
    monkeypatch.setattr(jurisdiction, "kerala_police_nearby", lambda lat, lon: kp)
    res = jurisdiction.lookup("682304")
    assert res["verdict"] == verdict
    assert [s["name"] for s in res["stations"] if s["recommended"]] == recommended
    assert [s["step"] for s in res["steps"]] == ["Google Maps", "Kerala Police", "Cross-check"]


def test_google_unavailable_is_unverified_and_recommends_nothing(monkeypatch):
    def fail(pin):
        raise RuntimeError("No Google Maps API key configured")
    monkeypatch.setattr(jurisdiction, "google_station", fail)
    res = jurisdiction.lookup("682304")
    assert res["verdict"] == "unverified" and res["stations"] == []
    assert "Skipped" in res["steps"][1]["detail"]


@pytest.fixture(scope="module")
def client():
    get_client().drop_database("trace_test_j")
    from app.main import app
    with TestClient(app) as c:
        yield c
    get_client().drop_database("trace_test_j")


def login(c, who):
    assert c.post("/api/login", json={"username": who, "password": f"{who}123"}).status_code == 200


def test_officer_prepares_sho_approves_then_dispatch(client, monkeypatch):
    monkeypatch.setattr(jurisdiction, "google_station", lambda pin: GOOGLE)
    monkeypatch.setattr(jurisdiction, "kerala_police_nearby", lambda lat, lon: KP)
    login(client, "officer")
    cid = client.post("/api/cases", json={"name": "Test", "address": "Kochi", "language": "English", "consent": True}).json()["id"]
    client.post(f"/api/cases/{cid}/files", files=[("files", ("ip_trace.txt", REPORT))])

    st = client.get(f"/api/cases/{cid}/jurisdiction").json()
    assert [p["pin"] for p in st["pins"]] == ["682304", "682030"]  # read before analysis has run
    st = client.post(f"/api/cases/{cid}/jurisdiction/lookup", json={"pins": ["682304"]}).json()
    station = next(s for s in st["pins"][0]["lookup"]["stations"] if s["recommended"])

    body = {"kind": "Lookout notice", "subject": "s", "body": "b", "recipients": [{**station, "pin": "682304"}]}
    assert client.post(f"/api/cases/{cid}/notices", json=body).status_code == 422  # not confirmed
    n = client.post(f"/api/cases/{cid}/notices", json={**body, "confirmed": True}).json()[0]
    assert n["status"] == "Awaiting SHO approval"
    assert client.post(f"/api/cases/{cid}/notices/{n['id']}/decision", json={"decision": "approve"}).status_code == 403
    assert client.post(f"/api/cases/{cid}/notices/{n['id']}/dispatch", json={"channel": "Official email"}).status_code == 409

    login(client, "sho")
    assert client.post(f"/api/cases/{cid}/notices/{n['id']}/decision", json={"decision": "return"}).status_code == 422
    n = client.post(f"/api/cases/{cid}/notices/{n['id']}/decision", json={"decision": "approve"}).json()[0]
    assert n["status"] == "Approved for dispatch"
    n = client.post(f"/api/cases/{cid}/notices/{n['id']}/dispatch", json={"channel": "Official email", "note": "ref 12"}).json()[0]
    assert n["status"] == "Dispatched" and [h["step"] for h in n["history"]][-1] == "Dispatched by Official email"
    assert "Thomas Varghese (SHO)" in client.get(f"/api/cases/{cid}/notices/{n['id']}/print").text

    actions = [e["action"] for e in client.get(f"/api/cases/{cid}/audit").json()]
    for a in ("JURISDICTION_LOOKUP", "NOTICE_PREPARED", "NOTICE_APPROVED", "NOTICE_DISPATCHED", "NOTICE_PRINTED"):
        assert a in actions
    assert client.post(f"/api/cases/{cid}/audit/verify").json()["ok"]
