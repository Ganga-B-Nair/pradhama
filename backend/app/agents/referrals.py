"""Forensic referral list: files Content Triage or Metadata flagged, ranked by
screening score. The SHO reorders, removes (with a reason), adds and confirms.
Any machine change clears the confirmation."""
from app import custody
from app.agents.triage import LIMITATION_TEXT
from app.db import get_db


def reason_for(f: dict) -> str:
    parts = []
    s, m = f.get("screen") or {}, f.get("meta") or {}
    if s.get("status") == "review":
        parts.append(f"Recommend forensic review (score {s['score']}). " + "; ".join(s.get("reasons", [])))
    parts += m.get("conflicts", [])
    return ". ".join(p.rstrip(".") for p in parts) + "."


def run(case_id: str) -> str:
    db = get_db()
    doc = db.referrals.find_one({"case_id": case_id}) or {"case_id": case_id, "items": [], "removed": [], "confirmed": None}
    have = {r["file"] for r in doc["items"]} | {r["file"] for r in doc["removed"]}
    flagged = [f for f in db.files.find({"case_id": case_id, "status": "accepted"})
               if ((f.get("screen") or {}).get("status") == "review" or (f.get("meta") or {}).get("status") == "Conflict")
               and f["ev_id"] not in have]
    flagged.sort(key=lambda f: -((f.get("screen") or {}).get("score") or 0) - (0.2 if (f.get("meta") or {}).get("conflicts") else 0))
    for f in flagged:
        doc["items"].append({"file": f["ev_id"], "reason": reason_for(f), "conf": (f.get("screen") or {}).get("score"),
                             "by": custody.MACHINE})
    if flagged:
        doc["confirmed"] = None
    db.referrals.replace_one({"case_id": case_id}, doc, upsert=True)
    return f"{len(doc['items'])} files on the forensic referral list" + (f" ({len(flagged)} new)" if flagged else "")


LIMITS = LIMITATION_TEXT
