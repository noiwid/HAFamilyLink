"""Session management for Google Family Link authentication."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..const import (
	CONF_COOKIE_FILE,
	DEFAULT_COOKIE_FILE,
	LOGGER_NAME,
	SESSION_REFRESH_INTERVAL,
)
from ..exceptions import CookieError, SessionExpiredError

_LOGGER = logging.getLogger(LOGGER_NAME)


class SessionManager:
	"""Manage authentication sessions and cookies."""

	def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
		"""Initialize the session manager."""
		self.hass = hass
		self.config = config
		self._cookie_file = config.get(CONF_COOKIE_FILE, DEFAULT_COOKIE_FILE)
		self._session_data: dict[str, Any] | None = None
		self._encryption_key: bytes | None = None

	async def async_load_session(self) -> dict[str, Any] | None:
		"""Load session data from storage."""
		cookie_path = self._get_cookie_file_path()
		
		if not cookie_path.exists():
			_LOGGER.debug("No existing session file found")
			return None

		try:
			# Read and decrypt session data
			with open(cookie_path, "rb") as file:
				encrypted_data = file.read()

			# Get encryption key
			encryption_key = self._get_encryption_key()
			fernet = Fernet(encryption_key)

			# Decrypt and parse
			decrypted_data = fernet.decrypt(encrypted_data)
			session_data = json.loads(decrypted_data.decode())

			# Validate session is not expired
			if self._is_session_expired(session_data):
				_LOGGER.warning("Loaded session has expired")
				await self.async_clear_session()
				return None

			self._session_data = session_data
			_LOGGER.debug("Successfully loaded session data")
			return session_data

		except Exception as err:
			_LOGGER.error("Failed to load session data: %s", err)
			# Clear corrupted session file
			await self.async_clear_session()
			return None

	async def async_save_session(self, session_data: dict[str, Any]) -> None:
		"""Save session data to storage."""
		try:
			# Add timestamp
			session_data["saved_at"] = dt_util.utcnow().isoformat()

			# Encrypt session data
			encryption_key = self._get_encryption_key()
			fernet = Fernet(encryption_key)
			
			session_json = json.dumps(session_data, indent=2)
			encrypted_data = fernet.encrypt(session_json.encode())

			# Save to file
			cookie_path = self._get_cookie_file_path()
			cookie_path.parent.mkdir(parents=True, exist_ok=True)

			with open(cookie_path, "wb") as file:
				file.write(encrypted_data)

			# Set restrictive permissions
			os.chmod(cookie_path, 0o600)

			self._session_data = session_data
			_LOGGER.debug("Successfully saved session data")

		except Exception as err:
			_LOGGER.error("Failed to save session data: %s", err)
			raise CookieError(f"Failed to save session: {err}") from err

	async def async_clear_session(self) -> None:
		"""Clear stored session data."""
		try:
			cookie_path = self._get_cookie_file_path()
			if cookie_path.exists():
				cookie_path.unlink()
				_LOGGER.debug("Cleared session file")

			self._session_data = None

		except Exception as err:
			_LOGGER.warning("Error clearing session file: %s", err)

	def get_cookies(self) -> list[dict[str, Any]]:
		"""Get cookies from current session."""
		if not self._session_data:
			raise SessionExpiredError("No active session")

		return self._session_data.get("cookies", [])

	def is_authenticated(self) -> bool:
		"""Check if we have a valid session."""
		return (
			self._session_data is not None
			and not self._is_session_expired(self._session_data)
		)

	def _get_cookie_file_path(self) -> Path:
		"""Get the full path to the cookie file."""
		return Path(self.hass.config.config_dir) / self._cookie_file

	def _get_encryption_key(self) -> bytes:
		"""Get or create encryption key."""
		if self._encryption_key is None:
			# Use Home Assistant's secret key as base
			secret = self.hass.config.secret_key.encode()
			# Create a Fernet-compatible key
			from cryptography.hazmat.primitives import hashes
			from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
			import base64

			kdf = PBKDF2HMAC(
				algorithm=hashes.SHA256(),
				length=32,
				salt=b"familylink_salt",
				iterations=100000,
			)
			key = base64.urlsafe_b64encode(kdf.derive(secret))
			self._encryption_key = key

		return self._encryption_key

	def _is_session_expired(self, session_data: dict[str, Any]) -> bool:
		"""Check if session data has expired."""
		if "saved_at" not in session_data:
			return True

		try:
			saved_at = datetime.fromisoformat(session_data["saved_at"].replace("Z", "+00:00"))
			expiry_time = saved_at + timedelta(seconds=SESSION_REFRESH_INTERVAL)
			return dt_util.utcnow() > expiry_time
		except (ValueError, TypeError):
			return True 