"""Content Triage Agent — deterministic, owned by G.
docs/HACKATHON_PLAN.md §6.1.

Fixed output wording only: "No screening concern" | "Recommend forensic review"
| "Not screened" — always with the limitations line. Never use the words fake,
forged, authentic or synthetic anywhere in the UI-facing text.
"""
import os

import cv2
import imagehash
import numpy as np
from PIL import Image

from app.db import get_db

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
LIMITATION_TEXT = (
    "Frequency analysis catches crude tampering and misses sophisticated forgery."
)
DUPLICATE_HAMMING_THRESHOLD = 6
SCREENING_SCORE_THRESHOLD = 0.5


def classify_file(file_record: dict, sample_text: str = "") -> str:
    """Filename extension + a content sniff for .txt files (chat export vs bank SMS)."""
    name = (file_record.get("name") or "").lower()
    ext = os.path.splitext(name)[1]

    if ext in IMAGE_EXTENSIONS:
        return "media"
    if ext in {".wav", ".mp3", ".m4a"}:
        return "audio"
    if ext == ".csv":
        return "call_log"
    if ext == ".pdf":
        return "financial_record"
    if ext == ".txt":
        lowered = sample_text.lower()
        bank_markers = ("debited", "credited", "a/c", "upi ref", "avl bal", "imps", "neft")
        if any(marker in lowered for marker in bank_markers):
            return "financial_record"
        return "conversation"
    return "other"


def compute_phash(image_path: str) -> str | None:
    try:
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


def group_duplicates(files: list[dict]) -> dict[str, str]:
    """files: media file records, each with a precomputed `_phash`. Returns
    {file_id: canonical_file_id} for every file (including canonicals, which
    map to themselves) so callers can set is_duplicate_of = None for canonicals.
    """
    ordered = sorted(
        (f for f in files if f.get("_phash")),
        key=lambda f: f.get("uploaded_at") or "",
    )
    canonical_of: dict[str, str] = {}
    canonicals: list[tuple[str, imagehash.ImageHash]] = []

    for f in ordered:
        phash = imagehash.hex_to_hash(f["_phash"])
        match = None
        for canon_id, canon_hash in canonicals:
            if phash - canon_hash <= DUPLICATE_HAMMING_THRESHOLD:
                match = canon_id
                break
        if match:
            canonical_of[f["id"]] = match
        else:
            canonical_of[f["id"]] = f["id"]
            canonicals.append((f["id"], phash))
    return canonical_of


def _estimate_recompression_flag(image_path: str) -> float:
    """A coarse recompression signal: an irregular (non-monotonic) luminance
    quantization table can indicate the file was re-saved after editing.
    Returns 0.0 or 0.3 — a small additive signal, not a verdict on its own.
    """
    try:
        with Image.open(image_path) as img:
            quant = getattr(img, "quantization", None)
            if not quant:
                return 0.0
            values = list(quant.get(0, []))
            if values and values != sorted(values):
                return 0.3
    except Exception:
        pass
    return 0.0


def screen_for_manipulation(image_path: str) -> dict:
    """OpenCV DFT spectrum peak ratio + a recompression signal -> screening_score
    in [0, 1]. score >= 0.5 => "Recommend forensic review". Threshold calibrated
    on the demo bundle only — this is stated on stage, not hidden in the UI.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"screening_score": 0.0, "label": "Not screened", "limitation": LIMITATION_TEXT}

    spectrum = np.fft.fftshift(np.fft.fft2(img))
    magnitude = np.log(np.abs(spectrum) + 1)
    h, w = magnitude.shape
    cy, cx = h // 2, w // 2

    mask = np.ones_like(magnitude, dtype=bool)
    radius = max(4, min(h, w) // 40)
    mask[max(0, cy - radius):cy + radius, max(0, cx - radius):cx + radius] = False
    outer = magnitude[mask]
    if outer.size == 0:
        peak_ratio = 0.0
    else:
        peak_threshold = outer.mean() + 3 * outer.std()
        peak_ratio = float((outer > peak_threshold).sum()) / outer.size

    score = min(1.0, peak_ratio * 400 + _estimate_recompression_flag(image_path))
    label = "Recommend forensic review" if score >= SCREENING_SCORE_THRESHOLD else "No screening concern"
    return {"screening_score": round(score, 2), "label": label, "limitation": LIMITATION_TEXT}


def run(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('triage', case_id).
    Classifies every unclassified accepted file, groups image duplicates by
    pHash, and runs manipulation screening on each image.
    """
    db = get_db()
    files = list(db.files.find({"case_id": case_id, "status": "accepted", "kind": None}))

    classified: list[dict] = []
    for file_record in files:
        sample_text = ""
        ext = os.path.splitext((file_record.get("name") or "").lower())[1]
        file_path = os.path.join(_evidence_dir(), file_record["sha256"])
        if ext == ".txt" and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample_text = f.read(2048)

        kind = classify_file(file_record, sample_text)
        update: dict = {"kind": kind}

        if kind == "media" and ext in IMAGE_EXTENSIONS and os.path.exists(file_path):
            file_record["_phash"] = compute_phash(file_path)
            screening = screen_for_manipulation(file_path)
            update["screening"] = {
                "label": screening["label"],
                "score": screening["screening_score"],
                "limitation": screening["limitation"],
            }

        db.files.update_one({"id": file_record["id"]}, {"$set": update})
        file_record.update(update)
        classified.append(file_record)

    media_files = [f for f in classified if f.get("kind") == "media" and f.get("_phash")]
    if media_files:
        canonical_of = group_duplicates(media_files)
        for file_id, canonical_id in canonical_of.items():
            is_dup_of = canonical_id if canonical_id != file_id else None
            db.files.update_one({"id": file_id}, {"$set": {"is_duplicate_of": is_dup_of}})


def _evidence_dir() -> str:
    from app.config import settings

    return settings.evidence_dir
