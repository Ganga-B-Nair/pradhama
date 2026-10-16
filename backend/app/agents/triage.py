"""Content Triage Agent — deterministic, owned by G.
docs/HACKATHON_PLAN.md §6.1.

Fixed output wording only: "No screening concern" | "Recommend forensic review"
| "Not screened" — always with the limitations line. Never use the words fake,
forged, authentic or synthetic anywhere in the UI-facing text.
"""


def classify_file(file_record: dict) -> str:
    """Magic bytes + filename -> financial_record | conversation | media | call_log | audio | other."""
    raise NotImplementedError


def compute_phash(image_path: str) -> str:
    """imagehash.phash; group duplicates where Hamming distance <= 6."""
    raise NotImplementedError


def screen_for_manipulation(image_path: str) -> dict:
    """OpenCV DFT spectrum + JPEG quality estimate -> {screening_score: 0..1, label: str}.
    label is one of the three fixed strings above. score >= 0.5 => "Recommend forensic review".
    Threshold is calibrated on the demo bundle only — say so on stage.
    """
    raise NotImplementedError


def run(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('triage', case_id)."""
    raise NotImplementedError
