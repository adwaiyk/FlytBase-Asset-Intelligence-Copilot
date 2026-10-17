"""HTTP API for the Next.js app.

Security model: the browser never sees the session token. The Next.js server
(BFF) keeps it in an httpOnly, SameSite=Strict cookie and forwards it here as a
Bearer token. Logins are rate-limited per user and per IP with a temporary
lockout, passwords are PBKDF2-SHA256 (200k rounds, per-user salt), sessions
expire and are revoked server-side on sign-out or password change.

Run: uvicorn copilot.server:app --port 8000
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import config
from .agent import Agent
from .data import load
from .engine import Engine, fmt_date
from .store import Store

app = FastAPI(title="WellWise API", docs_url=None, redoc_url=None, openapi_url=None)
_boot_lock = threading.Lock()
_state: dict = {}

MAX_FAILS, WINDOW_MIN, LOCK_MIN = 5, 15, 15


def state():
    with _boot_lock:
        if not _state:
            data = load()
            store = Store()
            store.seed_users(data.users, config.DEFAULT_PASSWORD)
            eng = Engine(data, store)
            _state.update(data=data, store=store, eng=eng, agent=Agent(eng))
    return _state


@app.on_event("startup")
def _warm():
    state()


def current_user(authorization: str | None = Header(default=None)):
    s = state()
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = s["store"].user_for_token(token)
    if not user:
        raise HTTPException(401, "Not signed in")
    user["token"] = token
    return user


class LoginIn(BaseModel):
    user_id: str = Field(max_length=32)
    password: str = Field(max_length=256)


class PasswordIn(BaseModel):
    old: str = Field(max_length=256)
    new: str = Field(min_length=8, max_length=256)


class ConvIn(BaseModel):
    sim_date: str | None = Field(default=None, max_length=10)


class ChatIn(BaseModel):
    conv_id: str = Field(max_length=40)
    text: str = Field(min_length=1, max_length=4000)


def _now():
    return datetime.now(timezone.utc)


def _recent_fails(store: Store, user_id: str, ip: str) -> int:
    """Failed attempts for this account since its last success (per-account lock), and an IP-wide cap
    of 4x that so one client cannot spray many accounts."""
    since = (_now() - timedelta(minutes=WINDOW_MIN)).isoformat(timespec="seconds")
    rows = store._q("SELECT ok FROM login_attempts WHERE user_id=? AND at>=? ORDER BY rowid DESC", (user_id, since))
    n = 0
    for r in rows:
        if r["ok"]:
            break
        n += 1
    ip_fails = store._q("SELECT COUNT(*) c FROM login_attempts WHERE ip=? AND ok=0 AND at>=?", (ip, since))[0]["c"]
    return max(n, ip_fails // 4)


@app.get("/api/health")
def health():
    s = state()
    return {"ok": True, "as_of": s["data"].load_report["as_of"], "wells": s["data"].load_report["wells"]}


@app.get("/api/users")
def users():
    s = state()
    teams = s["data"].teams
    return [{**u, "team_name": teams.get(u["team_id"], {}).get("name", u["team_id"])} for u in s["store"].list_users()]


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, x_forwarded_for: str | None = Header(default=None)):
    s = state()
    store = s["store"]
    ip = (x_forwarded_for or (request.client.host if request.client else "?")).split(",")[0].strip()
    if _recent_fails(store, body.user_id, ip) >= MAX_FAILS:
        raise HTTPException(429, f"Too many failed attempts. Try again in {LOCK_MIN} minutes.")
    token = store.login(body.user_id, body.password)
    store._x("INSERT INTO login_attempts VALUES (?,?,?,?)", (body.user_id, ip, 1 if token else 0,
                                                            _now().isoformat(timespec="seconds")))
    if not token:
        left = MAX_FAILS - _recent_fails(store, body.user_id, ip)
        raise HTTPException(401, f"Invalid credentials. {max(left, 0)} attempt(s) left before a temporary lock.")
    return {"token": token, "user": store.user_for_token(token), "expires_in": 7 * 24 * 3600}


@app.post("/api/auth/logout")
def logout(user=Depends(current_user)):
    state()["store"].logout(user["token"])
    return {"ok": True}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    s = state()
    return {k: v for k, v in user.items() if k != "token"} | {
        "team_name": s["data"].teams.get(user["team_id"], {}).get("name", user["team_id"])}


@app.post("/api/auth/password")
def change_password(body: PasswordIn, user=Depends(current_user)):
    store = state()["store"]
    if not store.change_password(user["user_id"], body.old, body.new):
        raise HTTPException(400, "Current password is wrong or the new one is too short.")
    # revoke every other session of this user
    store._x("DELETE FROM auth_sessions WHERE user_id=? AND token!=?", (user["user_id"], user["token"]))
    return {"ok": True}


@app.get("/api/overview")
def overview(user=Depends(current_user)):
    s = state()
    eng, d = s["eng"], s["data"]
    eng.refresh()
    L = eng.latest[~eng.latest.plugged]
    since = d.as_of - timedelta(days=90)
    sp = eng.I[eng.I.real_spill & (eng.I.t >= since)]
    R = d.reg
    open_fines = float(R[R.status == "open"].fine_usd.fillna(0).sum()) if len(R) else 0.0
    open_rep = int((d.mnt.end > d.as_of).sum())
    areas = []
    for aid, a in d.areas.items():
        la = L[L.area_id == aid]
        areas.append({"area_id": aid, "name": a.get("name"), "wells": int(len(la)),
                      "producing": int(la.producing.sum()), "lat": float(la.lat.mean()) if len(la) else None,
                      "lon": float(la.lon.mean()) if len(la) else None})
    wells = [{"asset_id": r.asset_id, "lat": r.lat, "lon": r.lon, "producing": bool(r.producing), "area_id": r.area_id,
              "well_type": r.well_type} for r in L.itertuples()]
    return {"as_of": d.load_report["as_of"], "as_of_label": fmt_date(d.as_of), "wells": int(len(L)),
            "producing": int(L.producing.sum()), "not_producing": int((~L.producing).sum()),
            "plugged": int(eng.latest.plugged.sum()), "spills_90d": int(len(sp)),
            "spill_bbl_90d": round(float(sp.spill_est_volume_bbl.sum()), 1), "open_fines_usd": open_fines,
            "open_repairs": open_rep, "areas": areas, "well_points": wells,
            "well_types": d.load_report["well_types"], "model": config.MODEL}


@app.get("/api/conversations")
def conversations(user=Depends(current_user)):
    return state()["store"].conversations(user["user_id"])


@app.post("/api/conversations")
def new_conversation(body: ConvIn, user=Depends(current_user)):
    s = state()
    sim = body.sim_date or str(s["data"].as_of.date())
    cid = s["store"].new_conversation(user["user_id"], sim)
    return s["store"].conversation(user["user_id"], cid)


@app.get("/api/conversations/{conv_id}/messages")
def messages(conv_id: str, user=Depends(current_user)):
    s = state()
    if not s["store"].conversation(user["user_id"], conv_id):
        raise HTTPException(404, "Conversation not found")
    return s["store"].messages(user["user_id"], conv_id)


@app.post("/api/chat")
def chat(body: ChatIn, user=Depends(current_user)):
    s = state()
    conv = s["store"].conversation(user["user_id"], body.conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    try:
        out = s["agent"].run(user, conv, body.text)
    except Exception as e:  # surfaced to the UI as a readable error
        raise HTTPException(502, f"The model call failed: {e}")
    return out


@app.post("/api/admin/reset")
def reset(user=Depends(current_user)):
    s = state()
    if user["role"] not in ("production_supervisor", "hse_officer", "maintenance_lead"):
        raise HTTPException(403, "Only supervisors, leads and HSE can reset demo memory")
    s["store"].reset_memory()
    s["eng"].refresh(force=True)
    return {"ok": True}
