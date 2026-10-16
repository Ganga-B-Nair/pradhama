"""Date and time reading shared by every parser. Indian sources write the day
first (01/10/26 is 1 October); a file is read month-first only when its own
dates prove it (a second field above 12 and no first field above 12).

All results are IST ISO strings."""
import re
from datetime import datetime

from app.util import IST

MONTHS = {m[:3]: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"], start=1)}
# Full month spellings only, so words like "maybe" or "marks" are never months.
MON = (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
       r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])")
NUM_DATE = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})(?!\d)")
ISO_DATE = re.compile(r"(?<!\d)(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})(?!\d)")
D_MON_Y = re.compile(rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?[\s\-/.]*(?:of\s+)?{MON}[\s\-/.,']*(\d{{4}}|\d{{2}})?(?!\d)", re.IGNORECASE)
MON_D_Y = re.compile(rf"(?<![a-z]){MON}[\s\-/.]*(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?(?!\d)", re.IGNORECASE)
# Colon times always; dotted times ("2.22 pm") only with am/pm, so "Rs 1.50" is never a time.
TIME = re.compile(r"(?<![\d.])(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]\.?\s?m(?![a-z])\.?)?(?!\d)", re.IGNORECASE)
TIME_DOT = re.compile(r"(?<![\d,.])(\d{1,2})\.(\d{2})\s*([ap]\.?\s?m(?![a-z])\.?)", re.IGNORECASE)
# Direction marks and BOMs that iPhone and Android exports put around dates and names.
INVISIBLE = re.compile("[‎‏‪-‮⁦-⁩﻿]")
ODD_SPACES = re.compile("[   ]")


def clean(s: str) -> str:
    return ODD_SPACES.sub(" ", INVISIBLE.sub("", s))


def year4(y: int | None, default: int) -> int:
    if y is None:
        return default
    return y + 2000 if y < 100 else y


def order_for(samples: list[tuple[int, int]]) -> str:
    """'dmy' unless the file's own dates show month-first."""
    first_big = any(a > 12 for a, _ in samples)
    second_big = any(b > 12 for _, b in samples)
    return "mdy" if second_big and not first_big else "dmy"


def to_24h(h: int, ampm: str | None) -> int:
    if not ampm:
        return h
    pm = ampm.lower().startswith("p")
    if h == 12:
        return 12 if pm else 0
    return h + 12 if pm else h


def find_time(text: str):
    """(hour, minute) of the first plausible clock time, or None."""
    found = [(m.start(), int(m.group(1)), int(m.group(2)), m.group(4)) for m in TIME.finditer(text)]
    found += [(m.start(), int(m.group(1)), int(m.group(2)), m.group(3)) for m in TIME_DOT.finditer(text)]
    for _pos, h, mi, ampm in sorted(found):
        if ampm and not 1 <= h <= 12:
            continue
        h = to_24h(h, ampm)
        if 0 <= h < 24 and 0 <= mi < 60:
            return h, mi
    return None


def find_date(text: str, default_year: int, order: str = "dmy"):
    """(year, month, day) of the first date in the text, or None."""
    cands = []
    for m in ISO_DATE.finditer(text):
        cands.append((m.start(), int(m.group(1)), int(m.group(2)), int(m.group(3))))
    for m in NUM_DATE.finditer(text):
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d, mo = (b, a) if order == "mdy" else (a, b)
        cands.append((m.start(), year4(y, default_year), mo, d))
    for m in D_MON_Y.finditer(text):
        cands.append((m.start(), year4(int(m.group(3)) if m.group(3) else None, default_year),
                      MONTHS[m.group(2).lower()[:3]], int(m.group(1))))
    for m in MON_D_Y.finditer(text):
        cands.append((m.start(), year4(int(m.group(3)) if m.group(3) else None, default_year),
                      MONTHS[m.group(1).lower()[:3]], int(m.group(2))))
    for _pos, y, mo, d in sorted(cands):
        try:
            datetime(y, mo, d)
            return y, mo, d
        except ValueError:
            continue
    return None


def iso(y: int, mo: int, d: int, hh: int = 12, mm: int = 0) -> str:
    return datetime(y, mo, d, hh, mm, tzinfo=IST).isoformat()


def stamp(text: str, default_year: int, order: str = "dmy"):
    """(iso, precision) from free text: 'exact' with a time, 'day' without, or None."""
    d = find_date(text, default_year, order)
    if not d:
        return None
    t = find_time(text)
    return (iso(*d, *t), "exact") if t else (iso(*d), "day")
