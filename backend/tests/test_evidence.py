"""Evidence intake: GridFS storage, the 10-file limit, custody chain, and the
deterministic agents reading originals back from MongoDB.

Runs against a separate database (`trace_test`), dropped before and after.

    docker compose run --rm backend pytest -q
"""
import hashlib
import io
import os

os.environ["MONGO_DB"] = "trace_test"  # before app.db is imported anywhere

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.gaps import BLOCKED_WORDS, TEMPLATES, lint  # noqa: E402
from app.db import get_client  # noqa: E402

SMS = b"01-10-26 14:05 Dear Customer, A/c XX1111 debited by Rs.5,000.00 on 01Oct26, IMPS to A/c XXXX2222. -Bank\n"
CALLS = b"date,time,number,type,duration\n2026-10-01,10:12,+91 90000 00001,incoming,00:01:00\n"


def test_gap_templates_have_no_blocked_words():
    for rule, text in TEMPLATES.items():
        assert not lint(text), f"{rule} template contains a blocked word"
    assert "credibility" in BLOCKED_WORDS and "fake" in BLOCKED_WORDS


@pytest.fixture(scope="module")
def client():
    get_client().drop_database("trace_test")
    from app.main import app
    with TestClient(app) as c:
        assert c.post("/api/login", json={"username": "officer", "password": "officer123"}).status_code == 200
        yield c
    get_client().drop_database("trace_test")


@pytest.fixture(scope="module")
def case_id(client):
    r = client.post("/api/cases", json={"name": "Test Complainant", "address": "Kochi", "language": "English", "consent": True})
    return r.json()["id"]


def test_upload_is_stored_in_gridfs_with_matching_hash(client, case_id):
    from app import storage

    res = client.post(f"/api/cases/{case_id}/files", files=[("files", ("bank_sms.txt", SMS)), ("files", ("call_log.csv", CALLS))]).json()
    assert [r["status"] for r in res] == ["accepted", "accepted"]
    assert [r["ev_id"] for r in res] == ["EV-001", "EV-002"]
    assert res[0]["sha256"] == hashlib.sha256(SMS).hexdigest()
    assert storage.get(res[0]["sha256"]) == SMS
    view = client.get(f"/api/cases/{case_id}/files/EV-001/view").json()
    assert view["lines"][0].startswith("01-10-26 14:05")
    assert client.get(f"/api/cases/{case_id}/files/EV-002/raw").content == CALLS


def test_rejected_file_is_not_stored(client, case_id):
    res = client.post(f"/api/cases/{case_id}/files", files=[("files", ("photo.jpg", b"not really a jpeg"))]).json()
    assert res[0]["status"] == "rejected" and res[0]["ev_id"] is None
    assert client.get(f"/api/cases/{case_id}/files/limit").json()["used"] == 2


def test_limit_of_ten_evidence_files(client, case_id):
    too_many = [("files", (f"note{i}.txt", f"note {i}\n".encode())) for i in range(9)]
    r = client.post(f"/api/cases/{case_id}/files", files=too_many)
    assert r.status_code == 409 and "Only 8 more" in r.json()["detail"]
    ok = client.post(f"/api/cases/{case_id}/files", files=too_many[:8]).json()
    assert all(x["status"] == "accepted" for x in ok)
    lim = client.get(f"/api/cases/{case_id}/files/limit").json()
    assert (lim["used"], lim["left"]) == (10, 0)
    assert client.post(f"/api/cases/{case_id}/files", files=[("files", ("extra.txt", b"x\n"))]).status_code == 409


def test_excel_statement_and_ocr_screenshot(client):
    """Formats that used to produce nothing: an Excel statement and a payment
    screenshot read by real Tesseract OCR."""
    from openpyxl import Workbook
    from PIL import Image, ImageDraw, ImageFont

    from app.agents import timeline, triage

    cid = client.post("/api/cases", json={"name": "Second Case", "language": "English", "consent": True}).json()["id"]
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Narration", "Withdrawal", "Deposit", "Balance"])
    ws.append(["01/10/2026", "OPENING BALANCE", None, None, "1,72,310.55"])
    ws.append(["01/10/2026", "IMPS/P2A/XXXX9032", "20,000.00", None, "1,52,310.55"])
    xbuf = io.BytesIO()
    wb.save(xbuf)

    img = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    except OSError:
        font = ImageFont.load_default(34)
    for i, t in enumerate(["Payment successful", "Rs 40,000", "Paid to kychelp.desk@ybl", "UPI Ref 627114012345", "1 Oct 2026, 2:22 pm"]):
        d.text((40, 40 + i * 100), t, fill="black", font=font)
    ibuf = io.BytesIO()
    img.save(ibuf, format="PNG")

    res = client.post(f"/api/cases/{cid}/files", files=[
        ("files", ("statement_oct.xlsx", xbuf.getvalue())), ("files", ("gpay_receipt.png", ibuf.getvalue()))]).json()
    assert [r["status"] for r in res] == ["accepted", "accepted"], res
    triage.run(cid)
    timeline.build(cid, use_llm=False)
    events = client.get(f"/api/cases/{cid}/timeline").json()["events"]
    got = sorted((e["amount"], e["source_kinds"][0]) for e in events)
    assert got == [(20000, "financial_record"), (40000, "screenshot")], events


def test_agents_read_originals_from_mongodb(client, case_id):
    from app import custody
    from app.agents import timeline, triage

    triage.run(case_id)
    timeline.build(case_id, use_llm=False)
    events = client.get(f"/api/cases/{case_id}/timeline").json()["events"]
    assert {e["type"] for e in events} == {"Transaction", "Call"}
    assert all(e["src"] for e in events)
    assert custody.verify(case_id)["ok"]
