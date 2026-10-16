"""BNS/IT Act suggestion adapter — V builds the live path, G owns the fixture.
docs/HACKATHON_PLAN.md §6.5.

Default mode is "fixture": 4 hardcoded entries for the demo story (BNS 318(4),
BNS 319(2), IT Act 66C, IT Act 66D), matched to events by local keyword rules.
"live" mode calls InsightLaw if BNS_MODE=live; 5s timeout; any error falls
back to the fixture and the UI shows an "offline" note.

InsightLaw's response shape is UNKNOWN as of this scaffold — the only
confirmed contract is:
    GET https://insightlaw.in?q=<term>  ->  JSON (no visible auth key)
Inspect the real response before relying on `live` mode; until then BNS_MODE
should stay "fixture" (the .env.example default).

SECTION NUMBERS ARE UNVERIFIED — every suggestion carries "Advisory: SHO
decides" and is labelled "Advisory — sections to be verified" until a legal
mentor checks them (docs Appendix B).
"""
import uuid

import requests

from app.config import settings
from app.custody import append_entry
from app.db import get_db

FIXTURE_SUGGESTIONS = [
    {
        "section": "BNS 318(4)",
        "title": "Cheating",
        "ingredients": [
            "Deception of the complainant",
            "Inducement to part with property",
            "Wrongful loss or damage",
        ],
        "keywords": ["deceiv", "induce", "cheat", "wrongful loss", "paid", "transfer", "sent money"],
    },
    {
        "section": "BNS 319(2)",
        "title": "Cheating by personation",
        "ingredients": [
            "Pretending to be another person or authority",
            "Deception based on that false identity",
        ],
        "keywords": [
            "impersonat", "pretend", "posed as", "posing as", "fake bank official",
            "claimed to be", "claiming to be", "representing the bank", "from the bank",
        ],
    },
    {
        "section": "IT Act 66C",
        "title": "Identity theft",
        "ingredients": ["Fraudulent or dishonest use of a unique identification feature (e.g. OTP, password, PIN)"],
        "keywords": ["otp", "shared the otp", "password", "pin number"],
    },
    {
        "section": "IT Act 66D",
        "title": "Cheating by personation by using computer resource",
        "ingredients": [
            "Cheating by personation",
            "Committed using a computer resource or communication device",
        ],
        "keywords": ["call", "sms", "whatsapp", "phishing", "fraudulent link", "fake website"],
    },
]


def _call_insightlaw(query: str) -> list[dict] | None:
    try:
        resp = requests.get(
            settings.insightlaw_base_url,
            params={"q": query},
            timeout=settings.insightlaw_timeout_seconds,
        )
        resp.raise_for_status()
        resp.json()
        # InsightLaw's real response shape is unknown — mapping it into
        # {section, title, ingredients} is intentionally not implemented so a
        # malformed guess can't silently reach the officer. BNS_MODE=live will
        # always fall through to the fixture until this is filled in after
        # inspecting a real response.
        return None
    except (requests.RequestException, ValueError):
        return None


def suggest(facts: list[dict]) -> list[dict]:
    """facts: [{"text": str, "event_ids": [str, ...]}] — short strings extracted
    from the case's events/narration, each tagged with the event IDs it came
    from. Returns [{section, title, ingredients, matched_event_ids, source}]."""
    if settings.bns_mode == "live":
        for fact in facts:
            result = _call_insightlaw(fact["text"])
            if result is not None:
                return result
        # falls through to the fixture below on any failure — never leave the
        # officer with nothing because an external service was unreachable

    results = []
    for entry in FIXTURE_SUGGESTIONS:
        matched_event_ids: set[str] = set()
        matched = False
        for fact in facts:
            lowered = fact["text"].lower()
            if any(keyword in lowered for keyword in entry["keywords"]):
                matched = True
                matched_event_ids.update(fact.get("event_ids", []))
        if matched:
            results.append({
                "section": entry["section"],
                "title": entry["title"],
                "ingredients": entry["ingredients"],
                "matched_event_ids": sorted(matched_event_ids),
                "source": "fixture",
            })
    return results


def run(case_id: str) -> None:
    """Entry point called from app.worker at the end of the draft stage (the
    "Draft builder" step in the TRD covers both the narrative and the BNS
    suggestions). Builds `facts` from timeline events and the narration text,
    then stores suggestions to db.bns_decisions."""
    db = get_db()
    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}))
    narrations = list(db.narrations.find({"case_id": case_id}, {"_id": 0}))

    facts = [{"text": event["summary"], "event_ids": [event["id"]]} for event in events]
    for narration in narrations:
        facts.append({"text": narration["english_text"], "event_ids": []})

    db.bns_decisions.delete_many({"case_id": case_id, "decision": "pending"})
    suggestions = suggest(facts)
    to_insert = [
        {
            "id": str(uuid.uuid4()),
            "case_id": case_id,
            "section": s["section"],
            "title": s["title"],
            "ingredients": s["ingredients"],
            "matched_event_ids": s["matched_event_ids"],
            "decision": "pending",
            "source": s["source"],
        }
        for s in suggestions
    ]
    if to_insert:
        db.bns_decisions.insert_many([dict(s) for s in to_insert])
    append_entry(case_id, "ARTIFACT_DERIVED", {"artifact": "bns_suggestions", "count": len(to_insert)})
