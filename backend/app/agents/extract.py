"""Shared regex entity extraction — used by timeline parsing and Gap Hunter's
entity normalisation so phone/UPI/IFSC/amount patterns can't drift between
the two call sites (docs/HACKATHON_PLAN.md §3: spaCy + regex normalisers).
"""
import re

PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\-\s]?)?([6-9]\d{4}[\s\-]?\d{5})(?!\d)")
UPI_RE = re.compile(r"\b[\w.\-]{2,256}@[a-zA-Z]{2,64}\b")
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
ACCOUNT_RE = re.compile(r"\b(?:A/?c|account)(?:\s*no\.?)?\s*([Xx*]{2,}\d{2,6}|\d{6,18})\b", re.IGNORECASE)
TO_ACCOUNT_RE = re.compile(r"\bto\s+(?:A/?c|account)\s*([Xx*]{2,}\d{2,6}|\d{6,18})\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|₹)\s?([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
AMOUNT_WORDS_RE = re.compile(r"\b(\d{1,3}(?:,\d{2,3})+|\d{3,9})(?:\.\d{1,2})?\s*(?:rupees|rs\b|inr\b)", re.IGNORECASE)
URL_RE = re.compile(r"\b(?:hxxps?|https?)://\S+|\b[\w\-]+\[\.\][\w\-.\[\]/]+", re.IGNORECASE)
OTP_RE = re.compile(r"^\s*\d{4,8}\s*$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) > 10:
        digits = digits[-10:]
    return f"+91{digits}"


def pretty_phone(e164: str) -> str:
    d = e164[-10:]
    return f"+91 {d[:5]} {d[5:]}"


def extract_phones(text: str) -> list[str]:
    return sorted({normalize_phone(m.group(1)) for m in PHONE_RE.finditer(text or "")})


def extract_upi_ids(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in UPI_RE.finditer(text or "")})


def extract_ifsc_codes(text: str) -> list[str]:
    return sorted({m.group(0).upper() for m in IFSC_RE.finditer(text or "")})


def extract_accounts(text: str) -> list[str]:
    return sorted({m.group(1).upper() for m in ACCOUNT_RE.finditer(text or "")})


def extract_to_account(text: str) -> str | None:
    m = TO_ACCOUNT_RE.search(text or "")
    return m.group(1).upper() if m else None


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_amount(text: str) -> float | None:
    amounts = extract_amounts(text)
    return amounts[0] if amounts else None


def extract_amounts(text: str) -> list[float]:
    text = text or ""
    found = [(m.start(), _num(m.group(1))) for m in AMOUNT_RE.finditer(text)]
    taken = {pos for pos, _ in found}
    for m in AMOUNT_WORDS_RE.finditer(text):
        if not any(abs(m.start() - p) < 6 for p in taken):
            found.append((m.start(), _num(m.group(1))))
    return [v for _, v in sorted(found) if v > 0]


def extract_urls(text: str) -> list[str]:
    return [m.group(0) for m in URL_RE.finditer(text or "")]
