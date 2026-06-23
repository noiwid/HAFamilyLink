"""API client for Google Family Link integration."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..auth.addon_client import AddonCookieClient
from ..const import (
	CONF_SCHEDULE_TIMEZONE,
	DEVICE_LOCK_ACTION,
	DEVICE_RING_ACTION_CODE,
	DEVICE_UNLOCK_ACTION,
	LOGGER_NAME,
)
from ..exceptions import (
	AuthenticationError,
	DeviceControlError,
	NetworkError,
	ScheduleUpdatePartialError,
	SessionExpiredError,
)
from ..schedules import (
	DAY_CODES,
	build_bedtime_day_enabled_update_payload,
	build_bedtime_schedule_update_payload,
	build_daily_limit_day_enabled_update_payload,
	build_daily_limit_schedule_update_payload,
	find_device_time_zone_name,
	get_time_zone,
	parse_daily_limit_schedule,
	parse_window_schedule_items,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class FamilyLinkClient:
	"""Client for interacting with Google Family Link API."""

	# Google Family Link API endpoints (reverse-engineered)
	BASE_URL = "https://kidsmanagement-pa.clients6.google.com/kidsmanagement/v1"
	ORIGIN = "https://familylink.google.com"
	API_KEY = "AIzaSyAQb1gupaJhY3CXQy2xmTwJMcjmot3M2hw"

	# Maximum session age before recreating (seconds)
	# SAPISIDHASH timestamp must stay fresh for Google API authentication
	SESSION_MAX_AGE = 1800  # 30 minutes

	def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
		"""Initialize the Family Link client."""
		self.hass = hass
		self.config = config
		# Get auth_url from config if available (for Docker standalone mode)
		auth_url = config.get("auth_url")
		self.addon_client = AddonCookieClient(hass, auth_url=auth_url)
		self._session: aiohttp.ClientSession | None = None
		self._session_lock = asyncio.Lock()
		self._session_created_at: float = 0  # Track session age for SAPISIDHASH refresh
		self._cookies: list[dict[str, Any]] | None = None
		self._account_id: str | None = None  # Cached supervised child ID
		self._configured_schedule_timezone = (
			config.get(CONF_SCHEDULE_TIMEZONE, "") or ""
		).strip()
		self._google_schedule_timezones: dict[str, str] = {}
		self._google_schedule_timezone_checked: set[str] = set()

	def update_google_schedule_timezone(self, account_id: str, devices_payload: Any) -> None:
		"""Cache the schedule timezone from the known Google devices payload."""
		if self._configured_schedule_timezone:
			return
		timezone = find_device_time_zone_name(devices_payload)
		if timezone:
			self._google_schedule_timezones[account_id] = timezone
			_LOGGER.debug("Using Google device timezone for %s: %s", account_id, timezone)

	def _schedule_time_zone_context(self, account_id: str | None = None) -> tuple[Any | None, str | None, str]:
		"""Return the effective timezone, name, and source for schedule dates."""
		configured = get_time_zone(self._configured_schedule_timezone)
		if configured:
			return configured, self._configured_schedule_timezone, "config"

		if self._configured_schedule_timezone:
			_LOGGER.warning(
				"Ignoring invalid configured schedule timezone: %s",
				self._configured_schedule_timezone,
			)

		google_timezone = (
			self._google_schedule_timezones.get(account_id)
			if account_id
			else None
		)
		if google_timezone is None and len(self._google_schedule_timezones) == 1:
			google_timezone = next(iter(self._google_schedule_timezones.values()))

		google = get_time_zone(google_timezone)
		if google:
			return google, google_timezone, "google"

		home_assistant_timezone = getattr(self.hass.config, "time_zone", None)
		return get_time_zone(home_assistant_timezone), home_assistant_timezone, "home_assistant"

	def schedule_today(self, account_id: str | None = None) -> int:
		"""Return today's ISO weekday in the effective schedule timezone."""
		time_zone, _, _ = self._schedule_time_zone_context(account_id)
		return dt_util.now(time_zone).isoweekday() if time_zone else dt_util.now().isoweekday()

	@staticmethod
	def _validate_id(value: str, name: str = "ID") -> str:
		"""Validate that an ID is safe for URL interpolation."""
		if not value or not re.match(r'^[a-zA-Z0-9_\-]+$', value):
			raise ValueError(f"Invalid {name}: contains disallowed characters")
		return value

	def _people_url(self, account_id: str, suffix: str) -> str:
		"""Build a /people/{account_id}/... URL with a validated account ID."""
		self._validate_id(account_id, "account_id")
		return f"{self.BASE_URL}/people/{account_id}/{suffix}"

	async def async_authenticate(self) -> None:
		"""Authenticate with Family Link."""
		# Load cookies from add-on (single round-trip; load_cookies already
		# tries API then file fallback)
		_LOGGER.debug("Loading cookies from Family Link Auth add-on")

		self._cookies = await self.addon_client.load_cookies()

		if not self._cookies:
			if getattr(self.addon_client, "last_fetch_status", None) == 403:
				raise AuthenticationError(
					"Auth server rejected the request (403): the cookie endpoint "
					"requires an API key. Append ?api_key=<key> to the configured "
					"auth URL. The key is in the auth container's data directory "
					"(./data/api_key), or set it via the API_KEY environment variable."
				)
			raise AuthenticationError(
				"No cookies found. Please use the Family Link Auth add-on to authenticate first."
			)

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

		When multiple cookies have the same name from different domains,
		we prioritize .google.com over regional TLDs like .google.com.au
		"""
		if not hasattr(self, '_cookie_dict'):
			self._cookie_dict = {}
			cookie_domains = {}  # Track which domain each cookie came from

			if self._cookies:
				for cookie in self._cookies:
					cookie_name = cookie.get("name", "")
					cookie_value = cookie.get("value", "")
					cookie_domain = cookie.get("domain", "").lower().lstrip(".")

					if cookie_name and cookie_value:
						# Strip quotes from cookie values (Playwright may add them)
						cookie_value = cookie_value.strip('"')

						# Check if we already have this cookie from a different domain
						if cookie_name in self._cookie_dict:
							existing_domain = cookie_domains.get(cookie_name, "")

							# Priority: google.com > other domains > regional TLDs
							def domain_priority(d):
								if d == "google.com":
									return 0
								elif d.startswith("google.com.") or d.startswith("google.co."):
									return 2  # Regional TLDs
								else:
									return 1

							# Only replace if new domain has higher priority (lower value)
							if domain_priority(cookie_domain) < domain_priority(existing_domain):
								_LOGGER.debug(
									f"Cookie '{cookie_name}': replacing {existing_domain} with {cookie_domain} (higher priority)"
								)
								self._cookie_dict[cookie_name] = cookie_value
								cookie_domains[cookie_name] = cookie_domain
							else:
								_LOGGER.debug(
									f"Cookie '{cookie_name}': keeping {existing_domain} over {cookie_domain}"
								)
						else:
							self._cookie_dict[cookie_name] = cookie_value
							cookie_domains[cookie_name] = cookie_domain

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
		try:
			await asyncio.wait_for(self._session_lock.acquire(), timeout=60)
		except asyncio.TimeoutError:
			_LOGGER.error("Timed out waiting for session lock (60s) — possible deadlock")
			raise
		try:
			# Recreate session if SAPISIDHASH timestamp is too old
			if self._session is not None and (time.time() - self._session_created_at) > self.SESSION_MAX_AGE:
				_LOGGER.debug("Session SAPISIDHASH is stale (>%ds), recreating session", self.SESSION_MAX_AGE)
				await self._session.close()
				self._session = None

			if self._session is None:
				# Extract SAPISID cookie for authentication
				sapisid = None
				sapisid_domain = None

				_LOGGER.debug("Creating new session with authentication")

				if self._cookies:
					_LOGGER.debug(f"Processing {len(self._cookies)} cookies for SAPISID")

					# Collect all SAPISID cookies and prioritize .google.com over regional domains
					sapisid_candidates = []

					for cookie in self._cookies:
						cookie_name = cookie.get("name", "")
						cookie_domain = cookie.get("domain", "")

						if cookie_name == "SAPISID":
							domain_lower = cookie_domain.lower().lstrip(".")
							if domain_lower.startswith("google.") or ".google." in domain_lower:
								cookie_value = cookie.get("value", "").strip('"')
								sapisid_candidates.append({
									"value": cookie_value,
									"domain": cookie_domain,
									"domain_lower": domain_lower
								})
								_LOGGER.debug(f"✓ Found SAPISID cookie with domain: {cookie_domain}")
							else:
								_LOGGER.warning(f"Found SAPISID but wrong domain: {cookie_domain} (expected google.* domain)")

					if sapisid_candidates:
						def domain_priority(candidate):
							d = candidate["domain_lower"]
							if d == "google.com":
								return 0
							elif d.startswith("google.com.") or d.startswith("google.co."):
								return 2
							else:
								return 1

						sapisid_candidates.sort(key=domain_priority)
						best_candidate = sapisid_candidates[0]
						sapisid = best_candidate["value"]
						sapisid_domain = best_candidate["domain"]

						if len(sapisid_candidates) > 1:
							_LOGGER.info(
								f"Found {len(sapisid_candidates)} SAPISID cookies, "
								f"using {sapisid_domain} (prioritized over regional domains)"
							)
						_LOGGER.debug(f"Selected SAPISID from domain: {sapisid_domain}")
						_LOGGER.debug("SAPISID cookie found")

				if not sapisid:
					_LOGGER.error("✗ SAPISID cookie not found in authentication data")
					raise AuthenticationError("SAPISID cookie not found in authentication data")

				sapisidhash = self._generate_sapisidhash(sapisid, self.ORIGIN)
				_LOGGER.debug("Generated SAPISIDHASH for session")

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

				_LOGGER.debug(f"Session headers: Origin={self.ORIGIN}")

				self._session = aiohttp.ClientSession(
					headers=headers,
					timeout=aiohttp.ClientTimeout(total=30),
				)
				self._session_created_at = time.time()
				_LOGGER.debug("✓ Session created successfully")

			return self._session
		finally:
			self._session_lock.release()

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

	async def async_get_all_supervised_children(self) -> list[dict[str, str]]:
		"""Get all supervised children in the family.

		Returns:
			List of dictionaries with 'id' and 'name' for each supervised child.

		Raises:
			ValueError: If no supervised children are found.
		"""
		members_data = await self.async_get_family_members()
		children = []

		for member in members_data.get("members", []):
			supervision_info = member.get("memberSupervisionInfo")
			if supervision_info and supervision_info.get("isSupervisedMember"):
				child_id = member["userId"]
				child_name = member.get("profile", {}).get("displayName", "Unknown")
				children.append({"id": child_id, "name": child_name})
				_LOGGER.debug(f"Found supervised child: {child_name} (ID: {child_id})")

		if not children:
			raise ValueError("No supervised children found in family")

		_LOGGER.info(f"Found {len(children)} supervised children")
		return children

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

			url = self._people_url(account_id, "appsandusage")
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
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(f"API Error {response.status}: {response_text}")
					_LOGGER.error(f"Request URL was: {url}")

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

	async def async_get_devices_payload(self, account_id: str | None = None) -> Any:
		"""Get the raw devices payload used for device timezone discovery."""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()
			url = self._people_url(account_id, "devices")

			_LOGGER.debug("Fetching devices payload from %s", url)

			async with session.get(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header,
				},
				params={"includeUnmanagedDevices": "true"},
			) as response:
				if response.status == 401:
					_LOGGER.error("✗ 401 Unauthorized - Session expired fetching devices")
					raise SessionExpiredError("Session expired, please re-authenticate")
				if response.status != 200:
					response_text = await response.text()
					raise NetworkError(
						f"Failed to fetch devices: HTTP {response.status}: {response_text}"
					)

				return await response.json()

		except SessionExpiredError:
			raise
		except NetworkError:
			raise
		except Exception as err:
			_LOGGER.error("Unexpected error fetching devices: %s", err)
			raise NetworkError(f"Failed to fetch devices: {err}") from err

	async def async_update_google_schedule_timezone_from_devices(self, account_id: str) -> None:
		"""Best-effort cache of the Google device timezone for one child."""
		if (
			self._configured_schedule_timezone
			or account_id in self._google_schedule_timezones
			or account_id in self._google_schedule_timezone_checked
		):
			return

		try:
			devices_payload = await self.async_get_devices_payload(account_id)
		except Exception as err:
			self._google_schedule_timezone_checked.add(account_id)
			_LOGGER.debug(
				"Could not fetch Google device timezone for %s; using fallback timezone: %s",
				account_id,
				err,
			)
			return

		self._google_schedule_timezone_checked.add(account_id)
		self.update_google_schedule_timezone(account_id, devices_payload)

	async def async_get_daily_screen_time(
		self,
		account_id: str | None = None,
		target_date: datetime | None = None,
		data: dict[str, Any] | None = None,
	) -> dict[str, Any]:
		"""Get total screen time for a specific date.

		Args:
			account_id: User ID of the supervised child (optional)
			target_date: Date to get screen time for (defaults to today)
			data: Already-fetched apps and usage data (optional). When provided,
				avoids an extra call to the appsandusage endpoint.

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
			target_date = dt_util.now()

		try:
			if data is None:
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
					try:
						usage_seconds = float(usage_str.rstrip("s"))
					except (ValueError, TypeError):
						_LOGGER.debug("Invalid usage format: %s", usage_str)
						usage_seconds = 0
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

			self._validate_id(account_id, "account_id")
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

				# Extract battery info (index 8) - format: [battery_level, battery_state]
				battery_level = None
				if len(location_array) > 8 and isinstance(location_array[8], list):
					battery_info = location_array[8]
					if len(battery_info) > 0 and battery_info[0] is not None:
						try:
							battery_level = int(battery_info[0])
						except (ValueError, TypeError):
							_LOGGER.debug("Invalid battery value: %s", battery_info[0])
					# Note: battery_info[1] may contain charging state but not confirmed yet

				# Convert timestamp to ISO format
				timestamp_iso = None
				if timestamp_ms:
					try:
						timestamp_iso = datetime.fromtimestamp(timestamp_ms / 1000).isoformat()
					except (ValueError, OSError) as e:
						_LOGGER.debug("Invalid location timestamp %s: %s", timestamp_ms, e)

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
					"battery_level": battery_level,
				}

				_LOGGER.debug(
					f"Location for child {account_id}: "
					f"({latitude}, {longitude}) accuracy={accuracy}m, "
					f"place={place_name or 'unknown'}, device={source_device_id}, "
					f"battery={battery_level}%"
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
				self._people_url(account_id, "apps:updateRestrictions"),
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
				self._people_url(account_id, "apps:updateRestrictions"),
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

	async def async_set_app_daily_limit(
		self,
		package_name: str,
		minutes: int,
		account_id: str | None = None
	) -> bool:
		"""Set a daily time limit for a specific app.

		Args:
			package_name: Android package name (e.g., com.zhiliaoapp.musically)
			minutes: Daily limit in minutes (e.g., 60 for 1 hour). Use -1 to remove the limit entirely.
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

			if minutes == -2:
				# Unlimited time: [account_id, [[[package_name], null, null, [1]]]]
				# App ignores device daily limits entirely
				payload = json.dumps([account_id, [[[package_name], None, None, [1]]]])
				_LOGGER.debug(f"Setting app to unlimited time: {package_name}")
			elif minutes >= 0:
				# Set limit: [account_id, [[[package_name], null, [minutes, 1]]]]
				# Note: minutes=0 means 0 minutes allowed (app completely blocked for today)
				payload = json.dumps([account_id, [[[package_name], None, [minutes, 1]]]])
				_LOGGER.debug(f"Setting app daily limit: {package_name} = {minutes} minutes")
			else:
				# Remove limit entirely (minutes == -1): [account_id, [[[package_name]]]]
				# This disables the per-app limit (app follows device limits)
				payload = json.dumps([account_id, [[[package_name]]]])
				_LOGGER.debug(f"Removing app daily limit: {package_name}")

			async with session.post(
				self._people_url(account_id, "apps:updateRestrictions"),
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header
				},
				data=payload
			) as response:
				response.raise_for_status()
				if minutes == -2:
					_LOGGER.info(f"Successfully set app to unlimited time: {package_name}")
				elif minutes >= 0:
					_LOGGER.info(f"Successfully set app daily limit: {package_name} = {minutes} minutes")
				else:
					_LOGGER.info(f"Successfully removed app daily limit: {package_name}")
				return True

		except aiohttp.ClientResponseError as err:
			if err.status == 401:
				raise SessionExpiredError("Session expired, please re-authenticate") from err
			_LOGGER.error(f"Failed to set app daily limit for {package_name}: {err}")
			return False
		except Exception as err:
			_LOGGER.error(f"Unexpected error setting app daily limit for {package_name}: {err}")
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
		unblocked = []

		# Convert whitelist to a set for faster lookups
		whitelist_set = set(whitelist)

		for app in all_apps:
			package_name = app.get("packageName", "")
			is_blocked = app.get("supervisionSetting", {}).get("hidden", False)

			if package_name in whitelist_set:
				# Unblock whitelisted apps that are currently blocked
				if is_blocked:
					_LOGGER.debug(f"Unblocking whitelisted app: {package_name}")
					success = await self.async_unblock_app(package_name, account_id)
					if success:
						unblocked.append({
							"name": app.get("title", "Unknown"),
							"package": package_name
						})
					else:
						failed.append(package_name)
					await asyncio.sleep(0.1)
				else:
					_LOGGER.debug(f"Skipping whitelisted app (already allowed): {package_name}")
				continue

			# Skip if already blocked
			if is_blocked:
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
			f"School mode activated: {len(blocked)} apps blocked, {len(unblocked)} unblocked, "
			f"{len(failed)} failed, {len(whitelist)} apps whitelisted"
		)

		return {
			"blocked_count": len(blocked),
			"blocked_apps": blocked,
			"unblocked_count": len(unblocked),
			"unblocked_apps": unblocked,
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

			url = self._people_url(account_id, "timeLimitOverrides:batchCreate")
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

	async def async_ring_device(self, device_id: str, child_id: str | None = None) -> bool:
		"""Ring a Family Link device (make it sound to help locate it).

		Uses the devices/{device_id}:executeRemoteAction endpoint with action
		code 2 (ring), discovered from the Family Link web UI.

		Args:
			device_id: Device ID to ring
			child_id: Child's user ID (optional, defaults to first supervised child)

		Returns:
			True if the ring command was accepted, False otherwise
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		self._validate_id(device_id, "device_id")

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Get supervised child account ID
			if child_id is None:
				account_id = await self.async_get_supervised_child_id()
			else:
				account_id = child_id

			# Payload format from the web UI:
			# [null, account_id, device_id, [<action_code>, null, device_id, 0]]
			payload = json.dumps([
				None,
				account_id,
				device_id,
				[DEVICE_RING_ACTION_CODE, None, device_id, 0],
			])

			url = self._people_url(account_id, f"devices/{device_id}:executeRemoteAction")
			_LOGGER.debug(f"Requesting device ring: POST {url}")
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
					_LOGGER.error(f"Device ring failed {response.status}: {response_text}")
					return False

				response_data = await response.json()
				_LOGGER.debug(f"Device ring response: {response_data}")
				_LOGGER.info(f"Successfully rang device {device_id}")
				return True

		except Exception as err:
			_LOGGER.error("Failed to ring device %s: %s", device_id, err)
			raise DeviceControlError(f"Failed to ring device: {err}") from err

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
			- bedtime_enabled_today: True if any device has an enabled bedtime
				rule for the current weekday (combines weekly + daily overrides;
				used by the bedtime switch for issue #114).
			- schooltime_enabled_today: same for school time.
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if account_id is None:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			url = self._people_url(account_id, "appliedTimeLimits")
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
					raise NetworkError(f"Failed to fetch applied time limits: HTTP {response.status}")

				data = await response.json()
				_LOGGER.debug(f"Applied time limits response (first 500 chars): {str(data)[:500]}")

				device_lock_states = {}
				devices = {}
				# Today-effective flags computed from the per-device rule entries.
				# Used by the switches to reflect the actual locked/unlocked state on
				# the child device for today (issue #114) — combines weekly policy
				# with any daily override that's been applied. See doc note in
				# GOOGLE_FAMILY_LINK_API_ANALYSIS.md ("appliedTimeLimits effective
				# state for today").
				bedtime_enabled_today = False
				schooltime_enabled_today = False

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
							"bedtime_window_start": None,
							"bedtime_window_end": None,
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
						current_day = self.schedule_today(account_id)
						_LOGGER.debug(f"Device {device_id}: Current day of week: {current_day}")

						for idx, item in enumerate(device_data):
							if isinstance(item, list) and len(item) >= 4:
								_LOGGER.debug(f"Device {device_id}: item[{idx}] is list with {len(item)} elements, first element: {item[0]}")
								if isinstance(item[0], str):
									first_elem = item[0]
									is_caeq = first_elem.startswith("CAEQ")
									is_camq = first_elem.startswith("CAMQ")
									is_known_prefix = is_caeq or is_camq
									is_uuid = len(first_elem) == 36 and first_elem.count('-') == 4

									if is_uuid:
										_LOGGER.debug(
											f"Device {device_id}: UUID-format identifier detected at index {idx}: "
											f"{first_elem} (tuple length={len(item)})"
										)

									if is_known_prefix or is_uuid:
										if len(item) == 6:
											# Daily limit: ["CAEQ*"/UUID, day, stateFlag, minutes, createdMs, updatedMs]
											day = item[1] if len(item) > 1 else None
											state_flag = item[2] if len(item) > 2 else None
											minutes = item[3] if len(item) > 3 else None

											_LOGGER.debug(
												f"Device {device_id}: Found daily limit at index {idx}: "
												f"id={first_elem}, day={day}, state_flag={state_flag}, minutes={minutes}"
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
											# Time window (8 elements): could be bedtime or schooltime
											# For CAEQ prefix -> bedtime
											# For CAMQ prefix -> schooltime
											# For UUID -> determine by structure: if bedtime not yet set, parse as bedtime; otherwise schooltime
											day = item[1] if len(item) > 1 else None
											state_flag = item[2] if len(item) > 2 else None
											start_time = item[3] if len(item) > 3 else None
											end_time = item[4] if len(item) > 4 else None

											parse_as_bedtime = is_caeq or (is_uuid and device_info["bedtime_window"] is None)
											parse_as_schooltime = is_camq or (is_uuid and not parse_as_bedtime)

											if parse_as_bedtime:
												window_type = "bedtime"
											elif parse_as_schooltime:
												window_type = "schooltime"
											else:
												window_type = "unknown"

											_LOGGER.debug(
												f"Device {device_id}: {first_elem} is {window_type} window (8 elements) - "
												f"day={day}, state_flag={state_flag}, start={start_time}, end={end_time}"
											)

											# Parse time window if it's for current day and enabled
											if (isinstance(day, int) and day == current_day and
												isinstance(state_flag, int) and state_flag == 2 and
												isinstance(start_time, list) and len(start_time) == 2 and
												isinstance(end_time, list) and len(end_time) == 2):

												# Convert [HH, MM] to epoch milliseconds for today
												now = dt_util.now()
												start_hour, start_min = start_time[0], start_time[1]
												end_hour, end_min = end_time[0], end_time[1]

												# Create datetime objects for start and end
												start_dt = now.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
												end_dt = now.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)

												# If end time is before start time, it crosses midnight (e.g., 20:55 -> 10:00)
												if end_hour < start_hour or (end_hour == start_hour and end_min < start_min):
													window_active = (now >= start_dt) or (now < end_dt)
												else:
													window_active = (start_dt <= now < end_dt)

												window_data = {
													"start_ms": int(start_dt.timestamp() * 1000),
													"end_ms": int(end_dt.timestamp() * 1000)
												}
												window_start = f"{start_hour:02d}:{start_min:02d}"
												window_end = f"{end_hour:02d}:{end_min:02d}"

												if parse_as_bedtime:
													device_info["bedtime_window"] = window_data
													device_info["bedtime_window_start"] = window_start
													device_info["bedtime_window_end"] = window_end
													device_info["bedtime_active"] = window_active
													# An enabled bedtime rule exists for today on this
													# device — switch must show ON regardless of weekly
													# revision (issue #114).
													bedtime_enabled_today = True

													_LOGGER.debug(
														f"Device {device_id}: Bedtime window parsed - "
														f"start={window_start}, end={window_end}, "
														f"current_time={now.strftime('%H:%M')}, active={window_active}"
													)
												elif parse_as_schooltime:
													device_info["schooltime_window"] = window_data
													device_info["schooltime_active"] = window_active
													schooltime_enabled_today = True

													_LOGGER.debug(
														f"Device {device_id}: Schooltime window parsed - "
														f"start={start_hour:02d}:{start_min:02d}, end={end_hour:02d}:{end_min:02d}, "
														f"current_time={now.strftime('%H:%M')}, active={window_active}"
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
												bedtime_enabled_today = True
												_LOGGER.debug(f"Device {device_id}: bedtime window {start_ms}-{end_ms}")
											elif device_info["schooltime_window"] is None:
												device_info["schooltime_window"] = {"start_ms": start_ms, "end_ms": end_ms}
												device_info["schooltime_active"] = True
												schooltime_enabled_today = True
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
					"devices": devices,
					# Today-effective flags (issue #114): combine weekly policy
					# with daily overrides so the HA switches show what Google
					# actually applies on the child device right now, instead of
					# only the weekly revision.
					"bedtime_enabled_today": bedtime_enabled_today,
					"schooltime_enabled_today": schooltime_enabled_today,
				}

		except SessionExpiredError:
			raise
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

			url = self._people_url(account_id, "timeLimitOverrides:batchCreate")
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
			self._validate_id(override_id, "override_id")
			url = self._people_url(account_id, f"timeLimitOverride/{override_id}") + "?$httpMethod=DELETE"
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

	# Day-of-week → CAEQ day_code used by Google's batchCreate payloads
	# (bedtime overrides, daily limit overrides). ISO weekday: 1=Monday … 7=Sunday.
	_DAY_CODES = DAY_CODES

	async def async_enable_bedtime(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Enable bedtime, mirroring the Family Link web app (issue #113).

		Posts both calls the web app sends when the user toggles bedtime on
		and confirms "Apply changes to today as well?":

		1. `PUT timeLimit:update` flips the weekly revision to state 2.
		2. `POST timeLimitOverrides:batchCreate` posts a per-day override
		   (action=2) with today's weekly bedtime hours, so the change takes
		   effect on the child device for tonight without waiting for the
		   weekly slot to start fresh.

		Without step 2 the child device may not see the change until the
		next weekly slot — that's exactly what issue #113 reported.
		"""
		return await self._async_apply_bedtime_today(
			enable=True, account_id=account_id, rule_id=rule_id
		)

	async def async_disable_bedtime(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Disable bedtime, mirroring the Family Link web app (issue #113).

		Posts both calls the web app sends when the user toggles bedtime
		off and confirms "Apply changes to today as well?":

		1. `PUT timeLimit:update` flips the weekly revision to state 1.
		2. `POST timeLimitOverrides:batchCreate` posts a per-day override
		   (action=1) so the bedtime slot already running tonight is
		   actually suspended on the child device.
		"""
		return await self._async_apply_bedtime_today(
			enable=False, account_id=account_id, rule_id=rule_id
		)

	async def _async_apply_bedtime_today(
		self,
		enable: bool,
		account_id: str | None = None,
		rule_id: str | None = None,
	) -> bool:
		"""Flip the weekly bedtime policy AND post a per-day override.

		This combination is what the Family Link web app sends when the user
		toggles the bedtime weekly switch and confirms "Apply changes to
		today as well?". Doing only the weekly PUT (the previous behavior)
		left the child device unaffected on days where the weekly schedule
		and tonight's actual hours diverged — issue #113.
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		# Need the rule_id (always) AND today's bedtime hours (for the
		# override payload). Fetch both via one call to async_get_time_limit.
		time_limit_data = await self.async_get_time_limit(account_id)
		if not rule_id:
			rule_id = time_limit_data.get("bedtime_rule_id")
			if not rule_id:
				_LOGGER.error("Could not find bedtime rule ID for this account")
				return False

		# Pick the weekly bedtime slot matching today; fall back to a sane
		# default (21:30 → 07:00) if the user has no slot configured for
		# today — that way the override at least covers a reasonable window.
		weekday = self.schedule_today(account_id)
		day_code = self._DAY_CODES.get(weekday)
		if not day_code:
			_LOGGER.error("Unexpected weekday %s — cannot build bedtime override", weekday)
			return False

		bedtime_schedule = time_limit_data.get("bedtime_schedule") or []
		_LOGGER.debug(
			"Bedtime schedule has %d entries (looking for weekday %d): %s",
			len(bedtime_schedule), weekday, bedtime_schedule,
		)

		start, end = [21, 30], [7, 0]
		for slot in bedtime_schedule:
			if slot.get("day") == weekday:
				slot_start = slot.get("start")
				slot_end = slot.get("end")
				if isinstance(slot_start, list) and len(slot_start) == 2:
					start = slot_start
				if isinstance(slot_end, list) and len(slot_end) == 2:
					end = slot_end
				_LOGGER.debug("Using schedule slot for weekday %d: %s-%s", weekday, start, end)
				break
		else:
			_LOGGER.warning(
				"No bedtime schedule found for weekday %d, using default %s-%s",
				weekday, start, end,
			)

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Step 1: flip the weekly policy. The web app sends this even
			# when the user only wants "tonight" because the dialog choice
			# also persists the weekly state.
			weekly_state = 2 if enable else 1
			weekly_payload = json.dumps([
				None,
				account_id,
				[[None, None, None, None], None, None, None, [None, [[rule_id, weekly_state]]]],
				None,
				[1],
			])
			weekly_url = self._people_url(account_id, "timeLimit:update")
			async with session.put(
				weekly_url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header,
				},
				data=weekly_payload,
				params={"$httpMethod": "PUT"},
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(
						"Failed to update weekly bedtime policy (HTTP %s): %s",
						response.status, response_text,
					)
					return False

			# Step 2: post the per-day override. Bedtime overrides reference
			# the day via the opaque CAEQxx day_code (NOT a [weekday, uuid]
			# tuple like schooltime — see GOOGLE_FAMILY_LINK_API_ANALYSIS.md).
			action = 2 if enable else 1
			override_payload = json.dumps([
				None,
				account_id,
				[[
					None, None,
					9,
					None, None, None, None, None, None, None, None, None,
					[action, start, end, day_code],
				]],
				[1],
			])
			override_url = self._people_url(account_id, "timeLimitOverrides:batchCreate")
			_LOGGER.debug(
				"Applying bedtime override action=%s window=%s-%s day_code=%s rule=%s",
				action, start, end, day_code, rule_id,
			)
			async with session.post(
				override_url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header,
				},
				data=override_payload,
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(
						"Bedtime weekly policy was updated but the daily override failed "
						"(HTTP %s): %s — tonight may not reflect the change",
						response.status, response_text,
					)
					return False

			_LOGGER.info(
				"Successfully %s bedtime for account %s (weekly + tonight %02d:%02d-%02d:%02d)",
				"enabled" if enable else "disabled",
				account_id, start[0], start[1], end[0], end[1],
			)
			return True

		except Exception as err:
			_LOGGER.error("Unexpected error applying bedtime override: %s", err)
			return False

	async def async_enable_school_time(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Enable school time for the rest of the current day (issue #111).

		Creates a daily override (action=2) covering now → 23:59 for today's
		weekday, scoped to the school time rule. This is the same mechanism the
		official Family Link web app uses when the "Today" toggle is checked,
		and is what actually locks the child device immediately. The weekly
		policy is left untouched.
		"""
		return await self._async_apply_school_time_today(
			enable=True, account_id=account_id, rule_id=rule_id
		)

	async def async_disable_school_time(self, account_id: str | None = None, rule_id: str | None = None) -> bool:
		"""Disable school time for the rest of the current day (issue #111).

		Removes any existing schooltime override for today, then creates a
		daily override (action=1) covering now → 23:59. This matches the
		behavior of unchecking the "Today" toggle in the official web app and
		guarantees that an active school time slot is actually suspended on
		the child device.
		"""
		return await self._async_apply_school_time_today(
			enable=False, account_id=account_id, rule_id=rule_id
		)

	async def _async_apply_school_time_today(
		self,
		enable: bool,
		account_id: str | None = None,
		rule_id: str | None = None,
	) -> bool:
		"""Apply a school time daily override covering now → 23:59.

		Implements the override mechanism reverse-engineered from the official
		Family Link web app (issue #111). The previous implementation only
		toggled the weekly policy via `timeLimit:update`, which has no effect
		on days that lack a weekly slot or when toggling outside a slot — the
		web app always layers a daily override on top, and so do we now.
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		if not rule_id:
			time_limit_data = await self.async_get_time_limit(account_id)
			rule_id = time_limit_data.get("schooltime_rule_id")
			if not rule_id:
				_LOGGER.error("Could not find school time rule ID for this account")
				return False

		# Google uses ISO weekday numbering (1=Monday … 7=Sunday) in the user's
		# local time, since Family Link schedules are per-day.
		schedule_time_zone, _, _ = self._schedule_time_zone_context(account_id)
		now_local = dt_util.now(schedule_time_zone) if schedule_time_zone else dt_util.now()
		weekday = now_local.isoweekday()
		start = [now_local.hour, now_local.minute]
		# 23:59 is what the web app uses when extending to end of day; this
		# avoids midnight-rollover ambiguity.
		end = [23, 59]

		try:
			# When turning OFF, first remove any existing schooltime override
			# for today so we don't stack conflicting overrides on the same day.
			if not enable:
				overrides = await self._async_list_schooltime_overrides_today(
					account_id, rule_id, weekday
				)
				for override_uuid in overrides:
					await self._async_delete_time_limit_override(account_id, override_uuid)

			action = 2 if enable else 1
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			# Payload reverse-engineered from the web app capture. The "9" at
			# index 2 is the override type code for schooltime; the trailing
			# [weekday, rule_uuid] distinguishes schooltime overrides from
			# bedtime ones (which use a CAEQxx code string).
			payload = json.dumps([
				None,
				account_id,
				[[
					None, None,
					9,
					None, None, None, None, None, None, None, None, None,
					[action, start, end, None, [weekday, rule_id]],
				]],
				[1],
			])

			url = self._people_url(account_id, "timeLimitOverrides:batchCreate")
			_LOGGER.debug(
				"Applying school time override action=%s window=%s-%s weekday=%s rule=%s",
				action, start, end, weekday, rule_id,
			)

			async with session.post(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header,
				},
				data=payload,
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(
						"Failed to create school time override (HTTP %s): %s",
						response.status, response_text,
					)
					return False

				_LOGGER.info(
					"Successfully %s school time today for account %s (window %02d:%02d-23:59)",
					"enabled" if enable else "disabled",
					account_id, start[0], start[1],
				)
				return True

		except Exception as err:
			_LOGGER.error("Unexpected error applying school time override: %s", err)
			return False

	async def _async_list_schooltime_overrides_today(
		self, account_id: str, rule_id: str, weekday: int
	) -> list[str]:
		"""Return UUIDs of existing schooltime overrides for today.

		Reads the time limit endpoint and extracts override entries whose
		payload references the schooltime rule and the current weekday. Used
		before posting a new override to avoid stacking.
		"""
		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			url = self._people_url(account_id, "timeLimit")
			params = [
				("capabilities", "TIME_LIMIT_CLIENT_CAPABILITY_SCHOOLTIME"),
				("timeLimitKey.type", "SUPERVISED_DEVICES"),
			]

			async with session.get(
				url,
				params=params,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header,
				},
			) as response:
				if response.status != 200:
					_LOGGER.debug(
						"Could not fetch overrides (HTTP %s) — skipping cleanup",
						response.status,
					)
					return []
				data = await response.json()
		except Exception as err:
			_LOGGER.debug("Failed to list school time overrides: %s", err)
			return []

		# Unwrapped structure: data[1] holds the payload. Override entries
		# look like:
		# [uuid, ts, 9, "", "", null, null, null, account_id, null, null, null,
		#  [action, [start_h, m], [end_h, m], null, [weekday, rule_uuid]]]
		matches: list[str] = []
		if not isinstance(data, list) or len(data) < 2:
			return matches
		inner = data[1]
		if not isinstance(inner, list):
			return matches

		for element in inner:
			if not isinstance(element, list):
				continue
			for item in element:
				if not isinstance(item, list) or len(item) < 13:
					continue
				if not isinstance(item[0], str):
					continue
				payload = item[12]
				if not isinstance(payload, list) or len(payload) < 5:
					continue
				rule_ref = payload[4]
				if not isinstance(rule_ref, list) or len(rule_ref) < 2:
					continue
				if rule_ref[0] != weekday or rule_ref[1] != rule_id:
					continue
				matches.append(item[0])

		if matches:
			_LOGGER.debug(
				"Found %d existing schooltime override(s) for weekday=%s: %s",
				len(matches), weekday, matches,
			)
		return matches

	async def _async_delete_time_limit_override(self, account_id: str, override_uuid: str) -> bool:
		"""Delete a single timeLimitOverride by UUID."""
		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()
			self._validate_id(override_uuid, "override_uuid")
			url = self._people_url(account_id, f"timeLimitOverride/{override_uuid}")
			async with session.post(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header,
				},
				params={"$httpMethod": "DELETE"},
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.warning(
						"Failed to delete override %s (HTTP %s): %s",
						override_uuid, response.status, response_text,
					)
					return False
				_LOGGER.debug("Deleted school time override %s", override_uuid)
				return True
		except Exception as err:
			_LOGGER.warning("Error deleting override %s: %s", override_uuid, err)
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

			url = self._people_url(account_id, "timeLimit:update")
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

			url = self._people_url(account_id, "timeLimit:update")
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
			current_day = self.schedule_today(account_id)
			day_code = self._DAY_CODES[current_day]

			# Payload format: [null, account_id, [[null, null, 8, device_token, null, null, null, null, null, null, null, [2, daily_minutes, day_code]]], [1]]
			payload = json.dumps([
				None,
				account_id,
				[[None, None, 8, device_id, None, None, None, None, None, None, None, [2, daily_minutes, day_code]]],
				[1]
			])

			url = self._people_url(account_id, "timeLimitOverrides:batchCreate")
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

			# Use provided day or default to today
			if day is None:
				day = self.schedule_today(account_id)

			if day not in self._DAY_CODES:
				raise ValueError(f"Invalid day: {day}. Must be 1-7 (Monday-Sunday)")

			day_code = self._DAY_CODES[day]

			# Payload format: [null, account_id, [[null,null,9,null,null,null,null,null,null,null,null,null,[2,[startH,startM],[endH,endM],dayCode]]], [1]]
			# Type 9 = bedtime override, Status 2 = enabled
			payload = json.dumps([
				None,
				account_id,
				[[None, None, 9, None, None, None, None, None, None, None, None, None, [2, [start_hour, start_min], [end_hour, end_min], day_code]]],
				[1]
			])

			url = self._people_url(account_id, "timeLimitOverrides:batchCreate")
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

	async def _async_update_time_limit(
		self,
		account_id: str,
		payload: list[Any],
		description: str,
	) -> bool:
		"""Send a recurring timeLimit:update payload via PUT."""
		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()
			url = self._people_url(account_id, "timeLimit:update")

			async with session.put(
				url,
				headers={
					"Content-Type": "application/json+protobuf",
					"Cookie": cookie_header,
				},
				data=json.dumps(payload),
				params={"$httpMethod": "PUT"},
			) as response:
				if response.status != 200:
					response_text = await response.text()
					_LOGGER.error(
						"Failed to update %s (HTTP %s): %s",
						description, response.status, response_text,
					)
					return False

			_LOGGER.info("Successfully updated %s", description)
			return True

		except Exception as err:
			_LOGGER.error("Unexpected error updating %s: %s", description, err)
			return False

	def _raise_partial_schedule_update(
		self,
		successful_updates: list[str],
		failed_update: str,
	) -> None:
		"""Raise or log a failed schedule sub-write."""
		if successful_updates:
			raise ScheduleUpdatePartialError(successful_updates, failed_update)
		_LOGGER.error("Failed to update %s", failed_update)

	async def async_set_bedtime_schedule(
		self,
		day: int,
		start_time: str | None = None,
		end_time: str | None = None,
		enabled: bool | None = None,
		account_id: str | None = None,
	) -> bool:
		"""Update a recurring bedtime schedule day."""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		has_window = start_time is not None or end_time is not None
		if has_window and (start_time is None or end_time is None):
			_LOGGER.error("Both start_time and end_time are required to update a bedtime window")
			return False
		if not has_window and enabled is None:
			_LOGGER.error("Provide start_time/end_time, enabled, or both")
			return False

		try:
			successful_updates: list[str] = []
			if has_window:
				description = f"bedtime schedule for day {day}"
				payload = build_bedtime_schedule_update_payload(
					account_id, day, start_time, end_time
				)
				if not await self._async_update_time_limit(
					account_id, payload, description
				):
					self._raise_partial_schedule_update(successful_updates, description)
					return False
				successful_updates.append(description)

			if enabled is not None:
				description = f"bedtime schedule enabled state for day {day}"
				payload = build_bedtime_day_enabled_update_payload(account_id, day, enabled)
				if not await self._async_update_time_limit(
					account_id, payload, description
				):
					self._raise_partial_schedule_update(successful_updates, description)
					return False
				successful_updates.append(description)

			return True

		except ValueError as err:
			_LOGGER.error("Invalid bedtime schedule value: %s", err)
			return False

	async def async_set_daily_limit_schedule(
		self,
		day: int,
		daily_minutes: int | None = None,
		enabled: bool | None = None,
		account_id: str | None = None,
	) -> bool:
		"""Update a recurring daily limit schedule day."""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if not account_id:
			account_id = await self.async_get_supervised_child_id()

		if daily_minutes is None and enabled is None:
			_LOGGER.error("Provide daily_minutes, enabled, or both")
			return False

		try:
			successful_updates: list[str] = []
			if daily_minutes is not None:
				description = f"daily limit schedule for day {day}"
				payload = build_daily_limit_schedule_update_payload(
					account_id, day, daily_minutes
				)
				if not await self._async_update_time_limit(
					account_id, payload, description
				):
					self._raise_partial_schedule_update(successful_updates, description)
					return False
				successful_updates.append(description)

			if enabled is not None:
				description = f"daily limit schedule enabled state for day {day}"
				payload = build_daily_limit_day_enabled_update_payload(account_id, day, enabled)
				if not await self._async_update_time_limit(
					account_id, payload, description
				):
					self._raise_partial_schedule_update(successful_updates, description)
					return False
				successful_updates.append(description)

			return True

		except ValueError as err:
			_LOGGER.error("Invalid daily limit schedule value: %s", err)
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
			- daily_limit_schedule: List of {day, minutes} dicts
		"""
		if not self.is_authenticated():
			raise AuthenticationError("Not authenticated")

		if account_id is None:
			account_id = await self.async_get_supervised_child_id()

		try:
			session = await self._get_session()
			cookie_header = self._get_cookie_header()

			url = self._people_url(account_id, "timeLimit")
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
				if response.status == 403:
					_LOGGER.error(
						"Permission denied fetching time limit rules (HTTP 403). "
						"Try re-authenticating via the Family Link Auth add-on."
					)
				elif response.status != 200:
					response_text = await response.text()
					# Use warning for temporary errors (503), error for others
					log_method = _LOGGER.warning if response.status == 503 else _LOGGER.error
					log_method(f"Failed to fetch time limit rules (HTTP {response.status}): {response_text}")
				if response.status != 200:
					return {
						"bedtime_enabled": False,
						"school_time_enabled": False,
						"bedtime_enabled_today": None,
						"bedtime_schedule": [],
						"school_time_schedule": [],
						"daily_limit_schedule": [],
						"bedtime_rule_id": None,
						"schooltime_rule_id": None
					}

				response_data = await response.json()
				_LOGGER.debug(f"Time limit rules response: {response_data}")
				schedule_time_zone, schedule_timezone, schedule_timezone_source = (
					self._schedule_time_zone_context(account_id)
				)
				schedule_today = (
					dt_util.now(schedule_time_zone).isoweekday()
					if schedule_time_zone
					else dt_util.now().isoweekday()
				)

				# Unwrap the response: [[metadata], [real_data]] -> [real_data]
				if not isinstance(response_data, list) or len(response_data) < 2:
					_LOGGER.error(f"Unexpected response structure: {response_data}")
					return {
						"bedtime_enabled": False,
						"school_time_enabled": False,
						"bedtime_enabled_today": None,
						"bedtime_schedule": [],
						"school_time_schedule": [],
						"daily_limit_schedule": [],
						"bedtime_rule_id": None,
						"schooltime_rule_id": None
					}

				data = response_data[1]  # Extract the real data array (index 1)
				_LOGGER.debug(f"Unwrapped data from response_data[1], type: {type(data)}, len: {len(data) if isinstance(data, list) else 'N/A'}")

				# Parse bedtime and schooltime schedules
				bedtime_schedule = []
				school_time_schedule = []
				daily_limit_schedule = []

				# The response structure after unwrapping is:
				# data = [bedtime_config, daily_limit_config, history, None, [1], [current_states]]
				# Index 0: bedtime schedules
				# Index 1: daily limit + school time schedules
				# Index -1 (5): current states (revisions for bedtime/schooltime)

				# Extract bedtime AND school time schedules.
				#
				# Both live in the SAME flat list at data[0][1], distinguished by
				# the opaque code prefix on each item (CAEQ* = bedtime window,
				# CAMQ* = school time window). The real (live, un-anonymized)
				# response confirms data[0] is:
				#   [stateFlag, [ <flat list of schedule items> ], ts, ts, 1]
				# so data[0][0] is the INTEGER stateFlag (2=ON/1=OFF), NOT a
				# nested list. The previous code expected data[0][0] to be a list
				# and required `isinstance(data[0][0], list)`, which was always
				# False here — so neither schedule was ever parsed (issue #113).
				#
				# data[1] is the daily-limit-MINUTES config ([[2,[6,0],[...],..]]
				# where the inner items are [code, day, stateFlag, minutes, ...])
				# — it does NOT contain CAMQ school-time windows, so the old
				# school-time branch reading data[1][0][2] also found 0 schedules.
				#
				# Each schedule item: [code, day, stateFlag, [startH,startM],
				#                      [endH,endM], ts, ts, ruleId]
				# item[2] is stateFlag (2=ON, 1=OFF), NOT the start time.
				if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
					bedtime_config = data[0]
					# schedules are the flat list at index 1
					if len(bedtime_config) > 1 and isinstance(bedtime_config[1], list):
						bedtime_schedule = parse_window_schedule_items(bedtime_config[1], "CAEQ")
						school_time_schedule = parse_window_schedule_items(bedtime_config[1], "CAMQ")

				if isinstance(data, list) and len(data) > 1:
					daily_limit_schedule = parse_daily_limit_schedule(data[1])

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
					_LOGGER.debug("No revision data found in response")

				# Today-effective bedtime state (issue #113).
				#
				# The weekly revision above is NOT what's applied on the child
				# device when a "Only today" override has been posted. The web app
				# pairs every weekly toggle with a per-day type-9 override, and that
				# override is what actually arbitrates today. It lives in this same
				# timeLimit response as an item whose [2] == 9 and whose payload is
				# [action, [startH,startM], [endH,endM], "CAEQxx"] (action 2=ON,
				# 1=OFF; the trailing CAEQ* string is the day_code). This is exactly
				# the structure we POST in async_set_bedtime / the bedtime override
				# helpers — here we read it back so the switch reflects Google's
				# applied state instead of the weekly-only revision.
				#
				# Default to the weekly value; override only when an override for
				# TODAY's day_code is present.
				#
				# IMPORTANT: Google does NOT replace overrides keyed by day_code —
				# it APPENDS. The response can therefore carry several type-9
				# overrides for the same day with conflicting actions, in no
				# particular order (verified live: same CAEQBQ day with action 2,
				# 1, 1, 2 at increasing timestamps). The effective one is the
				# MOST RECENT, identified by the override's own timestamp at
				# item[1] (epoch ms string) — NOT the last in iteration order.
				# Picking by list position silently read a stale override and
				# made the switch ignore a fresh "Only today" toggle.
				bedtime_enabled_today = bedtime_enabled
				bedtime_today_source = "weekly"
				bedtime_today_override_action = None
				today_day_code = self._DAY_CODES.get(schedule_today)
				if today_day_code and isinstance(data, list):
					latest_ts = -1
					latest_action = None
					for element in data:
						if not isinstance(element, list):
							continue
						for item in element:
							# Bedtime override: [uuid, ts, 9, ..., [action,[h,m],[h,m],code]]
							if not (isinstance(item, list) and len(item) > 2 and item[2] == 9):
								continue
							override_payload = next(
								(
									p for p in item
									if isinstance(p, list) and len(p) == 4
									and isinstance(p[3], str) and p[3].startswith("CAEQ")
								),
								None,
							)
							if override_payload is None:
								continue
							action = override_payload[0]
							code = override_payload[3]
							if code != today_day_code or action not in (1, 2):
								continue
							# Override timestamp at item[1] (epoch ms as string).
							try:
								ts = int(item[1]) if len(item) > 1 else -1
							except (TypeError, ValueError):
								ts = -1
							if ts >= latest_ts:
								latest_ts = ts
								latest_action = action
					if latest_action is not None:
						bedtime_enabled_today = (latest_action == 2)
						bedtime_today_source = "today_override"
						bedtime_today_override_action = latest_action
						_LOGGER.debug(
							f"Most recent bedtime override for today (day_code="
							f"{today_day_code}, ts={latest_ts}): action={latest_action} "
							f"-> bedtime_enabled_today={bedtime_enabled_today} "
							f"(weekly was {bedtime_enabled})"
						)

				_LOGGER.info(
					f"Time limit rules: bedtime_enabled={bedtime_enabled} (rule_id={bedtime_rule_id}, {len(bedtime_schedule)} schedules), "
					f"bedtime_enabled_today={bedtime_enabled_today}, "
					f"school_time_enabled={school_time_enabled} (rule_id={schooltime_rule_id}, {len(school_time_schedule)} schedules), "
					f"daily_limit_schedule={len(daily_limit_schedule)} entries"
				)

				return {
					"bedtime_enabled": bedtime_enabled,
					"school_time_enabled": school_time_enabled,
					# Effective state for today, after applying the per-day type-9
					# override if one exists for today (issue #113). Falls back to
					# the weekly value when no override is posted for today.
					"bedtime_enabled_today": bedtime_enabled_today,
					"bedtime_today_source": bedtime_today_source,
					"bedtime_today_override_action": bedtime_today_override_action,
						"schedule_today": schedule_today,
						"schedule_timezone": schedule_timezone,
						"schedule_timezone_source": schedule_timezone_source,
						"google_schedule_timezone": self._google_schedule_timezones.get(account_id),
					"bedtime_schedule": bedtime_schedule,
					"school_time_schedule": school_time_schedule,
					"daily_limit_schedule": daily_limit_schedule,
					"bedtime_rule_id": bedtime_rule_id,
					"schooltime_rule_id": schooltime_rule_id
				}

		except SessionExpiredError:
			raise
		except Exception as err:
			_LOGGER.error("Failed to fetch time limit rules: %s", err)
			raise NetworkError(f"Failed to fetch time limit rules: {err}") from err

	async def async_cleanup(self) -> None:
		"""Clean up client resources."""
		if self._session:
			try:
				await self._session.close()
			except Exception as e:
				_LOGGER.debug(f"Error closing session during cleanup: {e}")
			self._session = None
		# Clear cached cookie data
		if hasattr(self, '_cookie_dict'):
			del self._cookie_dict
		if hasattr(self, '_cookie_header'):
			del self._cookie_header
