from fastapi import APIRouter, Cookie, Depends, Response
from pydantic import BaseModel

from app.auth import SESSION_COOKIE, USERS, check_login, create_session, current_user, end_session, public_user
from app.config import settings

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/api/station")
def station():
    return {"code": settings.station_code, "name": settings.station_name,
            "demo_accounts": [public_user(u) for u in USERS.values()]}


@router.post("/api/login")
def login(body: LoginRequest, response: Response):
    user = check_login(body.username.strip(), body.password)
    response.set_cookie(SESSION_COOKIE, create_session(user), httponly=True, samesite="lax")
    return public_user(user)


@router.post("/api/logout")
def logout(response: Response, trace_session: str | None = Cookie(default=None)):
    end_session(trace_session)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/api/me")
def me(user: dict = Depends(current_user)):
    return public_user(user)
