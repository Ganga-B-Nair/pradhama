"""Content Triage Agent — deterministic. docs/HACKATHON_PLAN.md §6.1.

- Classify each file by magic bytes + filename into: financial record,
  conversation, media, call log, audio, other.
- pHash images; Hamming distance <= 6 is a duplicate group, earliest upload canonical.
- DFT spectrum peaks on the noise residual + a JPEG quality estimate give a
  screening score in [0, 1]; >= 0.5 means "Recommend forensic review".
  Threshold calibrated on the demo bundle only — say so on stage.

Fixed output wording: "No screening concern" | "Recommend forensic review" |
"Not screened", always shown with the limitations line. Never fake/forged/
authentic/synthetic.
"""
import os

import cv2
import imagehash
import numpy as np
from PIL import Image

from app.config import settings
from app.db import get_db

LIMITATION_TEXT = "Screening detects some crude edits and misses sophisticated ones. It is a referral aid, not a finding."
DUPLICATE_HAMMING_THRESHOLD = 6
SCREENING_THRESHOLD = 0.5
IMAGE_SNIFF = {"jpg", "png", "webp"}
AUDIO_SNIFF = {"wav", "mp3", "ogg", "m4a"}
BANK_MARKERS = ("debited", "credited", "a/c", "upi", "avl bal", "available balance", "imps", "neft", "rtgs")


def classify(f: dict, sample_text: str) -> str:
    name, sniff = f["name"].lower(), f.get("sniff")
    if sniff in IMAGE_SNIFF or sniff == "heic":
        return "media"
    if sniff in AUDIO_SNIFF:
        return "audio"
    if "call" in name and f["ext"] in (".csv", ".txt"):
        return "call_log"
    if sniff == "pdf":
        return "financial_record"
    if f["ext"] in (".txt", ".csv"):
        low = sample_text.lower()
        if any(m in low for m in BANK_MARKERS) or any(k in name for k in ("bank", "sms", "statement", "upi", "txn")):
            return "financial_record"
        if any(k in name for k in ("chat", "whatsapp", "telegram", "message")) or " - " in sample_text or "] " in sample_text:
            return "conversation"
    return "other"


def detect_language(text: str) -> str:
    if not text:
        return "—"
    ml = sum(1 for ch in text if "ഀ" <= ch <= "ൿ")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if ml and latin > ml * 0.3:
        return "Malayalam + English"
    return "Malayalam" if ml else "English"


def jpeg_quality(img: Image.Image) -> int | None:
    """Estimate JPEG quality from the luminance quantisation table (libjpeg scaling)."""
    quant = getattr(img, "quantization", None)
    if not quant or 0 not in quant:
        return None
    q0 = list(quant[0])
    std = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
           14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
           49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
    scale = float(np.mean([q / s for q, s in zip(sorted(q0), sorted(std))])) * 100
    return int(max(1, min(100, (200 - scale) / 2 if scale <= 100 else 5000 / scale)))


def periodic_peak_score(gray: np.ndarray) -> float:
    """Resampling and splicing leave periodic correlations in the noise residual,
    which show up as isolated strong peaks in its Fourier spectrum."""
    h, w = gray.shape
    if min(h, w) < 64:
        return 0.0
    g = gray.astype(np.float32)
    residual = g - cv2.GaussianBlur(g, (3, 3), 0)
    win = np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)
    mag = np.abs(np.fft.fftshift(np.fft.fft2(residual * win)))
    mag = np.log1p(mag)
    local = cv2.medianBlur(mag.astype(np.float32), 5)
    excess = mag - local
    cy, cx = h // 2, w // 2
    r = max(4, min(h, w) // 32)
    excess[cy - r:cy + r, cx - r:cx + r] = 0
    excess[cy - 1:cy + 2, :] = 0
    excess[:, cx - 1:cx + 2] = 0
    thr = excess.mean() + 6 * excess.std()
    peaks = int((excess > thr).sum())
    return float(peaks) / (h * w) * 1e4


def screen_image(path: str) -> dict:
    try:
        with Image.open(path) as img:
            quality = jpeg_quality(img)
            img.load()
            gray = np.array(img.convert("L"))
    except Exception:
        return {"status": "not", "score": None, "reasons": ["The image could not be decoded for screening"]}

    peak = periodic_peak_score(gray)
    reasons = []
    score = min(0.45, peak * 0.15)
    if peak >= 2.0:
        score += 0.35
        reasons.append("Periodic peaks in the frequency spectrum, consistent with resampling or pasted regions")
    if quality is not None and quality < 60:
        score += 0.15
        reasons.append(f"Low JPEG quality estimate ({quality}), consistent with repeated re-saving")
    score = round(min(1.0, score), 2)
    if not reasons:
        reasons.append("No frequency-domain or compression irregularity above threshold")
    return {"status": "review" if score >= SCREENING_THRESHOLD else "none", "score": score, "reasons": reasons,
            "jpeg_quality": quality}


def _phash(path: str) -> str | None:
    try:
        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


def evidence_path(f: dict) -> str:
    return os.path.join(settings.evidence_dir, f["sha256"])


def read_text(f: dict, limit: int | None = None) -> str:
    try:
        with open(evidence_path(f), "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read(limit) if limit else fh.read()
    except OSError:
        return ""


def run(case_id: str) -> str:
    db = get_db()
    files = list(db.files.find({"case_id": case_id, "status": "accepted"}).sort("uploaded_at", 1))
    for f in files:
        update: dict = {}
        text = read_text(f, 4096) if f["ext"] in (".txt", ".csv") else ""
        if not f.get("kind"):
            update["kind"] = "audio" if f.get("narration") else classify(f, text)
        kind = update.get("kind", f.get("kind"))
        if kind in ("conversation", "financial_record", "call_log", "other") and f["ext"] in (".txt", ".csv"):
            update["lang"] = detect_language(read_text(f))
        elif kind == "audio":
            update["lang"] = "Malayalam" if f.get("narration") else "—"
        if f.get("screen") is None:
            if f.get("sniff") in IMAGE_SNIFF:
                update["screen"] = screen_image(evidence_path(f))
                update["phash"] = _phash(evidence_path(f))
            elif f.get("sniff") == "heic":
                update["screen"] = {"status": "not", "score": None, "reasons": ["HEIC images are not screened in v1"]}
            elif kind == "audio":
                update["screen"] = {"status": "not", "score": None, "reasons": ["Audio is not screened in v1"]}
            else:
                update["screen"] = {"status": "na", "score": None, "reasons": []}
        if update:
            db.files.update_one({"id": f["id"]}, {"$set": update})
            f.update(update)

    # Near-duplicate grouping across all images in the case, earliest upload canonical.
    images = [f for f in files if f.get("phash")]
    groups: list[list[dict]] = []
    for f in images:
        h = imagehash.hex_to_hash(f["phash"])
        for g in groups:
            if h - imagehash.hex_to_hash(g[0]["phash"]) <= DUPLICATE_HAMMING_THRESHOLD:
                g.append(f)
                break
        else:
            groups.append([f])
    n = 0
    db.files.update_many({"case_id": case_id}, {"$set": {"dup": None}})
    for g in groups:
        if len(g) < 2:
            continue
        n += 1
        for i, f in enumerate(g):
            db.files.update_one({"id": f["id"]}, {"$set": {"dup": {
                "group": f"D{n}", "canonical": i == 0, "idx": i + 1, "of": len(g), "canonical_id": g[0]["ev_id"]}}})

    dups = sum(len(g) - 1 for g in groups if len(g) > 1)
    review = db.files.count_documents({"case_id": case_id, "status": "accepted", "screen.status": "review"})
    return f"{len(files)} files classified; {dups} duplicates grouped; {review} recommended for forensic review"
