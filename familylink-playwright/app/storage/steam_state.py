# app/storage/steam_state.py
import json
import os
import time
from typing import Any, Dict, List, Optional


def ensure_parent_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def save_steam_state(path: str, cookies: List[Dict[str, Any]]) -> None:
    ensure_parent_dir(path)
    payload = {
        "saved_at": int(time.time()),
        "cookies": cookies,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_steam_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_steam_cookies(path: str) -> List[Dict[str, Any]]:
    return load_steam_state(path).get("cookies", [])


def find_cookie(
    cookies: List[Dict[str, Any]],
    name: str,
    domain_contains: str = "store.steampowered.com",
) -> Optional[Dict[str, Any]]:
    for cookie in cookies:
        if cookie.get("name") == name and domain_contains in cookie.get("domain", ""):
            return cookie
    return None


def redact_cookies(cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for cookie in cookies:
        c = dict(cookie)
        if c.get("value"):
            c["value"] = c["value"][:8] + "..."
        result.append(c)
    return result
