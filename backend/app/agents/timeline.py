"""Timeline Agent. docs/HACKATHON_PLAN.md §6.3.

Order of reliability, most reliable first:
1. Rule parsers (deterministic): WhatsApp .txt exports (`dd/mm/yy, hh:mm -` and
   `[dd/mm/yy hh:mm]`), bank SMS .txt (amount, account, UPI ID, IMPS/NEFT, time),
   call-log .csv, plus EXIF capture times of photographs. Every event carries
   its source file and line.
2. Narration: the LLM (JSON-schema output) reads the English segments and must
   cite the segment each fact came from; facts with no valid citation are
   dropped, and amounts/names must literally appear in the cited segment.
   If the LLM is unavailable, a rule-based reader of the same segments is used.
3. Merge: narration facts attach to the evidence events they describe; events
   within 5 minutes with the same amount and account become one event that
   lists all sources. Times are IST with precision exact / day / approximate.
"""
import csv
import io
import re
from datetime import datetime, timedelta

from app import custody
from app.agents import extract
from app.agents.llm_client import LlmError, generate_json
from app.agents.triage import read_text
from app.db import get_db
from app.schemas import TimelineEvent, checked
from app.util import IST, money, now_iso, parse_iso

WA_DASH = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}), (\d{1,2}:\d{2})\s?(?:[ap]m)? - ([^:]+): (.*)$", re.IGNORECASE)
WA_BRACKET = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),? (\d{1,2}:\d{2})(?::\d{2})?\] ([^:]+): (.*)$")
SMS_DT = re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})[ ,]+(\d{1,2}):(\d{2})")
SMS_D = re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\b")
MONEY_WORDS = re.compile(r"money (has )?gone|debited|deducted|lost|refund|withdrawn", re.IGNORECASE)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], start=1)}
MONTH_RE = "|".join(MONTHS)
DATE_A = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MONTH_RE})\b", re.IGNORECASE)
DATE_B = re.compile(rf"\b({MONTH_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE)
KIND_RULES = {
    "call": re.compile(r"\bcall(ed|ing|s)?\b|\bphon(e|ed)\b", re.IGNORECASE),
    "link": re.compile(r"\blinks?\b|\burl\b", re.IGNORECASE),
    "otp": re.compile(r"\botp\b|one[- ]time|password", re.IGNORECASE),
    "debit": re.compile(r"debited|taken|deducted|withdrawn|gone from|went from|money .*(several|many) times", re.IGNORECASE),
    "payment": re.compile(r"\b(sent|send|transferred|paid|pay|gave)\b", re.IGNORECASE),
    "total": re.compile(r"\b(in total|total|altogether|in all)\b", re.IGNORECASE),
}
NAME_PATTERNS = [re.compile(r"\bnamed\s+([A-Z][a-z]{2,})"), re.compile(r"\b([A-Z][a-z]{2,})\s+(?:called|phoned|asked)")]
NOT_NAMES = {"October", "September", "November", "December", "January", "February", "March", "April", "May", "June",
             "July", "August", "Bank", "KYC", "WhatsApp", "That", "The", "Then", "He", "She", "They", "In", "On"}

PROMPT_VERSION = "narration-facts-v1"
NARRATION_PROMPT = """You read numbered segments of a complainant's statement to the police (English translation).
For EACH segment, report only facts literally stated in that segment.
Return JSON {{"facts": [{{"segment_id": int, "date": "D Month" or null, "amount": number or null,
"kinds": [one or more of "call","link","otp","debit","payment","total"], "person": name or null}}]}}.
kinds: call = a phone call; link = a link was sent; otp = an OTP/password was shared; debit = money was
taken from the account; payment = the complainant sent/paid money; total = a stated total loss.
person = a named person other than the complainant. Do not guess. Use null when not stated.
Segments:
{segments}"""
NARRATION_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "object", "properties": {
        "segment_id": {"type": "integer"}, "date": {"type": ["string", "null"]}, "amount": {"type": ["number", "null"]},
        "kinds": {"type": "array", "items": {"type": "string"}}, "person": {"type": ["string", "null"]}},
        "required": ["segment_id", "kinds"]}}},
    "required": ["facts"],
}


def _dt(d: int, m: int, y: int, hh: int = 12, mm: int = 0) -> str:
    y = y + 2000 if y < 100 else y
    return datetime(y, m, d, hh, mm, tzinfo=IST).isoformat()


def _dur(raw: str) -> str:
    parts = [int(p) for p in re.findall(r"\d+", raw or "")]
    secs = parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else (parts[0] * 60 + parts[1] if len(parts) == 2 else (parts[0] if parts else 0))
    if not secs:
        return ""
    m, s = divmod(secs, 60)
    return f"{m} min {s} s" if m else f"{s} s"


def _ev(**kw) -> dict:
    base = {"prec": "exact", "amount": None, "account": None, "to_account": None, "upi": None, "ifsc": None,
            "phone": None, "url": None, "place": None, "person": None, "conf": 0.95, "src": [], "source_kinds": []}
    base.update(kw)
    return base


def parse_whatsapp(f: dict, text: str, complainant_first: str) -> list[dict]:
    events = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        m = WA_DASH.match(line.strip()) or WA_BRACKET.match(line.strip())
        if not m:
            continue
        date_s, time_s, sender, msg = m.groups()
        try:
            d, mo, y = (int(x) for x in date_s.split("/"))
            hh, mm = (int(x) for x in time_s.split(":"))
            at = _dt(d, mo, y, hh, mm)
        except ValueError:
            continue
        sender = sender.strip()
        is_complainant = sender.lower() in (complainant_first.lower(), "you", "me")
        phones = extract.extract_phones(sender)
        actor = "Complainant" if is_complainant else (f"Caller {extract.pretty_phone(phones[0])}" if phones else sender)
        urls, amount = extract.extract_urls(msg), extract.extract_amount(msg)
        if urls and not is_complainant:
            action, kinds = "Sent a link on WhatsApp", ["link"]
        elif is_complainant and extract.OTP_RE.match(msg):
            action, kinds = "Shared a one-time password (OTP) on WhatsApp", ["otp"]
        elif amount or MONEY_WORDS.search(msg):
            short = msg.strip() if len(msg) < 110 else msg[:107].strip() + "…"
            action, kinds = f"WhatsApp message: “{short}”", ["money"]
        else:
            continue
        events.append(_ev(at=at, type="Message", actor=actor, action=action, amount=amount,
                          phone=phones[0] if phones else None, url=urls[0] if urls else None,
                          src=[{"f": f["ev_id"], "l": line_no}], source_kinds=["conversation"], kinds=kinds, conf=0.95))
    return events


def parse_bank_sms(f: dict, text: str) -> list[dict]:
    events = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        low = line.lower()
        amount = extract.extract_amount(line)
        if amount is None or not re.search(r"\b(debited|credited)\b", low):
            continue
        m = SMS_DT.search(line)
        if m:
            d, mo, y, hh, mm = (int(x) for x in m.groups())
            at, prec = _dt(d, mo, y, hh, mm), "exact"
        else:
            m = SMS_D.search(line)
            if not m:
                continue
            at, prec = _dt(*(int(x) for x in m.groups())), "day"
        accounts = extract.extract_accounts(line)
        to_acc = extract.extract_to_account(line)
        from_acc = next((a for a in accounts if a != to_acc), None)
        upis = extract.extract_upi_ids(line)
        method = (re.search(r"\b(IMPS|NEFT|RTGS|UPI)\b", line, re.IGNORECASE) or [None])[0]
        ifsc = extract.extract_ifsc_codes(line)
        if "credited" in low:
            action = "Credit"
        elif upis:
            action = f"Debit by UPI to {upis[0]}"
        elif method and to_acc:
            action = f"Debit by {method.upper()} to A/c {to_acc}"
        elif to_acc:
            action = f"Debit, transfer to A/c {to_acc}"
        else:
            action = "Debit"
        events.append(_ev(at=at, prec=prec, type="Transaction",
                          actor=f"Complainant (A/c {from_acc})" if from_acc else "Complainant",
                          action=action, amount=amount, account=from_acc, to_account=to_acc,
                          upi=upis[0] if upis else None, ifsc=ifsc[0] if ifsc else None,
                          src=[{"f": f["ev_id"], "l": line_no}], source_kinds=["financial_record"],
                          kinds=["debit"] if "debited" in low else ["credit"], conf=0.99))
    return events


def parse_call_log(f: dict, text: str) -> list[dict]:
    events = []
    reader = csv.DictReader(io.StringIO(text))
    cols = {c.strip().lower(): c for c in (reader.fieldnames or [])}
    get = lambda row, k: (row.get(cols.get(k, ""), "") or "").strip()  # noqa: E731
    for line_no, row in enumerate(reader, start=2):
        number, ctype, dur = get(row, "number"), get(row, "type").lower(), get(row, "duration")
        at = None
        try:
            if get(row, "timestamp"):
                at = parse_iso(get(row, "timestamp")).isoformat()
            else:
                y, mo, d = (int(x) for x in get(row, "date").split("-"))
                hh, mm = (int(x) for x in get(row, "time").split(":")[:2])
                at = _dt(d, mo, y, hh, mm)
        except (ValueError, AttributeError):
            continue
        phone = extract.normalize_phone(number) if number else None
        pretty = extract.pretty_phone(phone) if phone else "an unknown number"
        d_txt = _dur(dur)
        if ctype.startswith("out"):
            actor, action = "Complainant", f"Called {pretty}" + (f" ({d_txt})" if d_txt else " (not answered)")
        elif ctype.startswith("miss"):
            actor, action = f"Caller {pretty}", "Missed call to the complainant"
        else:
            actor, action = f"Caller {pretty}", "Called the complainant" + (f" ({d_txt})" if d_txt else "")
        events.append(_ev(at=at, type="Call", actor=actor, action=action, phone=phone, direction=ctype or "incoming",
                          src=[{"f": f["ev_id"], "l": line_no}], source_kinds=["call_log"], kinds=["call"], conf=0.97))
    return events


def media_events(files: list[dict]) -> list[dict]:
    events = []
    for f in files:
        meta = f.get("meta") or {}
        if f.get("kind") != "media" or not meta.get("capture_time") or (f.get("dup") and not f["dup"]["canonical"]):
            continue
        place = (meta.get("geo") or "").split(" (")[0] or None
        device = meta.get("device")
        events.append(_ev(at=meta["capture_time"], type="Media", actor="Complainant",
                          action=f"Photograph taken ({f['name']}{', ' + device if device else ''})",
                          place=place if place and not place.startswith("Outside") else None,
                          src=[{"f": f["ev_id"], "l": 0}], source_kinds=["media"], kinds=["media"], conf=0.9))
    return events


# ---------------------------------------------------------------- narration


def _seg_date(text: str, year: int):
    m = DATE_A.search(text)
    if m:
        return int(m.group(1)), MONTHS[m.group(2).lower()]
    m = DATE_B.search(text)
    if m:
        return int(m.group(2)), MONTHS[m.group(1).lower()]
    return None


def _person(text: str, complainant: str) -> str | None:
    for pat in NAME_PATTERNS:
        m = pat.search(text)
        if m and m.group(1) not in NOT_NAMES and m.group(1).lower() not in complainant.lower():
            return m.group(1)
    try:
        from app.agents.nlp import person_names
        for name in person_names(text):
            if name not in NOT_NAMES and name.lower() not in complainant.lower():
                return name
    except Exception:  # noqa: BLE001 - spaCy is an optional helper here
        pass
    return None


def rule_facts(segments: list[dict], complainant: str) -> list[dict]:
    facts = []
    for s in segments:
        text = s.get("en") or ""
        kinds = [k for k, rx in KIND_RULES.items() if rx.search(text)]
        amounts = extract.extract_amounts(text)
        if "total" in kinds and not amounts:
            kinds.remove("total")
        if "payment" in kinds and not amounts:
            kinds.remove("payment")
        d = _seg_date(text, 0)
        facts.append({"segment_id": s["id"], "date": f"{d[0]} {list(MONTHS)[d[1] - 1]}" if d else None,
                      "amount": amounts[-1] if amounts else None, "kinds": kinds, "person": _person(text, complainant)})
    return facts


def llm_facts(segments: list[dict], complainant: str) -> tuple[list[dict], str]:
    lines = "\n".join(f"[{s['id']}] {s['en']}" for s in segments if s.get("en"))
    result, model = generate_json(NARRATION_PROMPT.format(segments=lines), NARRATION_SCHEMA)
    by_id = {s["id"]: s for s in segments}
    rules = {f["segment_id"]: f for f in rule_facts(segments, complainant)}
    facts = []
    for raw in result.get("facts", []):
        seg = by_id.get(raw.get("segment_id"))
        if not seg:
            continue  # no valid citation: dropped (§6.3)
        text = seg["en"]
        rule = rules[seg["id"]]
        amount = raw.get("amount")
        if amount is not None and amount not in extract.extract_amounts(text):
            amount = None  # not literally in the cited segment
        person = raw.get("person")
        if person and person not in text:
            person = None
        date = raw.get("date") if raw.get("date") and _seg_date(raw["date"], 0) else None
        kinds = [k for k in raw.get("kinds", []) if k in KIND_RULES]
        facts.append({"segment_id": seg["id"], "date": date or rule["date"],
                      "amount": amount if amount is not None else rule["amount"],
                      "kinds": sorted(set(kinds) | set(rule["kinds"])), "person": person or rule["person"]})
    if not facts:
        raise LlmError("LLM returned no cited facts")
    return facts, model


def link_narration(facts: list[dict], events: list[dict], segments: list[dict], year: int) -> tuple[list[dict], float | None, list[str]]:
    by_seg = {s["id"]: s for s in segments}
    stated_total, persons = None, []
    current_day = None
    new_events = []
    for fact in sorted(facts, key=lambda x: x["segment_id"]):
        d = _seg_date(fact["date"], year) if fact.get("date") else None
        if d:
            current_day = d
        day = current_day
        kinds, amount, person = set(fact["kinds"]), fact.get("amount"), fact.get("person")
        if person and person not in persons:
            persons.append(person)
        src = {"n": fact["segment_id"]}

        def on_day(e):
            dt = parse_iso(e["at"]).astimezone(IST)
            return day is None or (dt.day, dt.month) == day

        if "total" in kinds and amount:
            stated_total = amount
            continue
        linked = False
        if "call" in kinds and not person:
            for e in events:
                if e["type"] == "Call" and on_day(e) and e.get("direction", "incoming").startswith("in"):
                    e["src"].append(src)
                    linked = True
                    break
        if "link" in kinds or "otp" in kinds:
            for e in events:
                if e["type"] == "Message" and on_day(e) and (("link" in kinds and "link" in e["kinds"]) or ("otp" in kinds and "otp" in e["kinds"])):
                    e["src"].append(src)
                    linked = True
        if "debit" in kinds and not amount:
            for e in events:
                if e["type"] == "Transaction" and on_day(e) and "financial_record" in e["source_kinds"]:
                    e["src"].append(src)
                    linked = True
        if amount and ("payment" in kinds or "debit" in kinds):
            match = next((e for e in events if e["type"] == "Transaction" and e.get("amount") == amount and on_day(e)), None)
            if match:
                match["src"].append(src)
                linked = True
            else:
                at = _dt(day[0], day[1], year) if day else None
                who = f" to {person}" if person else ""
                action = (f"Called and asked for {money(amount)} more; the complainant says it was sent"
                          if person and "call" in kinds else f"Payment of {money(amount)}{who} stated in the narration")
                new_events.append(_ev(at=at, prec="day" if day else "approx", type="Transaction",
                                      actor=person or "Complainant", action=action, amount=amount, person=person,
                                      src=[src], source_kinds=["narration"], kinds=["payment"], conf=0.62))
                linked = True
        if not linked and person and "call" in kinds:
            at = _dt(day[0], day[1], year) if day else None
            new_events.append(_ev(at=at, prec="day" if day else "approx", type="Call", actor=person,
                                  action="Called the complainant (stated in the narration)", person=person,
                                  src=[src], source_kinds=["narration"], kinds=["call"], conf=0.6))
    for e in new_events:
        if e["at"] is None:
            e["at"] = max((x["at"] for x in events), default=now_iso())
    return new_events, stated_total, persons


def merge(events: list[dict]) -> list[dict]:
    """Same amount + same receiving account within 5 minutes => one event, all sources."""
    out: list[dict] = []
    for e in sorted(events, key=lambda x: x["at"]):
        twin = None
        if e["type"] == "Transaction" and e.get("amount") is not None:
            for o in out:
                if (o["type"] == "Transaction" and o.get("amount") == e["amount"]
                        and (o.get("to_account"), o.get("upi")) == (e.get("to_account"), e.get("upi"))
                        and o["src"] != e["src"] and not set(map(str, o["src"])) & set(map(str, e["src"]))
                        and o["source_kinds"] != e["source_kinds"]
                        and abs((parse_iso(o["at"]) - parse_iso(e["at"])).total_seconds()) <= 300):
                    twin = o
                    break
        if twin:
            twin["src"] += [s for s in e["src"] if s not in twin["src"]]
            twin["source_kinds"] = sorted(set(twin["source_kinds"]) | set(e["source_kinds"]))
        else:
            out.append(e)
    return out


def build(case_id: str, *, use_llm: bool = True) -> str:
    db = get_db()
    case = db.cases.find_one({"id": case_id}) or {}
    complainant = case.get("complainant", {}).get("name", "")
    files = list(db.files.find({"case_id": case_id, "status": "accepted"}).sort("uploaded_at", 1))
    events: list[dict] = []
    for f in files:
        if f.get("narration"):
            continue
        if f.get("kind") == "conversation" and f["ext"] == ".txt":
            events += parse_whatsapp(f, read_text(f), complainant.split(" ")[0] if complainant else "")
        elif f.get("kind") == "financial_record" and f["ext"] in (".txt", ".csv"):
            events += parse_bank_sms(f, read_text(f))
        elif f.get("kind") == "call_log":
            events += parse_call_log(f, read_text(f))
    events += media_events(files)
    events = merge(events)

    narration = db.narrations.find_one({"case_id": case_id}) or {}
    segments = narration.get("segments") or []
    year = max((parse_iso(e["at"]).year for e in events), default=parse_iso(case.get("created_at") or now_iso()).year)
    note_src = "no narration"
    facts: list[dict] = []
    if segments:
        cached = case.get("analysis", {}).get("narration_facts")
        if not use_llm and cached is not None:
            facts, note_src = cached, case["analysis"].get("narration_model", "rules")
        else:
            try:
                facts, model = llm_facts(segments, complainant)
                note_src = f"narration read by {model}"
            except LlmError:
                facts, note_src = rule_facts(segments, complainant), "narration read by rules (LLM unavailable)"
    new_events, stated_total, persons = link_narration(facts, events, segments, year)
    events = sorted(events + new_events, key=lambda x: x["at"])
    for i, e in enumerate(events, start=1):
        e["id"], e["case_id"] = f"E{i}", case_id
    db.timeline_events.delete_many({"case_id": case_id})
    if events:
        db.timeline_events.insert_many([dict(checked(TimelineEvent, e)) for e in events])
    db.cases.update_one({"id": case_id}, {"$set": {
        "analysis.stated_total": stated_total, "analysis.persons": persons,
        "analysis.narration_facts": facts, "analysis.narration_model": note_src}})
    custody.derived(case_id, "timeline", [{k: v for k, v in e.items() if k != "_id"} for e in events],
                    model=note_src, prompt=PROMPT_VERSION if segments else "none")
    sources = {s.get("f") or "N" for e in events for s in e["src"]}
    return f"{len(events)} events from {len(sources)} sources; {note_src}"


def events_for(case_id: str) -> list[dict]:
    return list(get_db().timeline_events.find({"case_id": case_id}, {"_id": 0}).sort("at", 1))


def day_after(iso: str, days: int) -> str:
    return (parse_iso(iso) + timedelta(days=days)).isoformat()
