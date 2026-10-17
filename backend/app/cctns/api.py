"""Live CCTNS connection: a stub until the interface is provided.

The CCTNS API is not public. Its endpoints, authentication and payload codes
come from NCRB / the state CCTNS team (Kerala Police SCRB), so nothing here
guesses them. Each method says what is needed and raises NotImplementedError.
Selecting this adapter (CCTNS_ADAPTER=api) therefore fails loudly instead of
pretending to send anything.
"""
from app.cctns.base import CCTNSAdapter


class CCTNSApiAdapter(CCTNSAdapter):
    name = "api"
    live = True

    def __init__(self, base_url: str = "", client_id: str = "", client_secret: str = "", timeout: float = 15):
        # TODO: real values from the state CCTNS team; kept in the git-ignored .env, never in code.
        self.base_url, self.client_id, self.client_secret, self.timeout = base_url, client_id, client_secret, timeout

    def _token(self) -> str:
        # TODO: authentication scheme (token service, certificate or VPN-bound session) per the CCTNS
        #       integration document. Cache the token until expiry.
        raise NotImplementedError("CCTNS authentication is not configured: needs the CCTNS integration document.")

    def fetch_fir(self, fir_no: str, ps_code: str) -> dict | None:
        # TODO: GET the FIR by (state, district, PS code, year, FIR number); map the response's codes to the
        #       IIF-style dict with contracts/cctns_iif_mapping.json (reverse direction).
        raise NotImplementedError("CCTNS fetch_fir: endpoint and response format not yet provided by NCRB / SCRB.")

    def push_case_report(self, report: dict) -> dict:
        # TODO: map report fields to CCTNS master-data codes (act/section codes, police station and district
        #       codes, property type codes), POST them, and return the CCTNS acknowledgement number.
        #       Push only what the integration agreement allows (e.g. a draft for the IO), never a registered FIR.
        raise NotImplementedError("CCTNS push_case_report: endpoint, payload codes and permissions not yet provided.")

    def sync_status(self, fir_no: str, ps_code: str) -> dict:
        # TODO: poll (or receive a callback for) the FIR status and map CCTNS status codes to text.
        raise NotImplementedError("CCTNS sync_status: status endpoint not yet provided by NCRB / SCRB.")
