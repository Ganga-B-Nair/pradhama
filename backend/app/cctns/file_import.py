"""File exchange with CCTNS: FIRs exported from CCTNS as JSON are dropped in
an import folder, and TRACE's reports are written to an outbox folder for an
operator to upload. Works where a station has CCTNS access but no API."""
import json
import os
import re

from app.cctns.base import CCTNSAdapter, CCTNSError
from app.util import now_iso


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s or "")


class FileImportAdapter(CCTNSAdapter):
    name = "file"

    def __init__(self, import_dir: str, outbox_dir: str):
        self.import_dir, self.outbox_dir = import_dir, outbox_dir

    def _imported(self) -> list[dict]:
        if not os.path.isdir(self.import_dir):
            return []
        out = []
        for fn in sorted(os.listdir(self.import_dir)):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(self.import_dir, fn), encoding="utf-8") as f:
                        out.append(json.load(f))
                except (OSError, ValueError) as exc:
                    raise CCTNSError(f"Could not read imported FIR {fn}: {exc}") from exc
        return out

    def fetch_fir(self, fir_no: str, ps_code: str) -> dict | None:
        return next((d for d in self._imported() if d.get("iif_1_fir", {}).get("fir_no") == fir_no
                     and d["iif_1_fir"].get("ps_code") == ps_code), None)

    def push_case_report(self, report: dict) -> dict:
        fir = report["iif_1_fir"]
        os.makedirs(self.outbox_dir, exist_ok=True)
        fn = f"{_safe(fir['ps_code'])}_{_safe(fir['fir_no'] or fir['trace_ref'])}_{now_iso()[:19].replace(':', '')}.json"
        with open(os.path.join(self.outbox_dir, fn), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return {"accepted": True, "ack_id": fn, "received_at": now_iso(),
                "message": f"Written to the CCTNS outbox folder as {fn} for upload by the station operator."}

    def sync_status(self, fir_no: str, ps_code: str) -> dict:
        hit = self.fetch_fir(fir_no, ps_code)
        return {"fir_no": fir_no, "ps_code": ps_code, "status": hit["iif_1_fir"].get("case_status") if hit else "Not found",
                "updated_at": now_iso(), "source": self.name}
