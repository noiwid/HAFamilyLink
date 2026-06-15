"""Client to read cookies from Family Link Auth add-on or standalone container."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import aiohttp
from cryptography.fernet import Fernet

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Addon slug suffix (the hash prefix is derived from the repository URL)
_ADDON_SLUG_SUFFIX = "familylink-playwright"
_ADDON_PORT = 8099

# Default URL for local add-on (Home Assistant OS/Supervised)
DEFAULT_AUTH_URL = "http://localhost:8099"


class AddonCookieClient:
    """Client to read cookies from add-on via API or shared storage."""

    SHARE_DIR = Path("/share/familylink")
    COOKIE_FILE = "cookies.enc"
    KEY_FILE = ".key"
    API_KEY_FILE = "api_key"  # Written by the auth add-on, protects /api/cookies

    def __init__(self, hass: HomeAssistant, auth_url: str | None = None):
        """Initialize addon cookie client.

        Args:
            hass: Home Assistant instance
            auth_url: Optional URL for the auth server (for Docker standalone mode).
                May include an API key as a query parameter when the auth
                container is protected, e.g. "http://host:8099?api_key=secret".
        """
        self.hass = hass
        self._api_key: str | None = None
        if auth_url and "?" in auth_url:
            from urllib.parse import parse_qs

            auth_url, _, query = auth_url.partition("?")
            self._api_key = (parse_qs(query).get("api_key") or [None])[0]
        self.auth_url = auth_url
        self.storage_path = self.SHARE_DIR / self.COOKIE_FILE
        self.key_file = self.SHARE_DIR / self.KEY_FILE
        self.api_key_file = self.SHARE_DIR / self.API_KEY_FILE
        self._detected_url: str | None = None
        self._supervisor_url_resolved = False
        self.last_fetch_status: int | None = None  # HTTP status of last cookie fetch

    async def _get_api_key(self) -> str | None:
        """Resolve the API key protecting the auth server's cookie endpoint.

        Priority: key from the configured URL (?api_key=...), then the key
        file the add-on writes to the shared directory (add-on setups).
        """
        if self._api_key:
            return self._api_key

        def _read_key_file() -> str | None:
            try:
                return self.api_key_file.read_text().strip() or None
            except OSError:
                return None

        return await self.hass.async_add_executor_job(_read_key_file)

    async def _resolve_addon_url(self) -> str | None:
        """Resolve addon URL via Supervisor API.

        On HAOS, addon containers are not reachable via localhost.
        Each addon gets a Docker DNS hostname derived from its slug
        (underscores replaced with hyphens).
        """
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://supervisor/addons",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    addons = data.get("data", {}).get("addons", [])
                    for addon in addons:
                        slug = addon.get("slug", "")
                        if (
                            slug.endswith(f"_{_ADDON_SLUG_SUFFIX}")
                            and addon.get("state") == "started"
                        ):
                            hostname = slug.replace("_", "-")
                            url = f"http://{hostname}:{_ADDON_PORT}"
                            _LOGGER.debug(
                                "Resolved addon URL via Supervisor: %s", url
                            )
                            return url
        except Exception as err:
            _LOGGER.debug("Could not resolve addon URL via Supervisor: %s", err)
        return None

    async def _get_addon_url(self) -> str | None:
        """Get the Supervisor-resolved addon URL, caching the lookup.

        Returns the resolved Docker hostname URL, or None when the addon
        cannot be discovered via the Supervisor (non-HAOS setups).
        """
        if not self._supervisor_url_resolved:
            self._supervisor_url_resolved = True
            resolved = await self._resolve_addon_url()
            if resolved:
                self._detected_url = resolved
                _LOGGER.info("Addon URL resolved via Supervisor: %s", resolved)
        return self._detected_url

    async def _fetch_cookies_from_url(self, url: str) -> list[dict[str, Any]] | None:
        """Fetch cookies from auth server API.

        Args:
            url: Base URL of the auth server (e.g., http://localhost:8099)

        Returns:
            List of cookies or None if failed
        """
        api_url = f"{url.rstrip('/')}/api/cookies"
        self.last_fetch_status = None
        api_key = await self._get_api_key()
        headers = {"X-API-Key": api_key} if api_key else {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    self.last_fetch_status = response.status
                    if response.status == 200:
                        data = await response.json()
                        cookies = data.get("cookies", [])
                        _LOGGER.info(f"Loaded {len(cookies)} cookies from API ({url})")
                        return cookies
                    elif response.status == 404:
                        _LOGGER.debug(f"No cookies found at {api_url}")
                        return None
                    elif response.status == 403:
                        _LOGGER.warning(
                            "Auth server at %s rejected the request (403): the cookie "
                            "endpoint requires an API key. For remote/standalone setups, "
                            "append ?api_key=<key> to the configured auth URL — the key is "
                            "in the 'api_key' file of the auth container's data directory "
                            "(e.g. ./data/api_key).",
                            url,
                        )
                        return None
                    else:
                        _LOGGER.debug(f"API returned status {response.status} from {api_url}")
                        return None
        except aiohttp.ClientError as err:
            _LOGGER.debug(f"Failed to connect to {api_url}: {err}")
            return None
        except Exception as err:
            _LOGGER.debug(f"Error fetching cookies from {api_url}: {err}")
            return None

    async def _check_url_available(self, url: str) -> bool:
        """Check if auth server API is available at URL."""
        health_url = f"{url.rstrip('/')}/api/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _get_encryption_key(self) -> bytes:
        """Get encryption key (must match add-on key)."""
        if not await self.hass.async_add_executor_job(self.key_file.exists):
            raise FileNotFoundError(
                "Encryption key not found. Make sure the Family Link Auth add-on is installed and has been used at least once."
            )
        return await self.hass.async_add_executor_job(self.key_file.read_bytes)

    async def _load_cookies_from_file(self) -> list[dict[str, Any]] | None:
        """Load cookies from encrypted file (legacy/fallback mode)."""
        if not await self.hass.async_add_executor_job(self.storage_path.exists):
            _LOGGER.debug("No cookies found in shared storage")
            return None

        try:
            # Read and decrypt
            encrypted = await self.hass.async_add_executor_job(self.storage_path.read_bytes)
            key = await self._get_encryption_key()
            fernet = Fernet(key)
            decrypted = fernet.decrypt(encrypted)

            # Parse
            data = json.loads(decrypted.decode())
            cookies = data.get("cookies", [])

            _LOGGER.info(f"Loaded {len(cookies)} cookies from file")
            return cookies

        except Exception as err:
            _LOGGER.error(f"Failed to load cookies from file: {err}")
            return None

    async def _file_available(self) -> bool:
        """Check if cookie file is available."""
        storage_exists = await self.hass.async_add_executor_job(self.storage_path.exists)
        key_exists = await self.hass.async_add_executor_job(self.key_file.exists)
        return storage_exists and key_exists

    async def detect_auth_source(self) -> tuple[str, str | None]:
        """Detect available authentication source.

        Returns:
            Tuple of (source_type, url_or_none):
            - ("api", "http://...") if API is available
            - ("file", None) if file is available
            - ("none", None) if nothing is available
        """
        # 1. If custom URL is configured, check it first
        if self.auth_url:
            if await self._check_url_available(self.auth_url):
                self._detected_url = self.auth_url
                return ("api", self.auth_url)

        # 2. Resolve addon URL via Supervisor API (Docker hostname, HAOS)
        supervisor_url = await self._get_addon_url()
        if supervisor_url and await self._check_url_available(supervisor_url):
            self._detected_url = supervisor_url
            _LOGGER.info("Addon detected via Supervisor at %s", supervisor_url)
            return ("api", supervisor_url)

        # 3. Try default local URL (standalone / Docker Compose)
        if await self._check_url_available(DEFAULT_AUTH_URL):
            self._detected_url = DEFAULT_AUTH_URL
            return ("api", DEFAULT_AUTH_URL)

        # 4. Fallback to file
        if await self._file_available():
            return ("file", None)

        # 5. Nothing available
        return ("none", None)

    async def load_cookies(self) -> list[dict[str, Any]] | None:
        """Load cookies using best available method.

        Priority:
        1. Custom URL (if configured)
        2. Supervisor-resolved addon URL (HAOS installations)
        3. Default local API (localhost:8099)
        4. File fallback (/share/familylink/)
        """
        # 1. If custom URL is configured, use it
        if self.auth_url:
            cookies = await self._fetch_cookies_from_url(self.auth_url)
            if cookies is not None:
                return cookies
            _LOGGER.warning(f"Failed to load cookies from configured URL: {self.auth_url}")

        # 2. Try the Supervisor-resolved addon URL (HAOS installations)
        resolved_url = await self._get_addon_url()
        if resolved_url and resolved_url != self.auth_url:
            cookies = await self._fetch_cookies_from_url(resolved_url)
            if cookies is not None:
                return cookies

        # 3. Try default local API (standalone / Docker Compose)
        cookies = await self._fetch_cookies_from_url(DEFAULT_AUTH_URL)
        if cookies is not None:
            return cookies

        # 4. Fallback to file
        _LOGGER.debug("API not available, trying file fallback")
        return await self._load_cookies_from_file()

    async def cookies_available(self) -> bool:
        """Check if cookies are available from any source."""
        source_type, _ = await self.detect_auth_source()
        if source_type == "none":
            return False

        # Actually try to load cookies to verify they exist
        cookies = await self.load_cookies()
        return cookies is not None and len(cookies) > 0

    async def clear_cookies(self) -> None:
        """Clear stored cookies (file only, API doesn't support this)."""
        if await self.hass.async_add_executor_job(self.storage_path.exists):
            await self.hass.async_add_executor_job(self.storage_path.unlink)
            _LOGGER.info("Cleared addon cookies")
