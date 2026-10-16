"""BNS / IT Act suggestions. docs/HACKATHON_PLAN.md §6.5 and Trace-QnA §4.

`suggest(events) -> [{section, title, summary, ingredients:[{text, event_ids}], matched_event_ids}]`

Default mode is `fixture`: 4 entries for the demo story, each with its legal
ingredients written out and mapped to timeline events by local keyword rules
(OTP shared -> 66C; impersonating a bank -> 319(2) and 66D; payment induced by
deception -> 318(4)). `live` mode calls InsightLaw with a 5 s timeout and falls
back to the fixture on any error, with an "offline" note.

Layout: statute -> required ingredients -> supporting evidence per ingredient.
Every suggestion is advisory: the SHO decides. Section numbers are labelled
"Advisory — sections to be verified" until a legal mentor checks them.
"""
import re

import requests

from app import custody
from app.config import settings
from app.db import get_db

BANK = re.compile(r"\bbank|kyc|official|department", re.IGNORECASE)


def _is(e: dict, *kinds: str) -> bool:
    return any(k in e.get("kinds", []) for k in kinds)


def _debit(e):
    return e["type"] == "Transaction" and (_is(e, "debit", "payment"))


def _impersonation(e):
    return e["type"] in ("Call", "Message") and (BANK.search(e["action"]) or _is(e, "link"))


def _device(e):
    return e["type"] in ("Call", "Message")


FIXTURE = [
    {"section": "BNS s.318(4)", "title": "Cheating and dishonestly inducing delivery of property",
     "summary": "Deceiving a person and dishonestly inducing them to deliver property or money.",
     "ingredients": [("Deception of the complainant", lambda e: _is(e, "link") or _impersonation(e)),
                     ("Dishonest inducement to deliver property or share access", lambda e: _is(e, "otp", "payment")),
                     ("Delivery of property / wrongful loss", _debit)]},
    {"section": "BNS s.319(2)", "title": "Cheating by personation",
     "summary": "Cheating by pretending to be another person; here, an official of the bank.",
     "ingredients": [("Pretending to be another person or authority", _impersonation),
                     ("Cheating carried out on the strength of that identity", _debit)]},
    {"section": "IT Act s.66C", "title": "Identity theft",
     "summary": "Fraudulent use of another person's password or other unique identification feature; here, the OTP.",
     "ingredients": [("Fraudulent use of a unique identification feature (OTP, password, PIN)", lambda e: _is(e, "otp")),
                     ("Use of it to access the complainant's account", lambda e: e["type"] == "Transaction" and "financial_record" in e["source_kinds"])]},
    {"section": "IT Act s.66D", "title": "Cheating by personation using a computer resource",
     "summary": "Cheating by personation using a communication device or computer resource.",
     "ingredients": [("Cheating by personation", _impersonation),
                     ("Using a communication device or computer resource", _device)]},
]


def _live(events: list[dict]) -> list[dict] | None:
    try:
        resp = requests.get(settings.insightlaw_base_url, params={"q": "online banking OTP fraud impersonation"},
                            timeout=settings.insightlaw_timeout_seconds)
        resp.raise_for_status()
        resp.json()
        # Response shape is still unconfirmed (§12); never map a guess into an
        # officer-facing suggestion. Fall through to the fixture.
        return None
    except (requests.RequestException, ValueError):
        return None


def suggest(events: list[dict]) -> tuple[list[dict], str]:
    source = "fixture"
    if settings.bns_mode == "live":
        live = _live(events)
        if live is not None:
            return live, "InsightLaw"
        source = "fixture (InsightLaw offline)"
    out = []
    for entry in FIXTURE:
        ingredients = [{"text": text, "event_ids": [e["id"] for e in events if rule(e)]} for text, rule in entry["ingredients"]]
        if not any(i["event_ids"] for i in ingredients):
            continue
        matched = sorted({eid for i in ingredients for eid in i["event_ids"]}, key=lambda x: int(x[1:]))
        out.append({"section": entry["section"], "title": entry["title"], "summary": entry["summary"],
                    "ingredients": ingredients, "matched_event_ids": matched})
    return out, source


def run(case_id: str) -> str:
    db = get_db()
    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}).sort("at", 1))
    suggestions, source = suggest(events)
    decided = {d["section"]: d for d in db.bns_decisions.find({"case_id": case_id, "decision": {"$ne": None}})}
    db.bns_decisions.delete_many({"case_id": case_id})
    for i, s in enumerate(suggestions, start=1):
        old = decided.get(s["section"], {})
        db.bns_decisions.insert_one({"id": f"b{i}", "case_id": case_id, **s, "source": source,
                                     "decision": old.get("decision"), "note": old.get("note", ""),
                                     "by": old.get("by"), "at": old.get("at")})
    custody.derived(case_id, "bns_suggestions", suggestions, model=f"keyword rules, {source}", prompt="bns-fixture-v1")
    return f"{len(suggestions)} BNS suggestions ({source})"
