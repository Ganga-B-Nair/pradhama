"""The one interface TRACE uses to reach a case system such as CCTNS.

Agents and routes never talk to CCTNS directly: they build a report (see
iif.py) and hand it to whichever adapter is configured. Swapping the mock for
a live connection is a configuration change, not a code change.
"""
from abc import ABC, abstractmethod


class CCTNSError(Exception):
    """A case-system call failed in a way the officer should be told about."""


class CCTNSAdapter(ABC):
    name: str = "base"
    live: bool = False  # True only for an adapter that talks to the real system

    @abstractmethod
    def fetch_fir(self, fir_no: str, ps_code: str) -> dict | None:
        """The FIR as the case system holds it (IIF-style dict), or None if unknown."""

    @abstractmethod
    def push_case_report(self, report: dict) -> dict:
        """Send an IIF-style case report. Returns an acknowledgement:
        {"accepted": bool, "ack_id": str, "received_at": iso, "message": str}."""

    @abstractmethod
    def sync_status(self, fir_no: str, ps_code: str) -> dict:
        """Current status of the FIR in the case system:
        {"fir_no", "ps_code", "status", "updated_at", "source"}."""

    def describe(self) -> dict:
        return {"adapter": self.name, "live": self.live}
