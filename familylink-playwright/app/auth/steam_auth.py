# app/auth/steam_auth.py
import asyncio
import os
import time
from typing import Any, Dict, List

from playwright.async_api import async_playwright

from app.storage.steam_state import save_steam_state, find_cookie


class SteamCookieAuthManager:
    def __init__(self):
        self.profile_dir = os.getenv("STEAM_PROFILE_DIR", "/share/steam-auth/profile")
        self.state_file = os.getenv("STEAM_STATE_FILE", "/share/steam-auth/steam-state.json")
        self.language = os.getenv("LANGUAGE", "de-DE")
        self.timezone = os.getenv("TIMEZONE", "Europe/Berlin")
        self.login_timeout = int(os.getenv("STEAM_LOGIN_TIMEOUT", "300"))
        self.require_parental = os.getenv("STEAM_REQUIRE_PARENTAL", "false").lower() in (
            "1", "true", "yes", "on"
        )

    def _cookies_ready(self, cookies: List[Dict[str, Any]]) -> bool:
        steam_login = find_cookie(cookies, "steamLoginSecure", "store.steampowered.com")
        sessionid = find_cookie(cookies, "sessionid", "store.steampowered.com")

        if not steam_login or not sessionid:
            return False

        if self.require_parental:
            steam_parental = find_cookie(cookies, "steamparental", "store.steampowered.com")
            if not steam_parental:
                return False

        return True

    async def login_and_export(self) -> Dict[str, Any]:
        os.makedirs(self.profile_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                self.profile_dir,
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                locale=self.language,
                timezone_id=self.timezone,
                viewport={"width": 1280, "height": 900},
            )

            try:
                page = context.pages[0] if context.pages else await context.new_page()

                await page.goto("https://store.steampowered.com/", wait_until="domcontentloaded")
                await asyncio.sleep(2)

                cookies = await context.cookies()
                if self._cookies_ready(cookies):
                    save_steam_state(self.state_file, cookies)
                    return {
                        "ok": True,
                        "message": "Vorhandenes Steam-Profil wiederverwendet",
                        "state_file": self.state_file,
                        "require_parental": self.require_parental,
                    }

                await page.goto("https://store.steampowered.com/login/", wait_until="domcontentloaded")

                deadline = time.time() + self.login_timeout
                while time.time() < deadline:
                    await asyncio.sleep(2)

                    cookies = await context.cookies()

                    if self._cookies_ready(cookies):
                        save_steam_state(self.state_file, cookies)
                        return {
                            "ok": True,
                            "message": "Steam-Cookies exportiert",
                            "state_file": self.state_file,
                            "require_parental": self.require_parental,
                        }

                return {
                    "ok": False,
                    "message": "Steam-Login Timeout",
                    "state_file": self.state_file,
                    "require_parental": self.require_parental,
                }
            finally:
                await context.close()
