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
	FAMILYLINK_BASE_URL,
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
		self.addon_client = AddonCookieClient(hass)
		self._session: aiohttp.ClientSession | None = None
		self._cookies: list[dict[str, Any]] | None = None
		self._account_id: str | None = None  # Cached supervised child ID

	async def async_authenticate(self) -> None:
		"""Authenticate with Family Link."""
		# Load cookies from add-on
		_LOGGER.debug("Loading cookies from Family Link Auth add-on")

		if not self.addon_client.cookies_available():
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
						if ".google.com" in cookie_domain:
							sapisid = cookie.get("value", "").strip('"')
							_LOGGER.debug(f"✓ Found SAPISID cookie with domain: {cookie_domain}")
							_LOGGER.debug(f"SAPISID value (first 10 chars): {sapisid[:10]}...")
						else:
							_LOGGER.warning(f"Found SAPISID but wrong domain: {cookie_domain} (expected .google.com)")

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
				_LOGGER.warning(f"No app usage data found for {target_date.date()}")
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

		except Exception as err:
			_LOGGER.error("Failed to fetch daily screen time: %s", err)
			raise NetworkError(f"Failed to fetch daily screen time: {err}") from err

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

	async def async_control_device(self, device_id: str, action: str) -> bool:
		"""Control a Family Link device (lock/unlock).

		Uses the timeLimitOverrides:batchCreate endpoint discovered from browser DevTools.

		Args:
			device_id: Device ID to control
			action: "lock" or "unlock"

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
			account_id = await self.async_get_supervised_child_id()

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

	async def async_get_applied_time_limits(self, account_id: str | None = None) -> dict[str, bool]:
		"""Get applied time limits to determine device lock states.

		Args:
			account_id: User ID of the supervised child (optional)

		Returns:
			Dictionary mapping device_id to locked state (True = locked, False = unlocked)
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
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"Failed to fetch applied time limits {response.status}: {response_text}")
					return {}

				data = await response.json()
				_LOGGER.debug(f"Applied time limits response: {data}")

				# Parse lock states from response
				# Response format: [[null, timestamp], [device_arrays]]
				device_lock_states = {}

				if len(data) > 1 and isinstance(data[1], list):
					for device_data in data[1]:
						if not isinstance(device_data, list) or len(device_data) < 25:
							continue

						# Get device ID from the data
						# When unlocked: [0] contains an array with device_id at [3]
						# When locked: [0] is null
						device_id = None

						# Try to find device_id
						if device_data[0] and isinstance(device_data[0], list) and len(device_data[0]) > 3:
							# Found in unlock override
							device_id = device_data[0][3]
						elif len(device_data) > 25 and device_data[25]:
							# Found at index 25 (device_id field always present)
							device_id = device_data[25]

						if device_id:
							# Determine lock state by checking for active time limit override:
							# When LOCKED: device_data[0] contains the lock override [null, null, action_code, device_id]
							# When UNLOCKED: device_data[0] is null (no active override)
							has_lock_override = device_data[0] is not None and isinstance(device_data[0], list)

							# Additional check: action code at [0][2]
							# Code 1 = LOCK, Code 4 = UNLOCK
							# If there's an override, check if it's a lock (1) or unlock (4)
							if has_lock_override and len(device_data[0]) > 2:
								action_code = device_data[0][2]
								is_locked = (action_code == 1)  # 1 = lock, 4 = unlock
							else:
								# No override means unlocked (normal state)
								is_locked = False

							device_lock_states[device_id] = is_locked
							_LOGGER.debug(
								f"Device {device_id}: locked={is_locked}, "
								f"has_override={has_lock_override}, "
								f"action_code={device_data[0][2] if has_lock_override and len(device_data[0]) > 2 else None}"
							)

				return device_lock_states

		except Exception as err:
			_LOGGER.error("Failed to fetch applied time limits: %s", err)
			raise NetworkError(f"Failed to fetch applied time limits: {err}") from err

	async def async_cleanup(self) -> None:
		"""Clean up client resources."""
		if self._session:
			await self._session.close()
			self._session = None 