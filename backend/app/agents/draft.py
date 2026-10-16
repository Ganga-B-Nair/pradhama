"""Draft builder. docs/HACKATHON_PLAN.md §6.3 (draft narrative).

The LLM gets the ordered events and must return [{sentence, event_ids[]}].
A sentence with no event IDs, IDs that don't exist, or an amount that none of
its cited events carry is kept and marked "Unsupported — needs officer review"
(Trace-QnA §3) — never dropped silently. If the LLM is unavailable, a
deterministic template writes one sentence per event, each linked to it.

The Malayalam read-back is the complainant's own Whisper transcript, never
Malayalam written by the LLM (it is unreliable at Malayalam).
"""
from app import custody
from app.agents import extract
from app.agents.llm_client import LlmError, generate_json, unload
from app.db import get_db
from app.schemas import DraftVersion, checked
from app.util import IST, fmt_date, money, now_iso, parse_iso

PROMPT_VERSION = "draft-narrative-v1"
DRAFT_PROMPT = """Write the narrative of a First Information Report (FIR) in plain, neutral, formal English,
in chronological order, using ONLY the events below. Refer to the complainant as "the complainant".
Write dates as DD-MM-YYYY and times as HH:MM. Do not add any fact, name, number or amount that is not in the events.
Every sentence must cite the ids of the events it is based on.
Return JSON {{"sentences": [{{"sentence": "...", "event_ids": ["E1", ...]}}]}}.
Events:
{events}"""
DRAFT_SCHEMA = {"type": "object", "properties": {"sentences": {"type": "array", "items": {"type": "object", "properties": {
    "sentence": {"type": "string"}, "event_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["sentence", "event_ids"]}}}, "required": ["sentences"]}


def _when(e: dict) -> str:
    dt = parse_iso(e["at"]).astimezone(IST)
    return dt.strftime("on %d-%m-%Y") if e["prec"] != "exact" else dt.strftime("on %d-%m-%Y at %H:%M")


def template_sentence(e: dict) -> str:
    w = _when(e)
    actor, action = e["actor"], e["action"]
    if e["type"] == "Transaction" and "credit" in e.get("kinds", []):
        return f"{w.capitalize()}, {money(e['amount'])} was credited to the complainant's account."
    if e["type"] == "Transaction" and e["source_kinds"] != ["narration"]:
        acc = f" from account {e['account']}" if e.get("account") else ""
        dest = action.replace("Debit by ", "by ").replace("Debit, transfer to", "by transfer to").replace("Debit", "").strip()
        return f"{w.capitalize()}, {money(e['amount'])} was debited{acc}{' ' + dest if dest else ''}."
    if e["type"] == "Transaction":
        return f"The complainant states that {w}, {actor} called and asked for {money(e['amount'])} more, which the complainant sent." \
            if e.get("person") else f"The complainant states that {w} a payment of {money(e['amount'])} was made."
    if e["type"] == "Call":
        if actor == "Complainant":
            return f"{w.capitalize()}, the complainant {action[0].lower() + action[1:]}."
        who = actor.replace("Caller ", "")
        dur = action.split("(", 1)[1].rstrip(")") if "(" in action else ""
        return f"{w.capitalize()}, the complainant received a call from {who}{' lasting ' + dur if dur else ''}."
    if e["type"] == "Message":
        if "link" in e.get("kinds", []):
            return f"{w.capitalize()}, {actor.replace('Caller ', 'the caller ')} sent a link on WhatsApp ({e.get('url')})."
        if "otp" in e.get("kinds", []):
            return f"{w.capitalize()}, the complainant shared a one-time password (OTP) on WhatsApp."
        return f"{w.capitalize()}, {actor.lower() if actor == 'Complainant' else actor} sent a WhatsApp message: {action.split(': ', 1)[-1]}"
    if e["type"] == "Media":
        return f"{w.capitalize()}, a photograph was taken{' at ' + e['place'] if e.get('place') else ''} ({action.split('(')[-1].rstrip(')')})."
    return f"{w.capitalize()}, {action}."


def _src(event_ids: list[str], events: dict) -> list[dict]:
    out = []
    for eid in event_ids:
        for s in events[eid]["src"]:
            if s not in out:
                out.append(s)
    return out


def _check(sentence: str, ids: list[str], events: dict) -> bool:
    if not ids:
        return False
    cited = {events[i].get("amount") for i in ids} | {sum(events[i].get("amount") or 0 for i in ids)}
    return all(a in cited for a in extract.extract_amounts(sentence.replace("₹", "Rs ")))


def build_sentences(events: list[dict], stated_total, total_src) -> tuple[list[dict], str]:
    by_id = {e["id"]: e for e in events}
    model = "template (LLM unavailable)"
    sentences = []
    if events:
        lines = "\n".join(
            f"- {e['id']} | {parse_iso(e['at']).astimezone(IST).strftime('%d-%m-%Y %H:%M') if e['prec'] == 'exact' else fmt_date(e['at']) + ' (date only)'}"
            f" | {e['type']} | {e['actor']} | {e['action']}{' | ' + money(e['amount']) if e.get('amount') else ''}"
            f"{' | stated by the complainant only' if e['source_kinds'] == ['narration'] else ''}" for e in events)
        try:
            result, model = generate_json(DRAFT_PROMPT.format(events=lines), DRAFT_SCHEMA, unload_after=True)
            for raw in result.get("sentences", []):
                text = (raw.get("sentence") or "").strip()
                if not text:
                    continue
                ids = [i for i in raw.get("event_ids", []) if i in by_id]
                ok = _check(text, ids, by_id)
                sentences.append({"t": text, "event_ids": ids, "src": _src(ids, by_id), "supported": ok})
            if not sentences:
                raise LlmError("empty draft")
        except LlmError:
            model = "template (LLM unavailable)"
            sentences = [{"t": template_sentence(e), "event_ids": [e["id"]], "src": _src([e["id"]], by_id), "supported": True}
                         for e in events]
    if stated_total:
        sentences.append({"t": f"The complainant states that the total loss is {money(stated_total)}.", "event_ids": [],
                          "src": total_src, "supported": bool(total_src)})
    unload()
    return sentences, model


def run(case_id: str, user: str = custody.MACHINE) -> str:
    db = get_db()
    case = db.cases.find_one({"id": case_id}) or {}
    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}).sort("at", 1))
    a = case.get("analysis", {})
    total_src = [{"n": f["segment_id"]} for f in a.get("narration_facts") or [] if "total" in f.get("kinds", [])]
    sentences, model = build_sentences(events, a.get("stated_total"), total_src)
    prev = db.drafts.find_one({"case_id": case_id}, sort=[("v", -1)])
    prev_machine = db.drafts.find_one({"case_id": case_id, "edited": False}, sort=[("v", -1)])
    narrative = " ".join(s["t"] for s in sentences)
    if prev_machine and prev_machine["narrative"] == narrative:
        v = prev["v"]
        return f"Draft v{v} unchanged ({model})"
    first, last = (events[0]["at"], events[-1]) if events else (None, None)
    addr = case.get("complainant", {}).get("address", "")
    fields = {
        "place": (prev or {}).get("fields", {}).get("place") or (f"Online fraud; complainant at residence, {addr}" if addr else ""),
        "period": f"{parse_iso(first).astimezone(IST).strftime('%d-%m-%Y %H:%M')} to {fmt_date(last['at'])}" if events else "",
        "report_date": fmt_date(case.get("created_at")),
        "delay_reason": (prev or {}).get("fields", {}).get("delay_reason", ""),
    }
    v = (prev["v"] + 1) if prev else 1
    doc = {"case_id": case_id, "v": v, "by": custody.MACHINE, "at": now_iso(), "edited": False,
           "note": "Machine-generated draft" + (" (analysis re-run)" if prev else ""), "model": model,
           "fields": fields, "narrative": narrative, "sentences": sentences}
    db.drafts.insert_one(dict(checked(DraftVersion, doc)))
    custody.derived(case_id, f"draft_v{v}", {"fields": fields, "sentences": sentences}, model=model, prompt=PROMPT_VERSION)
    unsupported = sum(1 for s in sentences if not s["supported"])
    return f"Draft v{v}: {len(sentences)} sentences ({unsupported} unsupported), written by {model}"
