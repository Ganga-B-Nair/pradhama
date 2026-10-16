"""Shared regex entity extraction — used by timeline parsing and Gap Hunter's
entity normalization so phone/UPI/IFSC/amount patterns can't drift between
the two call sites.
"""
import re

PHONE_RE = re.compile(r"(?:\+?91[\-\s]?)?([6-9]\d{9})\b")
UPI_RE = re.compile(r"\b[\w.\-]{2,256}@[a-zA-Z]{2,64}\b")
IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
ACCOUNT_RE = re.compile(r"\b(?:A/?c|account)[^\d]{0,15}([Xx*]{2,}\d{2,6}|\d{6,18})\b", re.IGNORECASE)
AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|₹)\s?([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) > 10:
        digits = digits[-10:]
    return f"+91{digits}"


def extract_phones(text: str) -> list[str]:
    return sorted({normalize_phone(m.group(1)) for m in PHONE_RE.finditer(text)})


def extract_upi_ids(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in UPI_RE.finditer(text)})


def extract_ifsc_codes(text: str) -> list[str]:
    return sorted({m.group(0).upper() for m in IFSC_RE.finditer(text)})


def extract_accounts(text: str) -> list[str]:
    return sorted({m.group(1).upper() for m in ACCOUNT_RE.finditer(text)})


def extract_amount(text: str) -> float | None:
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def extract_amounts(text: str) -> list[float]:
    return [float(m.group(1).replace(",", "")) for m in AMOUNT_RE.finditer(text)]
