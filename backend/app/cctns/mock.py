"""Offline stand-in for CCTNS, used by default. Reads sample FIRs from
cctns/samples/ and keeps pushed reports in memory, so the full flow can be
shown without any network access or credentials."""
import json
import os
import uuid

from app.cctns.base import CCTNSAdapter
from app.util import now_iso

SAMPLES = os.path.join(os.path.dirname(__file__), "samples")


class MockCCTNSAdapter(CCTNSAdapter):
    name = "mock"

    def __init__(self, samples_dir: str = SAMPLES):
        self.samples_dir = samples_dir
        self.pushed: dict[tuple[str, str], dict] = {}

    def _samples(self) -> list[dict]:
        out = []
        for fn in sorted(os.listdir(self.samples_dir)):
            if fn.endswith(".json"):
                with open(os.path.join(self.samples_dir, fn), encoding="utf-8") as f:
                    out.append(json.load(f))
        return out

    def fetch_fir(self, fir_no: str, ps_code: str) -> dict | None:
        key = (fir_no, ps_code)
        if key in self.pushed:
            return self.pushed[key]["report"]
        return next((s for s in self._samples() if s["iif_1_fir"]["fir_no"] == fir_no
                     and s["iif_1_fir"]["ps_code"] == ps_code), None)

    def push_case_report(self, report: dict) -> dict:
        fir = report["iif_1_fir"]
        ack = {"accepted": True, "ack_id": f"MOCK-{uuid.uuid4().hex[:10].upper()}", "received_at": now_iso(),
               "message": "Accepted by the mock CCTNS adapter (no data left this machine)."}
        self.pushed[(fir["fir_no"] or fir["trace_ref"], fir["ps_code"])] = {"report": report, "ack": ack}
        return ack

    def sync_status(self, fir_no: str, ps_code: str) -> dict:
        hit = self.fetch_fir(fir_no, ps_code)
        status = hit["iif_1_fir"].get("case_status") if hit else "Not found"
        return {"fir_no": fir_no, "ps_code": ps_code, "status": status, "updated_at": now_iso(), "source": self.name}
