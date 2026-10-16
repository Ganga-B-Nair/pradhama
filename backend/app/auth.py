"""Two hard-coded demo accounts: Officer and SHO (docs/HACKATHON_PLAN.md §1).
"The officer files; the SHO approves": approval, BNS decisions, referral
confirmation, export and the audit trail are SHO-only.

Sessions live in Mongo and end after 15 minutes without activity.
"""
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException

from app.db import get_db

SESSION_COOKIE = "trace_session"
IDLE_LIMIT = timedelta(minutes=15)

USERS = {
    "officer": {"username": "officer", "password": "officer123", "name": "Divya R", "badge": "HC 2214", "role": "officer"},
    "sho": {"username": "sho", "password": "sho123", "name": "Thomas Varghese", "badge": "Inspector 0412", "role": "sho"},
}
ROLE_LABEL = {"officer": "Officer", "sho": "SHO"}

_failures: dict[str, dict] = {}


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("username", "name", "badge", "role")} | {"role_label": ROLE_LABEL[u["role"]]}


def check_login(username: str, password: str) -> dict:
    now = datetime.now(timezone.utc)
    state = _failures.setdefault(username, {"count": 0, "until": None})
    if state["until"] and state["until"] > now:
        mins = int((state["until"] - now).total_seconds() // 60) + 1
        raise HTTPException(423, f"This account is locked for {mins} more minute(s) after 5 failed attempts.")
    user = USERS.get(username)
    if not user or user["password"] != password:
        state["count"] += 1
        if state["count"] >= 5:
            state.update(count=0, until=now + timedelta(minutes=15))
            raise HTTPException(423, "This account is now locked for 15 minutes after 5 failed attempts.")
        raise HTTPException(401, "Sign-in failed. Check your details and try again.")
    state.update(count=0, until=None)
    return user


def create_session(user: dict) -> str:
    sid = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    get_db().sessions.insert_one({"sid": sid, "username": user["username"], "created": now, "last_seen": now})
    return sid


def end_session(sid: str | None) -> None:
    if sid:
        get_db().sessions.delete_one({"sid": sid})


def current_user(trace_session: str | None = Cookie(default=None)) -> dict:
    if not trace_session:
        raise HTTPException(401, "Not signed in")
    db = get_db()
    s = db.sessions.find_one({"sid": trace_session})
    if not s:
        raise HTTPException(401, "Not signed in")
    now = datetime.now(timezone.utc)
    last = s["last_seen"] if s["last_seen"].tzinfo else s["last_seen"].replace(tzinfo=timezone.utc)
    if now - last > IDLE_LIMIT:
        db.sessions.delete_one({"sid": trace_session})
        raise HTTPException(401, "Session ended after 15 minutes of inactivity.")
    db.sessions.update_one({"sid": trace_session}, {"$set": {"last_seen": now}})
    return USERS[s["username"]]


def require_sho(user: dict) -> None:
    if user["role"] != "sho":
        raise HTTPException(403, "Only the SHO can do this.")
