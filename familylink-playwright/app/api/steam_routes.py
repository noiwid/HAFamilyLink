# app/api/steam_routes.py
import os

from fastapi import APIRouter, HTTPException

from app.auth.steam_auth import SteamCookieAuthManager
from app.storage.steam_state import load_steam_state, redact_cookies

router = APIRouter(prefix="/api/steam", tags=["steam"])


@router.get("/health")
async def steam_health():
    state_file = os.getenv("STEAM_STATE_FILE", "/share/steam-auth/steam-state.json")
    state = load_steam_state(state_file)
    return {
        "ok": True,
        "steam_enabled": os.getenv("STEAM_ENABLED", "true").lower() in ("1", "true", "yes", "on"),
        "state_file": state_file,
        "has_state": bool(state),
        "saved_at": state.get("saved_at"),
    }


@router.post("/login")
async def steam_login():
    enabled = os.getenv("STEAM_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    if not enabled:
        raise HTTPException(status_code=404, detail="Steam support disabled")

    manager = SteamCookieAuthManager()
    result = await manager.login_and_export()

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("message"))

    return result


@router.get("/cookies")
async def steam_cookies():
    state_file = os.getenv("STEAM_STATE_FILE", "/share/steam-auth/steam-state.json")
    state = load_steam_state(state_file)
    return {
        "ok": True,
        "state_file": state_file,
        "saved_at": state.get("saved_at"),
        "cookies": redact_cookies(state.get("cookies", [])),
    }
