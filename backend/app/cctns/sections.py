"""Legal sections under the codes in force from 1 July 2024 (BNS, BNSS, BSA),
with the legacy IPC / CrPC / IEA section each one replaced.

Sections are stored and reported under the new codes. A legacy reference (for
example in an older complaint or a CCTNS record from before July 2024) is
mapped forward; the legacy number is kept alongside for reference. IT Act
sections are unchanged by the 2023 codes and pass through as they are.

The table covers the sections TRACE suggests or cites for cyber fraud. Check
it against the official correspondence tables before relying on it.
"""
import re

# (new code, section, title, legacy code, legacy section)
TABLE = [
    ("BNS", "318(2)", "Cheating", "IPC", "417"),
    ("BNS", "318(4)", "Cheating and dishonestly inducing delivery of property", "IPC", "420"),
    ("BNS", "319(2)", "Cheating by personation", "IPC", "419"),
    ("BNS", "316(2)", "Criminal breach of trust", "IPC", "406"),
    ("BNS", "336(3)", "Forgery for the purpose of cheating", "IPC", "468"),
    ("BNS", "340(2)", "Using as genuine a forged document or electronic record", "IPC", "471"),
    ("BNS", "308(2)", "Extortion", "IPC", "384"),
    ("BNS", "351(2)", "Criminal intimidation", "IPC", "506"),
    ("BNS", "61(2)", "Criminal conspiracy", "IPC", "120B"),
    ("BNS", "3(5)", "Acts done by several persons in furtherance of common intention", "IPC", "34"),
    ("BNS", "111", "Organised crime", None, None),
    ("BNSS", "173", "Information in cognizable cases (FIR)", "CrPC", "154"),
    ("BNSS", "176", "Procedure for investigation", "CrPC", "157"),
    ("BNSS", "180", "Examination of witnesses by police", "CrPC", "161"),
    ("BNSS", "94", "Summons to produce document or other thing", "CrPC", "91"),
    ("BNSS", "106", "Power of police officer to seize certain property", "CrPC", "102"),
    ("BNSS", "185", "Search by police officer", "CrPC", "165"),
    ("BNSS", "193", "Report of police officer on completion of investigation", "CrPC", "173"),
    ("BSA", "57", "Primary evidence", "IEA", "62"),
    ("BSA", "62", "Special provisions as to evidence relating to electronic record", "IEA", "65A"),
    ("BSA", "63", "Admissibility of electronic records (certificate)", "IEA", "65B"),
]
ACTS = {"BNS": "BNS", "BNSS": "BNSS", "BSA": "BSA", "IPC": "IPC", "CRPC": "CrPC", "IEA": "IEA", "IT ACT": "IT Act"}
CURRENT = {"BNS", "BNSS", "BSA"}
LEGACY = {"IPC": "BNS", "CrPC": "BNSS", "IEA": "BSA"}  # legacy code -> the code that replaced it
UNCHANGED = {"IT Act"}

_BY_NEW = {(row[0], row[1]): row for row in TABLE}
_BY_OLD = {(row[3], row[4]): row for row in TABLE if row[3]}
REF = re.compile(r"^\s*(BNSS|BNS|BSA|IPC|CrPC|IEA|IT\s*Act)\b[\s,.]*(?:s(?:ec(?:tion)?)?\.?\s*)?(\d+[a-z]?(?:\([0-9a-z]+\))*)",
                 re.IGNORECASE)


def parse(ref: str) -> tuple[str, str] | None:
    """("BNS", "318(4)") from "BNS s.318(4)", "bns 318(4)", "IPC Sec. 120b" -> ("IPC", "120B") and similar."""
    m = REF.match(ref or "")
    if not m:
        return None
    act = ACTS[re.sub(r"\s+", " ", m.group(1)).upper()]
    sec = re.sub(r"^\d+[a-z]?", lambda x: x.group(0).upper(), m.group(2), flags=re.IGNORECASE)
    return act, sec


def to_current(ref: str) -> dict:
    """A section reference as stored and reported: the current code first, the legacy one kept for reference.

    Returns {"act", "section", "code", "title", "legacy", "raw", "mapped"}. "mapped" is False when the
    reference is not in the table; it is then passed through for the officer to check, never guessed."""
    p = parse(ref)
    if not p:
        return {"act": None, "section": None, "code": ref, "title": None, "legacy": None, "raw": ref, "mapped": False}
    act, sec = p
    if act in UNCHANGED:
        return {"act": act, "section": sec, "code": f"{act} {sec}", "title": None, "legacy": None, "raw": ref, "mapped": True}
    row = _BY_NEW.get((act, sec)) if act in CURRENT else _BY_OLD.get((act, sec))
    if not row:
        if act in CURRENT:
            return {"act": act, "section": sec, "code": f"{act} {sec}", "title": None, "legacy": None, "raw": ref, "mapped": False}
        return {"act": LEGACY[act], "section": None, "code": None, "title": None, "legacy": f"{act} {sec}", "raw": ref, "mapped": False}
    a, s, t, la, ls = row
    return {"act": a, "section": s, "code": f"{a} {s}", "title": t, "legacy": f"{la} {ls}" if la else None, "raw": ref, "mapped": True}
