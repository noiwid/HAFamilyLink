"""Client to read cookies from Family Link Auth add-on or standalone container."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import aiohttp
from cryptography.fernet import Fernet
from yarl import URL

from homeassistant.core import HomeAssistant

from ..const import AUTH_SOURCE_MANAGED, AUTH_SOURCE_MANUAL

_LOGGER = logging.getLogger(__name__)

# Addon slug suffix (the hash prefix is derived from the repository URL)
_ADDON_SLUG_SUFFIX = "familylink-playwright"
_ADDON_PORT = 8099

# Default URL for local add-on (Home Assistant OS/Supervised)
DEFAULT_AUTH_URL = "http://localhost:8099"


def normalize_auth_url(value: str, *, allow_legacy_query: bool = False) -> str:
    """Return a safe, canonical authentication server base URL.

    A non-root path is retained as the API base path so deployments behind a
    reverse proxy can use URLs such as ``https://example.test/familylink``.
    """
    value = value.strip()
    if "#" in value:
        raise ValueError("URL fragments are not supported")
    if not allow_legacy_query and "?" in value:
        raise ValueError("URL query parameters are not supported")
    url = URL(value)
    if url.scheme not in {"http", "https"} or url.host is None:
        raise ValueError("Invalid authentication server URL")
    if url.user is not None or url.password is not None:
        raise ValueError("Credentials must not be embedded in the URL")
    if url.query and not allow_legacy_query:
        raise ValueError("URL query parameters are not supported")
    return str(url.with_query(None).with_fragment(None)).rstrip("/")


def split_legacy_auth_url(value: str) -> tuple[str, str | None]:
    """Split a version-1 URL into a safe base URL and optional API key."""
    value = value.strip()
    url = URL(value)
    clean_url = normalize_auth_url(value, allow_legacy_query=True)
    if "?" in value and not url.query:
        raise ValueError("Legacy URL contains an empty query delimiter")
    if not url.query:
        return clean_url, None
    if set(url.query) != {"api_key"}:
        raise ValueError("Unsupported legacy URL query parameters")
    keys = url.query.getall("api_key")
    if len(keys) != 1 or not keys[0].strip():
        raise ValueError("Legacy URL must contain exactly one non-empty API key")
    return clean_url, keys[0].strip()


class AuthServerConnectionError(Exception):
    """The configured authentication server health endpoint is unavailable."""


class AuthServerApiKeyError(Exception):
    """The configured authentication server rejected its API key."""


class AuthServerCookiesUnavailable(Exception):
    """The authentication server is reachable but has no usable cookies."""


class AddonCookieClient:
    """Client to read cookies from add-on via API or shared storage."""

    SHARE_DIR = Path("/share/familylink")
    COOKIE_FILE = "cookies.enc"
    KEY_FILE = ".key"
    API_KEY_FILE = "api_key"  # Written by the auth add-on, protects /api/cookies

    def __init__(
        self,
        hass: HomeAssistant,
        auth_url: str | None = None,
        api_key: str | None = None,
        auth_source: str | None = None,
    ):
        """Initialize addon cookie client.

        Args:
            hass: Home Assistant instance
            auth_url: Optional query-free auth server URL (Docker standalone).
            api_key: Optional cookie API key, stored separately from the URL.
            auth_source: Explicit endpoint ownership for new config entries.
        """
        self.hass = hass
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self.auth_url = normalize_auth_url(auth_url) if auth_url else None
        if auth_source not in {None, AUTH_SOURCE_MANAGED, AUTH_SOURCE_MANUAL}:
            raise ValueError("Unknown authentication source")
        self.auth_source = auth_source
        self.storage_path = self.SHARE_DIR / self.COOKIE_FILE
        self.key_file = self.SHARE_DIR / self.KEY_FILE
        self.api_key_file = self.SHARE_DIR / self.API_KEY_FILE
        self._detected_url: str | None = None
        self._supervisor_url_resolved = False
        self.last_fetch_status: int | None = None  # HTTP status of last cookie fetch

    async def _get_shared_api_key(self) -> str | None:
        """Read the key belonging to the Supervisor-managed auth add-on."""
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

    async def _fetch_cookies_from_url(
        self,
        url: str,
        *,
        api_key: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """Fetch cookies from auth server API.

        Args:
            url: Base URL of the auth server (e.g., http://localhost:8099)

        Returns:
            List of cookies or None if failed
        """
        api_url = f"{url.rstrip('/')}/api/cookies"
        self.last_fetch_status = None
        headers = {"X-API-Key": api_key} if api_key else {}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=False,
                ) as response:
                    self.last_fetch_status = response.status
                    if response.status == 200:
                        data = await response.json()
                        if not isinstance(data, dict):
                            return None
                        cookies = data.get("cookies", [])
                        if not isinstance(cookies, list) or not all(
                            isinstance(cookie, dict) for cookie in cookies
                        ):
                            return None
                        _LOGGER.info(f"Loaded {len(cookies)} cookies from API ({url})")
                        return cookies
                    elif response.status == 404:
                        _LOGGER.debug(f"No cookies found at {api_url}")
                        return None
                    elif response.status == 403:
                        _LOGGER.warning(
                            "Authentication server rejected the configured cookie API "
                            "key (403). Verify the separate API key setting."
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
                async with session.get(
                    health_url,
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=False,
                ) as response:
                    return response.status == 200
        except Exception:
            return False

    async def async_validate_manual_endpoint(self) -> list[dict[str, Any]]:
        """Validate the configured manual endpoint without source fallback.

        Raises a distinct public exception for connectivity, API-key, and
        cookie-availability failures so config flows do not need private HTTP
        helpers or transport-status inspection.
        """
        if not self.auth_url or not await self._check_url_available(self.auth_url):
            raise AuthServerConnectionError

        cookies = await self._fetch_cookies_from_url(
            self.auth_url,
            api_key=self._api_key,
        )
        if cookies:
            return cookies
        if self.last_fetch_status == 403:
            raise AuthServerApiKeyError
        if self.last_fetch_status is None:
            raise AuthServerConnectionError
        raise AuthServerCookiesUnavailable

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
            - ("managed_addon", "http://...") for the Supervisor add-on
            - ("api", "http://...") for a manual/local API
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
            return ("managed_addon", supervisor_url)

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
        # New config entries persist endpoint ownership explicitly.
        if self.auth_source == AUTH_SOURCE_MANUAL:
            if not self.auth_url:
                return None
            cookies = await self._fetch_cookies_from_url(
                self.auth_url,
                api_key=self._api_key,
            )
            if cookies is None:
                _LOGGER.warning(
                    "Failed to load cookies from configured authentication server"
                )
            return cookies

        if self.auth_source == AUTH_SOURCE_MANAGED:
            return await self._load_managed_cookies()

        # Compatibility for pre-marker entries. An explicit key makes the
        # endpoint manual. A keyless URL is recognized as managed only when it
        # matches the current Supervisor endpoint exactly.
        if self.auth_url:
            if self._api_key:
                cookies = await self._fetch_cookies_from_url(
                    self.auth_url,
                    api_key=self._api_key,
                )
                if cookies is None:
                    _LOGGER.warning(
                        "Failed to load cookies from configured authentication server"
                    )
                return cookies

            # Older auto-detected entries stored the Supervisor URL without an
            # origin marker. Resolve it again and use the shared key only when
            # both canonical endpoints match exactly.
            resolved_url = await self._get_addon_url()
            if resolved_url and normalize_auth_url(resolved_url) == self.auth_url:
                cookies = await self._fetch_cookies_from_url(
                    self.auth_url,
                    api_key=await self._get_shared_api_key(),
                )
                if cookies is not None or self.last_fetch_status == 403:
                    return cookies
                _LOGGER.debug("Managed add-on API unavailable, trying shared file")
                return await self._load_cookies_from_file()

            cookies = await self._fetch_cookies_from_url(self.auth_url)
            if cookies is None:
                _LOGGER.warning(
                    "Failed to load cookies from configured authentication server"
                )
            return cookies

        return await self._load_managed_cookies()

    async def _load_managed_cookies(self) -> list[dict[str, Any]] | None:
        """Load from Supervisor/default/file sources without crossing credentials."""
        # The shared key belongs only to the Supervisor-managed add-on.
        resolved_url = await self._get_addon_url()
        if resolved_url:
            cookies = await self._fetch_cookies_from_url(
                resolved_url,
                api_key=await self._get_shared_api_key(),
            )
            if cookies is not None or self.last_fetch_status == 403:
                return cookies
            _LOGGER.debug("Managed add-on API unavailable, trying shared file")
            return await self._load_cookies_from_file()

        # A legacy local standalone endpoint has no associated shared key.
        cookies = await self._fetch_cookies_from_url(DEFAULT_AUTH_URL)
        if cookies is not None:
            return cookies

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
