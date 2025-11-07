"""Client to read cookies from Family Link Auth add-on."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class AddonCookieClient:
    """Client to read cookies from add-on shared storage."""

    SHARE_DIR = Path("/share/familylink")
    COOKIE_FILE = "cookies.enc"
    KEY_FILE = ".key"

    def __init__(self, hass: HomeAssistant):
        """Initialize addon cookie client."""
        self.hass = hass
        self.storage_path = self.SHARE_DIR / self.COOKIE_FILE
        self.key_file = self.SHARE_DIR / self.KEY_FILE

    def _get_encryption_key(self) -> bytes:
        """Get encryption key (must match add-on key)."""
        if not self.key_file.exists():
            raise FileNotFoundError(
                "Encryption key not found. Make sure the Family Link Auth add-on is installed and has been used at least once."
            )
        return self.key_file.read_bytes()

    async def load_cookies(self) -> list[dict[str, Any]] | None:
        """Load cookies from shared storage."""
        if not self.storage_path.exists():
            _LOGGER.debug("No cookies found in shared storage")
            return None

        try:
            # Read and decrypt
            encrypted = self.storage_path.read_bytes()
            key = self._get_encryption_key()
            fernet = Fernet(key)
            decrypted = fernet.decrypt(encrypted)

            # Parse
            data = json.loads(decrypted.decode())
            cookies = data.get("cookies", [])

            _LOGGER.info(f"Loaded {len(cookies)} cookies from add-on")
            return cookies

        except Exception as err:
            _LOGGER.error(f"Failed to load cookies from add-on: {err}")
            return None

    def cookies_available(self) -> bool:
        """Check if cookies are available."""
        return self.storage_path.exists() and self.key_file.exists()

    async def clear_cookies(self) -> None:
        """Clear stored cookies."""
        if self.storage_path.exists():
            self.storage_path.unlink()
            _LOGGER.info("Cleared addon cookies")
