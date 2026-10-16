"""BNS/IT Act suggestion adapter — V builds the live path, G owns the fixture.
docs/HACKATHON_PLAN.md §6.5.

Default mode is "fixture": 4 hardcoded entries for the demo story (BNS 318(4),
BNS 319(2), IT Act 66C, IT Act 66D), matched to events by local keyword rules.
"live" mode calls InsightLaw if BNS_MODE=live; 5s timeout; any error falls
back to the fixture and the UI shows an "offline" note.

InsightLaw's response shape is UNKNOWN as of this scaffold — the only
confirmed contract is:
    GET https://insightlaw.in?q=<term>  ->  JSON (no visible auth key)
Inspect the real response at H1 before writing _call_insightlaw's parsing.
Every suggestion returned here must still show "Advisory: SHO decides" in
the UI, and section numbers are "Advisory — sections to be verified" until a
legal mentor checks them (Appendix B of docs/README.md).
"""
import requests

from app.config import settings

FIXTURE_SUGGESTIONS = [
    # TODO(G): fill in {section, title, ingredients[]}; matched_event_ids filled
    # at suggest() time from local keyword rules (OTP shared -> IT Act 66C;
    # impersonating a bank -> BNS 319(2) + IT Act 66D; payment induced by
    # deception -> BNS 318(4)).
]


def _call_insightlaw(query: str) -> list[dict] | None:
    try:
        resp = requests.get(
            settings.insightlaw_base_url,
            params={"q": query},
            timeout=settings.insightlaw_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        # TODO(V): map InsightLaw's actual response shape (inspect at H1) into
        # [{"section": str, "title": str, "ingredients": [...]}].
        raise NotImplementedError("InsightLaw response shape not yet mapped")
    except (requests.RequestException, ValueError, NotImplementedError):
        return None


def suggest(facts: list[str]) -> list[dict]:
    """facts: short strings extracted from the case's events/draft (e.g. 'OTP shared',
    'payment induced by deception'). Returns [{section, title, ingredients, matched_event_ids}]."""
    if settings.bns_mode == "live":
        for fact in facts:
            result = _call_insightlaw(fact)
            if result is not None:
                return result
        # fall through to fixture on any failure — never leave the officer with nothing
    raise NotImplementedError  # TODO(G): keyword-match facts against FIXTURE_SUGGESTIONS
