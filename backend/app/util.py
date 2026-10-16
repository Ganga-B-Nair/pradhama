"""Small shared helpers: time, money formatting, Mongo document cleanup."""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def money(amount: float | int | None) -> str:
    """Indian digit grouping: 160000 -> ₹1,60,000."""
    if amount is None:
        return ""
    n = int(round(amount))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def fmt_ist(value: str | None, with_time: bool = True) -> str:
    dt = parse_iso(value)
    if not dt:
        return ""
    return dt.astimezone(IST).strftime("%d %b %Y, %H:%M" if with_time else "%d %b %Y")


def fmt_date(value: str | None) -> str:
    dt = parse_iso(value)
    return dt.astimezone(IST).strftime("%d-%m-%Y") if dt else ""


def fmt_time(value: str | None) -> str:
    dt = parse_iso(value)
    return dt.astimezone(IST).strftime("%H:%M") if dt else ""


def clean(doc: dict | None) -> dict | None:
    if doc is not None:
        doc.pop("_id", None)
    return doc


def clean_all(docs) -> list[dict]:
    return [clean(d) for d in docs]
