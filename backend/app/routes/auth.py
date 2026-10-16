"""Two hardcoded demo accounts: Officer and SHO. No user management UI (out of
scope for the hackathon, see docs/HACKATHON_PLAN.md §1)."""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

router = APIRouter()

DEMO_ACCOUNTS = {
    "officer": {"password": "officer123", "role": "officer"},
    "sho": {"password": "sho123", "role": "sho"},
}


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/login")
def login(body: LoginRequest, response: Response):
    account = DEMO_ACCOUNTS.get(body.username)
    if not account or account["password"] != body.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    response.set_cookie("trace_user", body.username, httponly=True)
    response.set_cookie("trace_role", account["role"], httponly=True)
    return {"user": body.username, "role": account["role"]}
