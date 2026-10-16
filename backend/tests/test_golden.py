"""Golden-bundle regression test — docs/HACKATHON_PLAN.md §9.

Runs against a SEPARATE database (`trace_test`) so test runs never show up in
the demo case list. Uses the typed English narration from golden/expected.json
so the test doesn't wait on speech-to-text; the audio path is exercised on stage.

    MONGO_URI=... pytest tests/test_golden.py
"""
import glob
import json
import os

os.environ["MONGO_DB"] = "trace_test"  # before app.db is imported anywhere

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.gaps import BLOCKED_WORDS, TEMPLATES, lint  # noqa: E402
from app.db import get_client  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "golden")
EXPECTED = json.load(open(os.path.join(ROOT, "expected.json"), encoding="utf-8"))


def test_gap_templates_have_no_blocked_words():
    for rule, text in TEMPLATES.items():
        assert not lint(text), f"{rule} template contains a blocked word"
    assert "credibility" in BLOCKED_WORDS and "fake" in BLOCKED_WORDS


@pytest.fixture(scope="module")
def client():
    get_client().drop_database("trace_test")
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/login", json={"username": "officer", "password": "officer123"})
        assert r.status_code == 200
        yield c
    get_client().drop_database("trace_test")


def test_golden_bundle_end_to_end(client):
    from app import custody
    from app.worker import run_pipeline_sync

    case = client.post("/api/cases", json={**EXPECTED["complainant"], "consent": True}).json()
    cid = case["id"]
    files = [("files", (os.path.basename(p), open(p, "rb").read())) for p in sorted(glob.glob(os.path.join(ROOT, "bundle", "*")))
             if not p.endswith(".mp3")]
    uploaded = client.post(f"/api/cases/{cid}/files", files=files).json()
    assert all(u["status"] == "accepted" for u in uploaded), uploaded
    client.post(f"/api/cases/{cid}/narration/typed", json={"text": " ".join(EXPECTED["narration_english"])})

    run_id = client.post(f"/api/cases/{cid}/runs", json={}).json()["run_id"]
    run_pipeline_sync(run_id)  # the queue worker would do this in the background
    run = client.get(f"/api/runs/{run_id}").json()
    assert [s["state"] for s in run["steps"]] == ["done"] * 6, run["steps"]

    events = client.get(f"/api/cases/{cid}/timeline").json()["events"]
    assert len(events) == EXPECTED["events"]
    assert all(e["src"] for e in events), "every event must cite a source"

    gaps = client.get(f"/api/cases/{cid}/gaps").json()["gaps"]
    assert sorted(g["rule"] for g in gaps) == EXPECTED["gaps_rules"]
    assert not any(g["lint"] for g in gaps)

    bns = client.get(f"/api/cases/{cid}/bns").json()["suggestions"]
    assert [b["section"] for b in bns] == EXPECTED["bns_sections"]

    manifest = client.get(f"/api/cases/{cid}/manifest").json()["files"]
    assert sum(1 for f in manifest if f.get("dup") and not f["dup"]["canonical"]) == EXPECTED["duplicates_grouped"]
    assert [f["name"] for f in manifest if (f.get("meta") or {}).get("status") == "Conflict"] == EXPECTED["metadata_conflicts"]
    refs = client.get(f"/api/cases/{cid}/referrals").json()["items"]
    assert len(refs) >= EXPECTED["referrals_min"]

    draft = client.get(f"/api/cases/{cid}/draft").json()["versions"][-1]
    assert all(s["src"] or s["supported"] is False for s in draft["sentences"]), "sentence with no source must be flagged"

    # Answer G-01/G-09 by uploading the missing record, then re-run the checks.
    follow = os.path.join(ROOT, "followup", "bank_sms_02oct.txt")
    client.post(f"/api/cases/{cid}/files", files=[("files", ("bank_sms_02oct.txt", open(follow, "rb").read()))])
    res = client.post(f"/api/cases/{cid}/gaps/recheck").json()
    resolved_rules = sorted(g["rule"] for g in client.get(f"/api/cases/{cid}/gaps").json()["gaps"]
                            if g["id"] in res["resolved"])
    assert resolved_rules == EXPECTED["after_followup_resolved_rules"]

    assert custody.verify(cid)["ok"]
    from app.db import get_db
    get_db().audit_chain.update_one({"case_id": cid, "seq": 3}, {"$set": {"detail": "altered"}})
    bad = custody.verify(cid)
    assert not bad["ok"] and bad["bad"]["seq"] == 3
