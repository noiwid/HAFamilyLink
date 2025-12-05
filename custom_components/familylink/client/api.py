"""API client for Google Family Link integration."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant

from ..auth.addon_client import AddonCookieClient
from ..const import (
	DEVICE_LOCK_ACTION,
	DEVICE_UNLOCK_ACTION,
	LOGGER_NAME,
)
from ..exceptions import (
	AuthenticationError,
	DeviceControlError,
	NetworkError,
	SessionExpiredError,
)
from .models import Device

_LOGGER = logging.getLogger(LOGGER_NAME)


class FamilyLinkClient:
	"""Client for interacting with Google Family Link API."""

	# Google Family Link API endpoints (reverse-engineered)
	BASE_URL = "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1"
	ORIGIN = "https://familylink.google.com"
	API_KEY = "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw"

	def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
		"""Initialize the Family Link client."""
		self.hass = hass
		self.config = config
		# Get auth_url from config if available (for Docker standalone mode)
		auth_url = config.get("auth_url")
		self.addon_client = AddonCookieClient(hass, auth_url=auth_url)
		self._session: aiohttp.ClientSession | None = None
		self._cookies: list[dict[str, Any]] | None = None
		self._account_id: str | None = None  # Cached supervised child ID

	async def async_authenticate(self) -> None:
		"""Authenticate with Family Link."""
		# Load cookies from add-on
		_LOGGER.debug("Loading cookies from Family Link Auth add-on")

		if not await self.addon_client.cookies_available():
			raise AuthenticationError(
				"No cookies found. Please use the Family Link Auth add-on to authenticate first."
			)

		self._cookies = await self.addon_client.load_cookies()

		if not self._cookies:
			raise AuthenticationError("Failed to load cookies from add-on")

		_LOGGER.info(f"Successfully loaded {len(self._cookies)} cookies from add-on")

	async def async_refresh_session(self) -> None:
		"""Refresh the authentication session."""
		# Clear current cookies and reload from add-on
		self._cookies = None

		# CRITICAL: Also clear cached cookie dict and header to force rebuild
		# Without this, the retry mechanism would reuse stale cached cookies
		if hasattr(self, '_cookie_dict'):
			del self._cookie_dict
		if hasattr(self, '_cookie_header'):
			del self._cookie_header

		if self._session:
			await self._session.close()
			self._session = None

		await self.async_authenticate()

	def is_authenticated(self) -> bool:
		"""Check if we have valid cookies."""
		return self._cookies is not None and len(self._cookies) > 0

	def _generate_sapisidhash(self, sapisid: str, origin: str) -> str:
		"""Generate SAPISIDHASH token for Google API authorization.

		Args:
			sapisid: The SAPISID cookie value
			origin: The origin URL (e.g., 'https://familylink.google.com')

		Returns:
			The SAPISIDHASH string in format: "{timestamp}_{sha1_hash}"
		"""
		timestamp = int(time.time())  # Unix timestamp in seconds
		to_hash = f"{timestamp} {sapisid} {origin}"
		sha1_hash = hashlib.sha1(to_hash.encode("utf-8")).hexdigest()
		sapisidhash = f"{timestamp}_{sha1_hash}"
		_LOGGER.debug(f"Generated SAPISIDHASH with timestamp={timestamp}, hash={sha1_hash[:16]}...")
		return sapisidhash

	def _get_cookies_dict(self) -> dict[str, str]:
		"""Get cookies as a simple dict for passing to requests.

		CookieJar doesn't work properly with cross-domain cookies from Playwright,
		so we pass cookies directly in each request instead.
		"""
		if not hasattr(self, '_cookie_dict'):
			self._cookie_dict = {}
			if self._cookies:
				for cookie in self._cookies:
					cookie_name = cookie.get("name", "")
					cookie_value = cookie.get("value", "")
					if cookie_name and cookie_value:
						# Strip quotes from cookie values (Playwright may add them)
						cookie_value = cookie_value.strip('"')
						self._cookie_dict[cookie_name] = cookie_value
				_LOGGER.debug(f"Built cookie dict with {len(self._cookie_dict)} cookies: {list(self._cookie_dict.keys())}")
		return self._cookie_dict

	def _get_cookie_header(self) -> str:
		"""Build Cookie header string manually to avoid aiohttp adding quotes.

		aiohttp automatically adds quotes around cookie values containing special chars like /,
		but Google/Playwright don't use this - they send raw values without quotes.
		"""
		if not hasattr(self, '_cookie_header'):
			cookies_dict = self._get_cookies_dict()
			# Build cookie header as: "name1=value1; name2=value2; ..."
			# No quotes around values, even if they contain /
			cookie_parts = [f"{name}={value}" for name, value in cookies_dict.items()]
			self._cookie_header = "; ".join(cookie_parts)
			_LOGGER.debug(f"Built Cookie header with {len(cookies_dict)} cookies (length: {len(self._cookie_header)} chars)")
		return self._cookie_header

	async def _get_session(self) -> aiohttp.ClientSession:
		"""Get or create HTTP session with proper headers."""
		if self._session is None:
			# Extract SAPISID cookie for authentication
			sapisid = None

			_LOGGER.debug("Creating new session with authentication")

			if self._cookies:
				_LOGGER.debug(f"Processing {len(self._cookies)} cookies for SAPISID")

				for cookie in self._cookies:
					cookie_name = cookie.get("name", "")
					cookie_domain = cookie.get("domain", "")

					# Find SAPISID cookie
					if cookie_name == "SAPISID":
						# Accept any google.com domain (with or without leading dot)
						# Playwright may store as ".google.com" or "google.com"
						domain_lower = cookie_domain.lower().lstrip(".")
						if domain_lower == "google.com" or domain_lower.endswith(".google.com"):
							sapisid = cookie.get("value", "").strip('"')
							_LOGGER.debug(f"✓ Found SAPISID cookie with domain: {cookie_domain}")
							_LOGGER.debug(f"SAPISID value (first 10 chars): {sapisid[:10]}...")
						else:
							_LOGGER.warning(f"Found SAPISID but wrong domain: {cookie_domain} (expected google.com)")

			if not sapisid:
				_LOGGER.error("✗ SAPISID cookie not found in authentication data")
				raise AuthenticationError("SAPISID cookie not found in authentication data")

			# Generate authorization header
			sapisidhash = self._generate_sapisidhash(sapisid, self.ORIGIN)
			_LOGGER.debug(f"Generated SAPISIDHASH (first 20 chars): {sapisidhash[:20]}...")

			# Create session with Google Family Link API headers
			# Note: We don't use a cookie jar - cookies are passed directly in each request
			headers = {
				"User-Agent": (
					"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
					"AppleWebKit/537.36 (KHTML, like Gecko) "
					"Chrome/120.0.0.0 Safari/537.36"
				),
				"Origin": self.ORIGIN,
				"Content-Type": "application/json+protobuf",
				"X-Goog-Api-Key": self.API_KEY,
				"Authorization": f"SAPISIDHASH {sapisidhash}",
			}

			_LOGGER.debug(f"Session headers: Origin={self.ORIGIN}, API_Key={self.API_KEY[:20]}...")
			_LOGGER.debug(f"Full SAPISIDHASH: {sapisidhash}")

			self._session = aiohttp.ClientSession(
				headers=headers,
				timeout=aiohttp.ClientTimeout(total=30),
			)

			_LOGGER.debug("✓ Session created successfully")

		return self._session

	async def async_get_family_members(self) -> dict[str, Any]:
		"""Get list of all family members.

		Returns:
			Family members data including parents and supervised children.
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			url = f"{self.BASE_URL}/families/mine/members"
			_LOGGER.debug(f"Requesting: GET {url}")

			async with session.get(
				url,
				headers={
					"Content-Type": "application/json",
					"Cookie": cookie_header
				}
			) as response:
				_LOGGER.debug(f"Response status: {response.status}")

				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"API Error {response.status}: {response_text[:500]}")

				response.raise_for_status()
				data = await response.json()
				_LOGGER.debug(f"✓ Fetched {len(data.get('members', []))} family members")
				return data

		except aiohttp.ClientResponseError as err:
			if err.status == 401:
				_LOGGER.error(f"✗ 401 Unauthorized - Session expired. Response headers: {err.headers}")
				raise SessionExpiredError("Session expired, please re-authenticate") from err
			_LOGGER.error("Failed to fetch family members: %s", err)
			raise NetworkError(f"Failed to fetch family members: {err}") from err
		except Exception as err:
			_LOGGER.error("Unexpected error fetching family members: %s", err)
			raise NetworkError(f"Failed to fetch family members: {err}") from err

	async def async_get_supervised_child_id(self) -> str:
		"""Get the user ID of the first supervised child.

		Returns:
			User ID of the supervised child.

		Raises:
			ValueError: If no supervised child is found.
		"""
		if self._account_id:
			return self._account_id

		members_data = await self.async_get_family_members()

		for member in members_data.get("members", []):
			supervision_info = member.get("memberSupervisionInfo")
			if supervision_info and supervision_info.get("isSupervisedMember"):
				self._account_id = member["userId"]
				_LOGGER.info(f"Found supervised child: {member['profile']['displayName']} (ID: {self._account_id})")
				return self._account_id

		raise ValueError("No supervised child found in family")

	async def async_get_apps_and_usage(self, account_id: str | None = None) -> dict[str, Any]:
		"""Get apps, devices, and usage data for a supervised account.

		Args:
			account_id: User ID of the supervised child (optional, uses cached ID if None)

		Returns:
			Complete apps and usage data including:
			- apps: List of installed apps with supervision settings
			- deviceInfo: List of devices
			- appUsageSessions: Daily screen time data per app
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Google expects multiple capabilities as separate URL parameters
			# ?capabilities=CAPABILITY_APP_USAGE_SESSION&capabilities=CAPABILITY_SUPERVISION_CAPABILITIES
			params = [
				("capabilities", "CAPABILITY_APP_USAGE_SESSION"),
				("capabilities", "CAPABILITY_SUPERVISION_CAPABILITIES"),
			]

			url = f"{self.BASE_URL}/people/{account_id}/appsandusage"
			_LOGGER.debug(f"Requesting: GET {url}")

			async with session.get(
				url,
				headers={
					"Content-Type": "application/json",
					"Cookie": cookie_header
				},
				params=params
			) as response:
				_LOGGER.debug(f"Response status: {response.status}")
				_LOGGER.debug(f"Response headers: {dict(response.headers)}")

				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"API Error {response.status}: {response_text}")
					_LOGGER.error(f"Request URL was: {url}?{params}")
					_LOGGER.error(f"Request headers: {dict(response.request_info.headers)}")

				response.raise_for_status()
				data = await response.json()
				_LOGGER.debug(
					f"✓ Fetched usage data: {len(data.get('apps', []))} apps, "
					f"{len(data.get('deviceInfo', []))} devices, "
					f"{len(data.get('appUsageSessions', []))} usage sessions"
				)
				return data

		except aiohttp.ClientResponseError as err:
			if err.status == 401:
				_LOGGER.error(f"✗ 401 Unauthorized - Session expired. Response headers: {err.headers}")
				raise SessionExpiredError("Session expired, please re-authenticate") from err
			_LOGGER.error("Failed to fetch apps and usage: %s", err)
			raise NetworkError(f"Failed to fetch apps and usage: {err}") from err
		except Exception as err:
			_LOGGER.error("Unexpected error fetching apps and usage: %s", err)
			raise NetworkError(f"Failed to fetch apps and usage: {err}") from err

	async def async_get_devices(self) -> list[dict[str, Any]]:
		"""Get list of Family Link devices.

		Returns:
			List of devices with information about model, name, and last activity.
		"""
		try:
			data = await self.async_get_apps_and_usage()
			devices = []

			for device_info in data.get("deviceInfo", []):
				display_info = device_info.get("displayInfo", {})
				device = {
					"id": device_info.get("deviceId"),
					"name": display_info.get("friendlyName", "Unknown Device"),
					"model": display_info.get("model", "Unknown"),
					"last_activity": display_info.get("lastActivityTimeMillis"),
					"capabilities": device_info.get("capabilityInfo", {}).get("capabilities", []),
				}
				devices.append(device)

			_LOGGER.debug(f"Returning {len(devices)} devices")
			return devices

		except Exception as err:
			_LOGGER.error("Failed to fetch devices: %s", err)
			raise NetworkError(f"Failed to fetch devices: {err}") from err

	async def async_get_daily_screen_time(
		self,
		account_id: str | None = None,
		target_date: datetime | None = None
	) -> dict[str, Any]:
		"""Get total screen time for a specific date.

		Args:
			account_id: User ID of the supervised child (optional)
			target_date: Date to get screen time for (defaults to today)

		Returns:
			Dictionary with:
			- total_seconds: Total screen time in seconds
			- formatted: Formatted time string (HH:MM:SS)
			- hours: Hours component
			- minutes: Minutes component
			- seconds: Seconds component
			- app_breakdown: Per-app usage breakdown
		"""
		if target_date is None:
			target_date = datetime.now()

		try:
			data = await self.async_get_apps_and_usage(account_id)
			total_seconds = 0
			app_breakdown = {}

			all_sessions = data.get("appUsageSessions", [])
			_LOGGER.debug(f"Found {len(all_sessions)} total app usage sessions")
			if all_sessions:
				_LOGGER.debug(f"First session example: {all_sessions[0]}")

			for session in all_sessions:
				session_date = session.get("date", {})

				# Check if this session is for the target date
				if (session_date.get("year") == target_date.year and
					session_date.get("month") == target_date.month and
					session_date.get("day") == target_date.day):

					# Extract seconds from "1809.5s" format
					usage_str = session.get("usage", "0s")
					usage_seconds = float(usage_str.replace("s", ""))
					total_seconds += usage_seconds

					# Track per-app usage
					package_name = session.get("appId", {}).get("androidAppPackageName", "unknown")
					app_breakdown[package_name] = app_breakdown.get(package_name, 0) + usage_seconds

			# Convert to hours, minutes, seconds
			hours = int(total_seconds // 3600)
			minutes = int((total_seconds % 3600) // 60)
			seconds = int(total_seconds % 60)

			_LOGGER.debug(
				f"Daily screen time for {target_date.date()}: {hours:02d}:{minutes:02d}:{seconds:02d} "
				f"({len(app_breakdown)} apps, {total_seconds} total seconds)"
			)
			if not app_breakdown:
				_LOGGER.debug(f"No app usage data found for {target_date.date()}")
			else:
				_LOGGER.debug(f"App breakdown: {app_breakdown}")

			return {
				"total_seconds": total_seconds,
				"formatted": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
				"hours": hours,
				"minutes": minutes,
				"seconds": seconds,
				"app_breakdown": app_breakdown,
				"date": target_date.date(),
			}

		except SessionExpiredError:
			raise  # Re-raise to trigger auth notification
		except Exception as err:
			_LOGGER.error("Failed to fetch daily screen time: %s", err)
			raise NetworkError(f"Failed to fetch daily screen time: {err}") from err

	async def async_get_location(
		self,
		account_id: str | None = None,
		refresh: bool = False
	) -> dict[str, Any] | None:
		"""Get location data for a supervised child.

		Args:
			account_id: User ID of the supervised child (optional)
			refresh: If True, request fresh location from device (uses more battery)
					If False, return cached location from Google servers

		Returns:
			Dictionary with location data:
			- latitude: Latitude coordinate
			- longitude: Longitude coordinate
			- accuracy: GPS accuracy in meters
			- timestamp: Location timestamp in milliseconds
			- timestamp_iso: ISO formatted timestamp
			- place_id: ID of the saved place (if in a known location)
			- place_name: Name of the saved place (e.g., "Maison")
			- place_address: Address of the saved place
			- source_device_id: Device ID that provided the location
			Or None if location is not available
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if account_id is None:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			url = f"{self.BASE_URL}/families/mine/location/{account_id}"
			params = [
				("locationRefreshMode", "REFRESH" if refresh else "DO_NOT_REFRESH"),
				("supportedConsents", "SUPERVISED_LOCATION_SHARING"),
			]

			_LOGGER.debug(f"Fetching location for child {account_id} (refresh={refresh})")

			async with session.get(
				url,
				params=params,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				}
			) as response:
				if response.status == 401:
					_LOGGER.error("✗ 401 Unauthorized - Session expired fetching location")
					raise SessionExpiredError("Session expired, please re-authenticate")
				if response.status == 404:
					_LOGGER.warning(f"Location not available for child {account_id}")
					return None
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to fetch location (HTTP {response.status}): {response_text}")
					return None

				data = await response.json()
				_LOGGER.debug(f"Location response: {str(data)[:500]}")

				# Parse the protobuf-like JSON response
				# Structure: [[null, timestamp], [child_id, status, [location_data], ...]]
				if not isinstance(data, list) or len(data) < 2:
					_LOGGER.warning(f"Unexpected location response structure: {data}")
					return None

				child_data = data[1] if len(data) > 1 else None
				if not isinstance(child_data, list) or len(child_data) < 3:
					_LOGGER.warning(f"No location data in response for child {account_id}")
					return None

				location_array = child_data[2] if len(child_data) > 2 else None
				if not isinstance(location_array, list) or len(location_array) < 2:
					_LOGGER.warning(f"Invalid location array for child {account_id}")
					return None

				# Extract coordinates [lat, lng]
				coords = location_array[0] if len(location_array) > 0 else None
				if not isinstance(coords, list) or len(coords) < 2:
					_LOGGER.warning(f"Invalid coordinates for child {account_id}")
					return None

				latitude = coords[0]
				longitude = coords[1]

				# Extract timestamp (milliseconds)
				timestamp_ms = location_array[1] if len(location_array) > 1 else None
				timestamp_ms = int(timestamp_ms) if timestamp_ms else None

				# Extract accuracy (meters)
				accuracy = location_array[2] if len(location_array) > 2 else None
				accuracy = int(accuracy) if accuracy else None

				# Extract place info if available (index 4)
				place_info = location_array[4] if len(location_array) > 4 else None
				place_id = None
				place_name = None
				place_address = None

				if isinstance(place_info, list) and len(place_info) > 2:
					place_id = place_info[0]
					place_name = place_info[1]
					place_address = place_info[2]

				# Extract source device ID (index 6)
				source_device_id = location_array[6] if len(location_array) > 6 else None

				# Convert timestamp to ISO format
				timestamp_iso = None
				if timestamp_ms:
					try:
						timestamp_iso = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
					except (ValueError, OSError):
						pass

				result = {
					"latitude": latitude,
					"longitude": longitude,
					"accuracy": accuracy,
					"timestamp": timestamp_ms,
					"timestamp_iso": timestamp_iso,
					"place_id": place_id,
					"place_name": place_name,
					"place_address": place_address,
					"source_device_id": source_device_id,
				}

				_LOGGER.debug(
					f"Location for child {account_id}: "
					f"({latitude}, {longitude}) accuracy={accuracy}m, "
					f"place={place_name or 'unknown'}, device={source_device_id}"
				)

				return result

		except SessionExpiredError:
			raise  # Re-raise to trigger auth notification
		except Exception as err:
			_LOGGER.error(f"Failed to fetch location for child {account_id}: {err}")
			return None

	async def async_block_app(self, package_name: str, account_id: str | None = None) -> bool:
		"""Block a specific app.

		Args:
			package_name: Android package name (e.g., com.youtube.android)
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Format: [account_id, [[[package_name], [1]]]]
			# [1] = block flag
			payload = json.dumps([account_id, [[[package_name], [1]]]])

			async with session.post(
				f"{self.BASE_URL}/people/{account_id}/apps:updateRestrictions",
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload
			) as response:
				response.raise_for_status()
				_LOGGER.info(f"Successfully blocked app: {package_name}")
				return True

		except aiohttp.ClientResponseError as err:
			if err.status == 401:
				raise SessionExpiredError("Session expired, please re-authenticate") from err
			_LOGGER.error(f"Failed to block app {package_name}: {err}")
			return False
		except Exception as err:
			_LOGGER.error(f"Unexpected error blocking app {package_name}: {err}")
			return False

	async def async_unblock_app(self, package_name: str, account_id: str | None = None) -> bool:
		"""Unblock a specific app by removing all restrictions.

		Args:
			package_name: Android package name
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Format: [account_id, [[[package_name], []]]]
			# Empty array = remove restrictions
			payload = json.dumps([account_id, [[[package_name], []]]])

			async with session.post(
				f"{self.BASE_URL}/people/{account_id}/apps:updateRestrictions",
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload
			) as response:
				response.raise_for_status()
				_LOGGER.info(f"Successfully unblocked app: {package_name}")
				return True

		except aiohttp.ClientResponseError as err:
			if err.status == 401:
				raise SessionExpiredError("Session expired, please re-authenticate") from err
			_LOGGER.error(f"Failed to unblock app {package_name}: {err}")
			return False
		except Exception as err:
			_LOGGER.error(f"Unexpected error unblocking app {package_name}: {err}")
			return False

	async def async_block_device_for_school(
		self,
		account_id: str | None = None,
		whitelist: list[str] | None = None
	) -> dict[str, Any]:
		"""Block all apps except essential ones (simulate device lock for school).

		Args:
			account_id: User ID of the supervised child (optional)
			whitelist: List of package names to keep allowed (optional)

		Returns:
			Dictionary with blocked count and list of blocked apps
		"""
		# Default essential apps whitelist
		default_whitelist = [
			"com.android.dialer",           # Phone
			"com.android.contacts",         # Contacts
			"com.android.mms",              # SMS/Messages
			"com.google.android.apps.messaging",  # Google Messages
			"com.android.settings",         # Settings
			"com.android.deskclock",        # Clock/Alarm
			"com.google.android.apps.maps", # Maps (emergency)
			"com.android.emergency",        # Emergency info
			"com.android.systemui",         # System UI
			"com.android.launcher3",        # Launcher
			"com.google.android.gms",       # Google Play Services
		]

		if whitelist:
			# Merge user whitelist with defaults
			whitelist = list(set(default_whitelist + whitelist))
		else:
			whitelist = default_whitelist

		_LOGGER.info(f"Blocking device for school mode. Whitelist: {len(whitelist)} apps")

		# Get all installed apps
		apps_data = await self.async_get_apps_and_usage(account_id)
		all_apps = apps_data.get("apps", [])

		blocked = []
		failed = []

		for app in all_apps:
			package_name = app.get("packageName", "")

			# Skip if in whitelist
			if package_name in whitelist:
				_LOGGER.debug(f"Skipping whitelisted app: {package_name}")
				continue

			# Skip if already blocked
			if app.get("supervisionSetting", {}).get("hidden", False):
				_LOGGER.debug(f"App already blocked: {package_name}")
				continue

			# Block the app
			success = await self.async_block_app(package_name, account_id)
			if success:
				blocked.append({
					"name": app.get("title", "Unknown"),
					"package": package_name
				})
			else:
				failed.append(package_name)

			# Small delay to avoid rate limiting
			await asyncio.sleep(0.1)

		_LOGGER.info(
			f"School mode activated: {len(blocked)} apps blocked, {len(failed)} failed, "
			f"{len(whitelist)} apps whitelisted"
		)

		return {
			"blocked_count": len(blocked),
			"blocked_apps": blocked,
			"failed_count": len(failed),
			"failed_apps": failed,
			"whitelisted_count": len(whitelist),
		}

	async def async_unblock_all_apps(self, account_id: str | None = None) -> dict[str, Any]:
		"""Unblock all apps (end school mode / unlock device).

		Args:
			account_id: User ID of the supervised child (optional)

		Returns:
			Dictionary with unblocked count and list of apps
		"""
		_LOGGER.info("Unblocking all apps (ending school mode)")

		# Get all apps
		apps_data = await self.async_get_apps_and_usage(account_id)
		all_apps = apps_data.get("apps", [])

		unblocked = []
		failed = []

		for app in all_apps:
			package_name = app.get("packageName", "")

			# Check if app is currently blocked
			if app.get("supervisionSetting", {}).get("hidden", False):
				success = await self.async_unblock_app(package_name, account_id)
				if success:
					unblocked.append({
						"name": app.get("title", "Unknown"),
						"package": package_name
					})
				else:
					failed.append(package_name)

				# Small delay to avoid rate limiting
				await asyncio.sleep(0.1)

		_LOGGER.info(
			f"All apps unblocked: {len(unblocked)} apps unblocked, {len(failed)} failed"
		)

		return {
			"unblocked_count": len(unblocked),
			"unblocked_apps": unblocked,
			"failed_count": len(failed),
			"failed_apps": failed,
		}

	async def async_control_device(self, device_id: str, action: str, child_id: str | None = None) -> bool:
		"""Control a Family Link device (lock/unlock).

		Uses the timeLimitOverrides:batchCreate endpoint discovered from browser DevTools.

		Args:
			device_id: Device ID to control
			action: "lock" or "unlock"
			child_id: Child's user ID (optional, will use first supervised child if not provided)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if action not in [DEVICE_LOCK_ACTION, DEVICE_UNLOCK_ACTION]:
			raise DeviceControlError(f"Invalid action: {action}")

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Get supervised child account ID
			if child_id is None:
				account_id = await self.async_get_supervised_child_id()
			else:
				account_id = child_id

			# Action codes discovered from browser DevTools:
			# Code 1 = LOCK (verrouiller)
			# Code 4 = UNLOCK (déverrouiller)
			action_code = 1 if action == DEVICE_LOCK_ACTION else 4

			# Payload format from browser: [null, account_id, [[null, null, action_code, device_id]], [1]]
			payload = json.dumps([
				None,
				account_id,
				[
					[None, None, action_code, device_id]
				],
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimitOverrides:batchCreate"
			_LOGGER.debug(f"Requesting device {action}: POST {url}")
			_LOGGER.debug(f"Payload: {payload}")

			async with session.post(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload
			) as response:
				_LOGGER.debug(f"Response status: {response.status}")

				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Device control failed {response.status}: {response_text}")
					return False

				response_data = await response.json()
				_LOGGER.debug(f"Device control response: {response_data}")
				_LOGGER.info(f"Successfully {action}ed device {device_id}")
				return True

		except Exception as err:
			_LOGGER.error("Failed to control device %s: %s", device_id, err)
			raise DeviceControlError(f"Failed to control device: {err}") from err

	async def async_get_applied_time_limits(self, account_id: str | None = None) -> dict[str, Any]:
		"""Get applied time limits for all devices (time remaining, windows, etc.).

		Args:
			account_id: User ID of the supervised child (optional)

		Returns:
			Dictionary with:
			- device_lock_states: Dict mapping device_id to locked state
			- devices: Dict mapping device_id to device time limit data:
				- total_allowed_minutes: Total allowed today
				- used_minutes: Time used today
				- remaining_minutes: Time remaining
				- daily_limit_enabled: Boolean
				- daily_limit_minutes: Configured daily limit
				- bedtime_window: {start_ms, end_ms} or None
				- schooltime_window: {start_ms, end_ms} or None
				- bedtime_active: Boolean
				- schooltime_active: Boolean
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if account_id is None:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			url = f"{self.BASE_URL}/people/{account_id}/appliedTimeLimits"
			params = [("capabilities", "TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME")]

			_LOGGER.debug(f"Fetching applied time limits from {url}")

			async with session.get(
				url,
				params=params,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				}
			) as response:
				if response.status == 401:
					response_text = await response.text()
					_LOGGER.error(f"✗ 401 Unauthorized - Session expired fetching applied time limits")
					raise SessionExpiredError("Session expired, please re-authenticate")
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to fetch applied time limits {response.status}: {response_text}")
					return {"device_lock_states": {}, "devices": {}}

				data = await response.json()
				_LOGGER.debug(f"Applied time limits response (first 500 chars): {str(data)[:500]}")

				device_lock_states = {}
				devices = {}

				if len(data) > 1 and isinstance(data[1], list):
					for device_data in data[1]:
						if not isinstance(device_data, list) or len(device_data) < 25:
							continue

						# Extract device ID
						device_id = None
						if device_data[0] and isinstance(device_data[0], list) and len(device_data[0]) > 3:
							device_id = device_data[0][3]
						elif len(device_data) > 25 and device_data[25]:
							device_id = device_data[25]

						if not device_id:
							continue

						# Parse lock state
						has_lock_override = device_data[0] is not None and isinstance(device_data[0], list)
						if has_lock_override and len(device_data[0]) > 2:
							action_code = device_data[0][2]
							is_locked = (action_code == 1)
						else:
							is_locked = False
						device_lock_states[device_id] = is_locked

						# Initialize device data
						device_info = {
							"total_allowed_minutes": 0,
							"used_minutes": 0,
							"remaining_minutes": 0,
							"daily_limit_enabled": False,
							"daily_limit_minutes": 0,
							"bedtime_window": None,
							"schooltime_window": None,
							"bedtime_active": False,
							"schooltime_active": False,
							"bonus_minutes": 0,
							"bonus_override_id": None
						}

						# Parse bonus override (device_data[0] if it exists and type == 10)
						# Structure: [override_id, timestamp, type, device_id, ..., [[duration_seconds]]]
						if device_data[0] and isinstance(device_data[0], list) and len(device_data[0]) > 13:
							override_type = device_data[0][2] if len(device_data[0]) > 2 else None
							if override_type == 10:  # Type 10 = time bonus
								override_id = device_data[0][0]
								override_device_id = device_data[0][3]

								# Parse bonus duration from position [13][0][0] (seconds string)
								if (len(device_data[0]) > 13 and
									isinstance(device_data[0][13], list) and
									len(device_data[0][13]) > 0 and
									isinstance(device_data[0][13][0], list) and
									len(device_data[0][13][0]) > 0):

									bonus_seconds_str = device_data[0][13][0][0]
									if isinstance(bonus_seconds_str, str) and bonus_seconds_str.isdigit():
										bonus_seconds = int(bonus_seconds_str)
										bonus_minutes_from_override = bonus_seconds // 60

										device_info["bonus_override_id"] = override_id
										# Store bonus minutes from override
										device_info["bonus_minutes"] = bonus_minutes_from_override
										_LOGGER.debug(
											f"Device {override_device_id}: Found bonus override - "
											f"id={override_id}, duration={bonus_minutes_from_override}min "
											f"({bonus_seconds}s)"
										)


						# Parse time data from positions 19-20
						# Position 19: appears to contain remaining time when bonus is active
						# Position 20: used time on daily_limit (ms string)
						if len(device_data) > 20:
							# Log position 19 for debugging
							if isinstance(device_data[19], str) and device_data[19].isdigit():
								pos19_ms = int(device_data[19])
								pos19_mins = pos19_ms // 60000
								_LOGGER.debug(
									f"Device {device_id}: Position 19 contains {pos19_mins} minutes ({pos19_ms} ms) "
									f"- override_id={device_info.get('bonus_override_id')}"
								)

							# Parse used time from position 20
							if isinstance(device_data[20], str) and device_data[20].isdigit():
								used_ms = int(device_data[20])
								device_info["used_minutes"] = used_ms // 60000
								_LOGGER.debug(f"Device {device_id}: Used time = {device_info['used_minutes']} minutes ({used_ms} ms)")

						# Parse windows and CAEQBg/CAMQ tuples
						# Look for bedtime window (indices vary, usually around 3-10)
						# Look for schooltime window
						# Look for CAEQBg (daily limit) tuple
						# Format: ["CAEQBg", day, stateFlag, minutes_or_hours, ...]
						_LOGGER.debug(f"Device {device_id}: device_data has {len(device_data)} elements")
						_LOGGER.debug(f"Device {device_id}: First 10 elements (types): {[type(x).__name__ for x in device_data[:10]]}")

						# Get current day of week (1=Monday, 7=Sunday)
						current_day = datetime.now().isoweekday()
						_LOGGER.debug(f"Device {device_id}: Current day of week: {current_day}")

						for idx, item in enumerate(device_data):
							if isinstance(item, list) and len(item) >= 4:
								_LOGGER.debug(f"Device {device_id}: item[{idx}] is list with {len(item)} elements, first element: {item[0]}")
								if isinstance(item[0], str):
									# CAEQ* = daily limit (6 elem) OR bedtime window (8 elem)
									if item[0].startswith("CAEQ"):
										if len(item) == 6:
											# Daily limit: ["CAEQ*", day, stateFlag, minutes, createdMs, updatedMs]
											day = item[1] if len(item) > 1 else None
											state_flag = item[2] if len(item) > 2 else None
											minutes = item[3] if len(item) > 3 else None

											_LOGGER.debug(
												f"Device {device_id}: Found CAEQ daily limit at index {idx}: "
												f"day={day}, state_flag={state_flag}, minutes={minutes}"
											)

											# Daily limit is ACTIVE only if:
											# 1. It's for the CURRENT day
											# 2. Index < 10 (active section, not config/historical)
											# 3. state_flag == 2 (enabled)
											if isinstance(day, int) and isinstance(state_flag, int) and isinstance(minutes, int):
												if day == current_day:
													is_active_position = (idx < 10)
													is_enabled_flag = (state_flag == 2)
													daily_enabled = is_active_position and is_enabled_flag

													device_info["daily_limit_enabled"] = daily_enabled
													device_info["daily_limit_minutes"] = minutes

													_LOGGER.debug(
														f"Device {device_id}: CURRENT DAY ({day}) daily_limit - "
														f"index={idx}, position_active={is_active_position}, "
														f"state_flag={state_flag}, enabled_flag={is_enabled_flag}, "
														f"FINAL enabled={daily_enabled}, minutes={minutes}"
													)
										elif len(item) == 8:
											# Bedtime window: ["CAEQ*", day, stateFlag, [startH, startM], [endH, endM], createdMs, updatedMs, policyId]
											day = item[1] if len(item) > 1 else None
											state_flag = item[2] if len(item) > 2 else None
											start_time = item[3] if len(item) > 3 else None
											end_time = item[4] if len(item) > 4 else None

											_LOGGER.debug(
												f"Device {device_id}: CAEQ is bedtime window (8 elements) - "
												f"day={day}, state_flag={state_flag}, start={start_time}, end={end_time}"
											)

											# Parse bedtime window if it's for current day and enabled
											if (isinstance(day, int) and day == current_day and
												isinstance(state_flag, int) and state_flag == 2 and
												isinstance(start_time, list) and len(start_time) == 2 and
												isinstance(end_time, list) and len(end_time) == 2):

												# Convert [HH, MM] to epoch milliseconds for today
												now = datetime.now()
												start_hour, start_min = start_time[0], start_time[1]
												end_hour, end_min = end_time[0], end_time[1]

												# Create datetime objects for start and end
												start_dt = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
												end_dt = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)

												# If end time is before start time, it crosses midnight (e.g., 20:55 -> 10:00)
												# In this case, if current time is after start OR before end, bedtime is active
												if end_hour < start_hour or (end_hour == start_hour and end_min < start_min):
													# Crosses midnight
													bedtime_active = (now >= start_dt) or (now < end_dt)
												else:
													# Same day window
													bedtime_active = (start_dt <= now < end_dt)

												device_info["bedtime_window"] = {
													"start_ms": int(start_dt.timestamp() * 1000),
													"end_ms": int(end_dt.timestamp() * 1000)
												}
												device_info["bedtime_active"] = bedtime_active

												_LOGGER.debug(
													f"Device {device_id}: Bedtime window parsed - "
													f"start={start_hour:02d}:{start_min:02d}, end={end_hour:02d}:{end_min:02d}, "
													f"current_time={now.strftime('%H:%M')}, active={bedtime_active}"
												)
									# CAMQ = schooltime
									elif item[0].startswith("CAMQ"):
										# Same format as bedtime
										if len(item) == 8:
											day = item[1] if len(item) > 1 else None
											state_flag = item[2] if len(item) > 2 else None
											start_time = item[3] if len(item) > 3 else None
											end_time = item[4] if len(item) > 4 else None

											_LOGGER.debug(
												f"Device {device_id}: CAMQ is schooltime window (8 elements) - "
												f"day={day}, state_flag={state_flag}, start={start_time}, end={end_time}"
											)

											# Parse schooltime window if it's for current day and enabled
											if (isinstance(day, int) and day == current_day and
												isinstance(state_flag, int) and state_flag == 2 and
												isinstance(start_time, list) and len(start_time) == 2 and
												isinstance(end_time, list) and len(end_time) == 2):

												# Convert [HH, MM] to epoch milliseconds for today
												now = datetime.now()
												start_hour, start_min = start_time[0], start_time[1]
												end_hour, end_min = end_time[0], end_time[1]

												# Create datetime objects for start and end
												start_dt = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
												end_dt = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)

												# Schooltime shouldn't cross midnight, but handle it anyway
												if end_hour < start_hour or (end_hour == start_hour and end_min < start_min):
													schooltime_active = (now >= start_dt) or (now < end_dt)
												else:
													schooltime_active = (start_dt <= now < end_dt)

												device_info["schooltime_window"] = {
													"start_ms": int(start_dt.timestamp() * 1000),
													"end_ms": int(end_dt.timestamp() * 1000)
												}
												device_info["schooltime_active"] = schooltime_active

												_LOGGER.debug(
													f"Device {device_id}: Schooltime window parsed - "
													f"start={start_hour:02d}:{start_min:02d}, end={end_hour:02d}:{end_min:02d}, "
													f"current_time={now.strftime('%H:%M')}, active={schooltime_active}"
												)

							# Look for window objects (arrays with 2 epoch timestamps)
							elif isinstance(item, list) and len(item) == 2:
								if all(isinstance(x, (int, str)) for x in item):
									try:
										start_ms = int(item[0]) if isinstance(item[0], str) else item[0]
										end_ms = int(item[1]) if isinstance(item[1], str) else item[1]
										# Heuristic: if both are large epoch ms values
										if start_ms > 1000000000000 and end_ms > 1000000000000:
											# First window = bedtime, second = schooltime (heuristic)
											if device_info["bedtime_window"] is None:
												device_info["bedtime_window"] = {"start_ms": start_ms, "end_ms": end_ms}
												device_info["bedtime_active"] = True
												_LOGGER.debug(f"Device {device_id}: bedtime window {start_ms}-{end_ms}")
											elif device_info["schooltime_window"] is None:
												device_info["schooltime_window"] = {"start_ms": start_ms, "end_ms": end_ms}
												device_info["schooltime_active"] = True
												_LOGGER.debug(f"Device {device_id}: schooltime window {start_ms}-{end_ms}")
									except (ValueError, TypeError):
										pass

						# Calculate total_allowed_minutes and remaining_minutes
						# IMPORTANT: Bonus REPLACES normal time, it doesn't add to it!
						# - If bonus > 0: remaining = bonus only
						# - If bonus == 0: remaining = max(0, daily_limit - used)
						# ALSO calculate daily_limit_remaining (without bonus) for Daily Limit Reached sensor
						if device_info.get("daily_limit_enabled", False):
							daily_limit_mins = device_info.get("daily_limit_minutes", 0)
							bonus_mins = device_info.get("bonus_minutes", 0)
							used_mins = device_info.get("used_minutes", 0)

							if daily_limit_mins > 0:
								# ALWAYS calculate daily_limit_remaining (ignoring bonus)
								# This is used by "Daily Limit Reached" binary sensor
								device_info["daily_limit_remaining"] = max(0, daily_limit_mins - used_mins)

								if bonus_mins > 0:
									# Bonus is active: bonus REPLACES normal time
									device_info["total_allowed_minutes"] = bonus_mins
									device_info["remaining_minutes"] = bonus_mins
									_LOGGER.debug(
										f"Device {device_id}: BONUS ACTIVE - "
										f"bonus={bonus_mins} min (from override), "
										f"daily_limit={daily_limit_mins} min, "
										f"used={used_mins} min, "
										f"daily_limit_remaining={device_info['daily_limit_remaining']} min"
									)
								else:
									# No bonus: use daily_limit - used
									device_info["total_allowed_minutes"] = daily_limit_mins
									device_info["remaining_minutes"] = max(0, daily_limit_mins - used_mins)
									_LOGGER.debug(
										f"Device {device_id}: NO BONUS - "
										f"daily_limit={daily_limit_mins}, used={used_mins}, "
										f"remaining={device_info['remaining_minutes']}"
									)

						# Log final daily_limit values for this device
						_LOGGER.debug(
							f"Device {device_id}: daily_limit_enabled={device_info.get('daily_limit_enabled', False)}, "
							f"daily_limit_minutes={device_info.get('daily_limit_minutes', 0)}"
						)

						devices[device_id] = device_info
						_LOGGER.debug(f"Device {device_id} parsed: {device_info}")

				return {
					"device_lock_states": device_lock_states,
					"devices": devices
				}

		except Exception as err:
			_LOGGER.error("Failed to fetch applied time limits: %s", err)
			raise NetworkError(f"Failed to fetch applied time limits: {err}") from err

	async def async_add_time_bonus(
		self,
		bonus_minutes: int,
		device_id: str,
		account_id: str | None = None
	) -> bool:
		"""Add a time bonus to a device (e.g., 30 minutes extra screen time).

		Args:
			bonus_minutes: Number of minutes to add (e.g., 30 for 30 minutes)
			device_id: Device ID (device token)
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Convert minutes to seconds
			bonus_seconds = bonus_minutes * 60

			# Payload format: [null, account_id, [[null, null, 10, device_token, null, null, null, null, null, null, null, null, null, [[bonus_seconds, 0]]]], [1]]
			payload = json.dumps([
				None,
				account_id,
				[[None, None, 10, device_id, None, None, None, None, None, None, None, None, None, [[str(bonus_seconds), 0]]]],
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimitOverrides:batchCreate"
			_LOGGER.debug(f"Adding {bonus_minutes} minutes time bonus to device {device_id}")

			async with session.post(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to add time bonus {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully added {bonus_minutes} minutes time bonus to device {device_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error adding time bonus: {err}")
			return False

	async def async_cancel_time_bonus(
		self,
		override_id: str,
		account_id: str | None = None
	) -> bool:
		"""Cancel an active time bonus override.

		Args:
			override_id: The UUID of the time limit override to cancel
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Use POST with $httpMethod=DELETE query parameter (Google API convention)
			url = f"{self.BASE_URL}/people/{account_id}/timeLimitOverride/{override_id}?$httpMethod=DELETE"
			_LOGGER.debug(f"Cancelling time bonus override {override_id} for account {account_id}")

			async with session.post(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				}
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to cancel time bonus {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully cancelled time bonus override {override_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error cancelling time bonus: {err}")
			return False

	async def async_enable_bedtime(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Enable bedtime (downtime) restrictions for a child.

		Args:
			account_id: User ID of the supervised child (optional)
			rule_id: Bedtime rule UUID (optional, fetched dynamically if not provided)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		# Fetch rule_id dynamically if not provided
		if not rule_id:
			time_limit_data = await self.async_get_time_limit(account_id)
			rule_id = time_limit_data.get("bedtime_rule_id")
			if not rule_id:
				_LOGGER.error("Could not find bedtime rule ID for this account")
				return False

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Payload format: [null, account_id, [[null, null, null, null], null, null, null, [null, [[rule_id, 2]]]], null, [1]]
			# Status 2 = enabled
			payload = json.dumps([
				None,
				account_id,
				[[None, None, None, None], None, None, None, [None, [[rule_id, 2]]]],
				None,
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimit:update"
			_LOGGER.debug(f"Enabling bedtime for account {account_id} with rule_id {rule_id}")

			async with session.put(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload,
				params={"$httpMethod": "PUT"}
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to enable bedtime {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully enabled bedtime for account {account_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error enabling bedtime: {err}")
			return False

	async def async_disable_bedtime(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Disable bedtime (downtime) restrictions for a child.

		Args:
			account_id: User ID of the supervised child (optional)
			rule_id: Bedtime rule UUID (optional, fetched dynamically if not provided)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		# Fetch rule_id dynamically if not provided
		if not rule_id:
			time_limit_data = await self.async_get_time_limit(account_id)
			rule_id = time_limit_data.get("bedtime_rule_id")
			if not rule_id:
				_LOGGER.error("Could not find bedtime rule ID for this account")
				return False

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Payload format: [null, account_id, [[null, null, null, null], null, null, null, [null, [[rule_id, 1]]]], null, [1]]
			# Status 1 = disabled
			payload = json.dumps([
				None,
				account_id,
				[[None, None, None, None], None, None, None, [None, [[rule_id, 1]]]],
				None,
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimit:update"
			_LOGGER.debug(f"Disabling bedtime for account {account_id} with rule_id {rule_id}")

			async with session.put(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload,
				params={"$httpMethod": "PUT"}
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to disable bedtime {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully disabled bedtime for account {account_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error disabling bedtime: {err}")
			return False

	async def async_enable_school_time(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Enable school time (evening limit) restrictions for a child.

		Args:
			account_id: User ID of the supervised child (optional)
			rule_id: School time rule UUID (optional, fetched dynamically if not provided)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		# Fetch rule_id dynamically if not provided
		if not rule_id:
			time_limit_data = await self.async_get_time_limit(account_id)
			rule_id = time_limit_data.get("schooltime_rule_id")
			if not rule_id:
				_LOGGER.error("Could not find school time rule ID for this account")
				return False

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Payload format: [null, account_id, [[null, null, null, null], null, null, null, [null, [[rule_id, 2]]]], null, [1]]
			# Status 2 = enabled
			payload = json.dumps([
				None,
				account_id,
				[[None, None, None, None], None, None, None, [None, [[rule_id, 2]]]],
				None,
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimit:update"
			_LOGGER.debug(f"Enabling school time for account {account_id} with rule_id {rule_id}")

			async with session.put(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload,
				params={"$httpMethod": "PUT"}
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to enable school time {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully enabled school time for account {account_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error enabling school time: {err}")
			return False

	async def async_disable_school_time(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Disable school time (evening limit) restrictions for a child.

		Args:
			account_id: User ID of the supervised child (optional)
			rule_id: School time rule UUID (optional, fetched dynamically if not provided)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		# Fetch rule_id dynamically if not provided
		if not rule_id:
			time_limit_data = await self.async_get_time_limit(account_id)
			rule_id = time_limit_data.get("schooltime_rule_id")
			if not rule_id:
				_LOGGER.error("Could not find school time rule ID for this account")
				return False

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Payload format: [null, account_id, [[null, null, null, null], null, null, null, [null, [[rule_id, 1]]]], null, [1]]
			# Status 1 = disabled
			payload = json.dumps([
				None,
				account_id,
				[[None, None, None, None], None, None, None, [None, [[rule_id, 1]]]],
				None,
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimit:update"
			_LOGGER.debug(f"Disabling school time for account {account_id} with rule_id {rule_id}")

			async with session.put(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload,
				params={"$httpMethod": "PUT"}
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to disable school time {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully disabled school time for account {account_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error disabling school time: {err}")
			return False

	async def async_enable_daily_limit(self, account_id: str | None = None) -> bool:
		"""Enable daily time limit for a child.

		Args:
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Payload format: [null, account_id, [null, [[2, null, null, null]]], null, [1]]
			# Status 2 = enabled
			payload = json.dumps([
				None,
				account_id,
				[None, [[2, None, None, None]]],
				None,
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimit:update"
			_LOGGER.debug(f"Enabling daily limit for account {account_id}")

			async with session.put(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload,
				params={"$httpMethod": "PUT"}
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to enable daily limit {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully enabled daily limit for account {account_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error enabling daily limit: {err}")
			return False

	async def async_disable_daily_limit(self, account_id: str | None = None) -> bool:
		"""Disable daily time limit for a child.

		Args:
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Payload format: [null, account_id, [null, [[1, null, null, null]]], null, [1]]
			# Status 1 = disabled
			payload = json.dumps([
				None,
				account_id,
				[None, [[1, None, None, None]]],
				None,
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimit:update"
			_LOGGER.debug(f"Disabling daily limit for account {account_id}")

			async with session.put(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload,
				params={"$httpMethod": "PUT"}
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to disable daily limit {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully disabled daily limit for account {account_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error disabling daily limit: {err}")
			return False

	async def async_set_daily_limit(
		self,
		daily_minutes: int,
		device_id: str,
		account_id: str | None = None
	) -> bool:
		"""Set daily time limit duration for a device.

		Args:
			daily_minutes: Number of minutes allowed per day (e.g., 120 for 2 hours)
			device_id: Device ID (device token)
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Get current day of week (1=Monday, 7=Sunday) and map to CAEQ code
			# The CAEQ suffix encodes the day: CAEQAQ=1, CAEQAg=2, CAEQAw=3, CAEQBA=4, CAEQBQ=5, CAEQBg=6, CAEQBw=7
			from datetime import datetime
			day_codes = {
				1: "CAEQAQ",  # Monday
				2: "CAEQAg",  # Tuesday
				3: "CAEQAw",  # Wednesday
				4: "CAEQBA",  # Thursday
				5: "CAEQBQ",  # Friday
				6: "CAEQBg",  # Saturday
				7: "CAEQBw",  # Sunday
			}
			current_day = datetime.now().isoweekday()
			day_code = day_codes[current_day]

			# Payload format: [null, account_id, [[null, null, 8, device_token, null, null, null, null, null, null, null, [2, daily_minutes, day_code]]], [1]]
			payload = json.dumps([
				None,
				account_id,
				[[None, None, 8, device_id, None, None, None, None, None, None, None, [2, daily_minutes, day_code]]],
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimitOverrides:batchCreate"
			_LOGGER.debug(f"Setting daily limit to {daily_minutes} minutes for device {device_id} (day={current_day}, code={day_code})")

			async with session.post(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to set daily limit {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully set daily limit to {daily_minutes} minutes for device {device_id}")
				return True

		except Exception as err:
			_LOGGER.error(f"Unexpected error setting daily limit: {err}")
			return False

	async def async_set_bedtime(
		self,
		start_time: str,
		end_time: str,
		day: int | None = None,
		account_id: str | None = None
	) -> bool:
		"""Set bedtime (downtime) schedule for a specific day.

		Args:
			start_time: Bedtime start time in HH:MM format (e.g., "20:45")
			end_time: Bedtime end time in HH:MM format (e.g., "07:30")
			day: Day of week (1=Monday, 7=Sunday). Defaults to today if not specified.
			account_id: User ID of the supervised child (optional)

		Returns:
			True if successful, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			# Parse start and end times
			start_parts = start_time.split(":")
			end_parts = end_time.split(":")
			start_hour, start_min = int(start_parts[0]), int(start_parts[1])
			end_hour, end_min = int(end_parts[0]), int(end_parts[1])

			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Day codes mapping
			day_codes = {
				1: "CAEQAQ",  # Monday
				2: "CAEQAg",  # Tuesday
				3: "CAEQAw",  # Wednesday
				4: "CAEQBA",  # Thursday
				5: "CAEQBQ",  # Friday
				6: "CAEQBg",  # Saturday
				7: "CAEQBw",  # Sunday
			}

			# Use provided day or default to today
			if day is None:
				day = datetime.now().isoweekday()

			if day not in day_codes:
				raise ValueError(f"Invalid day: {day}. Must be 1-7 (Monday-Sunday)")

			day_code = day_codes[day]

			# Payload format: [null, account_id, [[null,null,9,null,null,null,null,null,null,null,null,null,[2,[startH,startM],[endH,endM],dayCode]]], [1]]
			# Type 9 = bedtime override, Status 2 = enabled
			payload = json.dumps([
				None,
				account_id,
				[[None, None, 9, None, None, None, None, None, None, None, None, None, [2, [start_hour, start_min], [end_hour, end_min], day_code]]],
				[1]
			])

			url = f"{self.BASE_URL}/people/{account_id}/timeLimitOverrides:batchCreate"
			_LOGGER.debug(f"Setting bedtime {start_time}-{end_time} for day={day} (code={day_code})")

			async with session.post(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to set bedtime {response.status}: {response_text}")
					return False

				_LOGGER.info(f"Successfully set bedtime {start_time}-{end_time} for day {day}")
				return True

		except ValueError as err:
			_LOGGER.error(f"Invalid time format: {err}")
			return False
		except Exception as err:
			_LOGGER.error(f"Unexpected error setting bedtime: {err}")
			return False

	async def async_get_time_limit(self, account_id: str | None = None) -> dict[str, Any]:
		"""Get time limit rules and schedules (bedtime/schooltime).

		Args:
			account_id: User ID of the supervised child (optional)

		Returns:
			Dictionary with:
			- bedtime_enabled: Boolean
			- school_time_enabled: Boolean
			- bedtime_schedule: List of {day, start, end} dicts
			- school_time_schedule: List of {day, start, end} dicts
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if account_id is None:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			url = f"{self.BASE_URL}/people/{account_id}/timeLimit"
			params = [
				("capabilities", "TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME"),
				("timeLimitKey.type", "SUPERVISED_DEVICES")
			]

			_LOGGER.debug(f"Fetching time limit rules from {url}")

			async with session.get(
				url,
				params=params,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				}
			) as response:
				if response.status == 401:
					_LOGGER.error(f"✗ 401 Unauthorized - Session expired fetching time limit rules")
					raise SessionExpiredError("Session expired, please re-authenticate")
				if response.status != 200:
					response_text = await response.text()
					# Use warning for temporary errors (503), error for others
					log_method = _LOGGER.warning if response.status == 503 else _LOGGER.error
					log_method(f"Failed to fetch time limit rules (HTTP {response.status}): {response_text}")
					return {
						"bedtime_enabled": False,
						"school_time_enabled": False,
						"bedtime_schedule": [],
						"school_time_schedule": [],
						"bedtime_rule_id": None,
						"schooltime_rule_id": None
					}

				response_data = await response.json()
				_LOGGER.debug(f"Time limit rules response: {response_data}")

				# Unwrap the response: [[metadata], [real_data]] -> [real_data]
				if not isinstance(response_data, list) or len(response_data) < 2:
					_LOGGER.error(f"Unexpected response structure: {response_data}")
					return {
						"bedtime_enabled": False,
						"school_time_enabled": False,
						"bedtime_schedule": [],
						"school_time_schedule": [],
						"bedtime_rule_id": None,
						"schooltime_rule_id": None
					}

				data = response_data[1]  # Extract the real data array (index 1)
				_LOGGER.debug(f"Unwrapped data from response_data[1], type: {type(data)}, len: {len(data) if isinstance(data, list) else 'N/A'}")

				# Parse bedtime and schooltime schedules
				bedtime_schedule = []
				school_time_schedule = []

				# The response structure after unwrapping is:
				# data = [bedtime_config, daily_limit_config, history, None, [1], [current_states]]
				# Index 0: bedtime schedules
				# Index 1: daily limit + school time schedules
				# Index -1 (5): current states (revisions for bedtime/schooltime)

				# Extract bedtime schedules from index 0
				if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
					bedtime_config = data[0]
					# Format: [[2, [schedules], timestamp, timestamp, 1]]
					if len(bedtime_config) > 0 and isinstance(bedtime_config[0], list):
						schedule_data = bedtime_config[0]
						# schedules are in index 1
						if len(schedule_data) > 1 and isinstance(schedule_data[1], list):
							for schedule_list in schedule_data[1]:
								if isinstance(schedule_list, list):
									for item in schedule_list:
										if isinstance(item, list) and len(item) >= 4:
											if isinstance(item[0], str) and item[0].startswith("CAEQ"):
												day = item[1] if len(item) > 1 else None
												start = item[2] if len(item) > 2 else None
												end = item[3] if len(item) > 3 else None
												if day and start and end:
													bedtime_schedule.append({
														"day": day,
														"start": start,  # [hh, mm]
														"end": end  # [hh, mm]
													})

				# Extract school time schedules from index 1
				if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
					daily_limit_config = data[1]
					# Format: [[2, [6, 0], [schedules], timestamp, timestamp]]
					if len(daily_limit_config) > 0 and isinstance(daily_limit_config[0], list):
						config_data = daily_limit_config[0]

						# School time schedules are in index 2
						if len(config_data) > 2 and isinstance(config_data[2], list):
							for item in config_data[2]:
								if isinstance(item, list) and len(item) >= 4:
									if isinstance(item[0], str) and item[0].startswith("CAMQ"):
										day = item[1] if len(item) > 1 else None
										start = item[2] if len(item) > 2 else None
										end = item[3] if len(item) > 3 else None
										if day and start and end:
											school_time_schedule.append({
												"day": day,
												"start": start,
												"end": end
											})

				# Parse revisions to get ON/OFF state and rule IDs
				# Revisions are in the last element of data, containing items with format:
				# ["uuid", type_flag, state_flag, [timestamp, nanos]]
				# type_flag: 1=bedtime, 2=schooltime
				# state_flag: 2=ON, 1=OFF
				# NOTE: Revisions have EXACTLY 4 elements (schedules have 7+)
				bedtime_enabled = False
				school_time_enabled = False
				bedtime_rule_id = None
				schooltime_rule_id = None

				# Look for revisions in the last element of data
				revisions_found = False
				if isinstance(data, list) and len(data) > 0:
					_LOGGER.debug(f"[REVISION DEBUG] Data array has {len(data)} elements")
					# Search backwards from the end to find revision list
					for idx in range(len(data) - 1, -1, -1):
						element = data[idx]
						_LOGGER.debug(f"[REVISION DEBUG] Checking data[{idx}], type={type(element)}, is_list={isinstance(element, list)}")
						if not isinstance(element, list):
							continue

						_LOGGER.debug(f"[REVISION DEBUG] data[{idx}] is a list with {len(element)} items")

						# Filter to only revision items (exactly 4 elements with timestamp list at end)
						# This excludes schedule items which have 7+ elements
						revision_candidates = [
							item for item in element
							if isinstance(item, list) and len(item) == 4 and isinstance(item[3], list)
						]

						_LOGGER.debug(f"[REVISION DEBUG] Found {len(revision_candidates)} candidates at index {idx}")
						if len(revision_candidates) > 0:
							_LOGGER.debug(f"[REVISION DEBUG] Candidates: {revision_candidates}")

						# Check if these look like valid revisions
						if len(revision_candidates) > 0:
							valid_revisions = [
								item for item in revision_candidates
								if (isinstance(item[0], str) and len(item[0]) > 30 and  # UUID
								    isinstance(item[1], int) and item[1] in [1, 2] and  # type_flag
								    isinstance(item[2], int) and item[2] in [1, 2])  # state_flag
							]

							_LOGGER.debug(f"[REVISION DEBUG] {len(valid_revisions)} valid revisions after validation")
							if len(valid_revisions) > 0:
								_LOGGER.debug(f"Found {len(valid_revisions)} revision entries at index {idx}")
								for revision in valid_revisions:
									rule_id = revision[0]
									type_flag = revision[1]
									state_flag = revision[2]

									if type_flag == 1:  # downtime/bedtime
										bedtime_enabled = (state_flag == 2)
										bedtime_rule_id = rule_id
										_LOGGER.debug(f"Found bedtime revision: rule_id={rule_id}, type={type_flag}, state={state_flag}, enabled={bedtime_enabled}")
										revisions_found = True
									elif type_flag == 2:  # schooltime
										school_time_enabled = (state_flag == 2)
										schooltime_rule_id = rule_id
										_LOGGER.debug(f"Found schooltime revision: rule_id={rule_id}, type={type_flag}, state={state_flag}, enabled={school_time_enabled}")
										revisions_found = True
								break

				if not revisions_found:
					_LOGGER.warning("No revision data found in response")

				_LOGGER.info(
					f"Time limit rules: bedtime_enabled={bedtime_enabled} (rule_id={bedtime_rule_id}, {len(bedtime_schedule)} schedules), "
					f"school_time_enabled={school_time_enabled} (rule_id={schooltime_rule_id}, {len(school_time_schedule)} schedules)"
				)

				return {
					"bedtime_enabled": bedtime_enabled,
					"school_time_enabled": school_time_enabled,
					"bedtime_schedule": bedtime_schedule,
					"school_time_schedule": school_time_schedule,
					"bedtime_rule_id": bedtime_rule_id,
					"schooltime_rule_id": schooltime_rule_id
				}

		except Exception as err:
			_LOGGER.error("Failed to fetch time limit rules: %s", err)
			raise NetworkError(f"Failed to fetch time limit rules: {err}") from err

	async def async_cleanup(self) -> None:
		"""Clean up client resources."""
		if self._session:
			await self._session.close()
			self._session = None 