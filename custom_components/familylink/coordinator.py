"""Data update coordinator for Google Family Link integration."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client.api import FamilyLinkClient
from .const import (
	CONF_STRICT_MODE,
	CONF_STRICT_MODE_RULES,
	DEFAULT_STRICT_MODE,
	DEFAULT_STRICT_MODE_RULES,
	EVENT_STRICT_MODE_ACTION,
	STRICT_MODE_BONUS_GRACE,
	STRICT_MODE_COOLDOWN,
	CONF_ENABLE_LOCATION_TRACKING,
	CONF_UPDATE_INTERVAL,
	DEFAULT_UPDATE_INTERVAL,
	DEVICE_LOCK_ACTION,
	DEVICE_UNLOCK_ACTION,
	DOMAIN,
	LOGGER_NAME,
)
from .exceptions import FamilyLinkException, SessionExpiredError
from .strict_mode import (
	ACTION_CANCEL_BONUS,
	ACTION_DISABLE_BEDTIME,
	ACTION_DISABLE_DAILY_LIMIT,
	ACTION_DISABLE_SCHOOL_TIME,
	ACTION_ENABLE_BEDTIME,
	ACTION_ENABLE_DAILY_LIMIT,
	ACTION_ENABLE_SCHOOL_TIME,
	ACTION_LOCK_DEVICE,
	ACTION_SET_BEDTIME,
	ACTION_SET_DAILY_LIMIT,
	ACTION_UNLOCK_DEVICE,
	plan_strict_actions,
	snapshot_policies,
	snapshot_values,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


def _gate_windows_on_policy_state(
	devices_time_data: dict[str, dict[str, Any]],
	bedtime_enabled_today: bool | None,
	schooltime_enabled_today: bool | None,
	child_name: str = "",
) -> None:
	"""Clear per-device windows whose policy is off for today (issue #155).

	Mutates ``devices_time_data`` in place. A ``None`` policy state means the
	state is unknown, in which case the parser's own reading is kept.
	"""
	for policy, enabled_today in (
		("bedtime", bedtime_enabled_today),
		("schooltime", schooltime_enabled_today),
	):
		if enabled_today is not False:
			continue
		for device_id, time_data in devices_time_data.items():
			if not isinstance(time_data, dict):
				continue
			if time_data.get(f"{policy}_active") or time_data.get(f"{policy}_window"):
				_LOGGER.debug(
					f"Device {device_id} ({child_name}): {policy} window dropped, "
					f"policy is off today (was active={time_data.get(f'{policy}_active')})"
				)
			time_data[f"{policy}_active"] = False
			time_data[f"{policy}_window"] = None


class FamilyLinkDataUpdateCoordinator(DataUpdateCoordinator):
	"""Class to manage fetching data from the Family Link API."""

	def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
		"""Initialize the coordinator."""
		self.entry = entry
		self.client: FamilyLinkClient | None = None
		self._devices: dict[str, dict[str, Any]] = {}
		self._is_retrying_auth = False  # Prevent infinite retry loops
		self._auth_notification_sent = False  # Only send auth notification once
		self._pending_lock_states: dict[str, tuple[bool, float]] = {}  # device_id -> (locked, timestamp)
		self._pending_time_limit_states: dict[str, dict[str, tuple[bool, float]]] = {}  # child_id -> {"bedtime": (enabled, timestamp), "school_time": (enabled, timestamp), "daily_limit": (enabled, timestamp)}
		self._last_known_data: dict[str, Any] | None = None  # Cache for last successful fetch
		self.child_device_ids: dict[str, str] = {}  # child_id -> registry id of the child's hub device

		# Strict mode: Home Assistant reverts restriction changes made from the
		# Family Link side (see strict_mode.py). The default and the rule set
		# come from the options; the per-child switch overrides the default.
		self.strict_mode_default: bool = bool(entry.options.get(
			CONF_STRICT_MODE, entry.data.get(CONF_STRICT_MODE, DEFAULT_STRICT_MODE)
		))
		self.strict_rules: frozenset[str] = frozenset(entry.options.get(
			CONF_STRICT_MODE_RULES, entry.data.get(CONF_STRICT_MODE_RULES, DEFAULT_STRICT_MODE_RULES)
		) or ())
		self._strict_mode_children: dict[str, bool] = {}
		self.strict_mode_status: dict[str, dict[str, Any]] = {}  # child_id -> last action info
		self._strict_cooldown: dict[str, float] = {}  # action key -> last run timestamp
		self._ha_bonus_until: dict[str, float] = {}  # device_id -> until when an HA-granted bonus is legitimate
		# Today's decisions made from Home Assistant, per child (persisted so a
		# restart does not turn a bedtime the parent switched off back on):
		# {child_id: {"date": "YYYY-MM-DD", "policies": {...}, "devices": {...}}}
		self._strict_intents: dict[str, dict[str, Any]] = {}
		self._strict_store: Store = Store(hass, 1, f"{DOMAIN}.strict_mode_intents")

		# Get settings from options (runtime changes) or fall back to data (initial config)
		self._location_tracking_enabled = entry.options.get(
			CONF_ENABLE_LOCATION_TRACKING,
			entry.data.get(CONF_ENABLE_LOCATION_TRACKING, False)
		)
		update_interval = entry.options.get(
			CONF_UPDATE_INTERVAL,
			entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
		)

		super().__init__(
			hass,
			_LOGGER,
			name=DOMAIN,
			update_interval=timedelta(seconds=update_interval),
		)
		_LOGGER.debug(f"Coordinator initialized with update_interval={update_interval}s, location_tracking={self._location_tracking_enabled}")

	async def _async_update_data(self) -> dict[str, Any]:
		"""Fetch data from Family Link API."""
		try:
			result = await self._async_fetch_data()
			# Reset notification flag on successful fetch (allows new notification if auth fails again later)
			if self._auth_notification_sent:
				self._auth_notification_sent = False
				_LOGGER.debug("Auth notification flag reset after successful data fetch")
			self._last_known_data = result  # Store successful result
			await self._async_enforce_strict_mode(result)
			return result

		except SessionExpiredError as err:
			# Prevent infinite retry loops
			if self._is_retrying_auth:
				_LOGGER.error("Session still expired after refresh - cookies are invalid")
				await self._create_auth_notification()
				raise UpdateFailed("Session expired, please re-authenticate via Family Link Auth add-on") from err

			_LOGGER.warning("Session expired, attempting to refresh authentication")
			self._is_retrying_auth = True

			try:
				await self._async_refresh_auth()

				# Retry ONCE after refreshing authentication
				_LOGGER.info("Retrying data fetch after authentication refresh...")
				result = await self._async_fetch_data()
				self._is_retrying_auth = False  # Reset flag on success
				self._last_known_data = result  # Store successful result
				await self._async_enforce_strict_mode(result)
				return result

			except SessionExpiredError:
				# If it still fails after refresh, cookies are truly invalid
				_LOGGER.error("Session still expired after refresh - please re-authenticate via add-on")
				await self._create_auth_notification()
				raise UpdateFailed("Session expired, please re-authenticate via Family Link Auth add-on") from err
			except Exception as retry_err:
				_LOGGER.error(f"Retry after auth refresh failed: {retry_err}")
				raise UpdateFailed(f"Failed after auth refresh: {retry_err}") from retry_err
			finally:
				self._is_retrying_auth = False  # Always reset flag

		except FamilyLinkException as err:
			_LOGGER.error("Error fetching Family Link data: %s", err)
			if self._last_known_data is not None:
				_LOGGER.info("Returning last known data due to FamilyLinkException: %s", err)
				return self._last_known_data
			raise UpdateFailed(f"Error communicating with Family Link: {err}") from err

		except Exception as err:
			_LOGGER.exception("Unexpected error fetching Family Link data")
			if self._last_known_data is not None:
				_LOGGER.info("Returning last known data due to unexpected error: %s", err)
				return self._last_known_data
			raise UpdateFailed(f"Unexpected error: {err}") from err

	async def _async_fetch_data(self) -> dict[str, Any]:
		"""Perform the actual data fetch from Family Link API."""
		if self.client is None:
			await self._async_setup_client()

		# Initialize empty device cache (will be populated per-child below)
		self._devices = {}

		# Fetch family members info first to get all supervised children
		family_members = None
		supervised_children = []
		try:
			members_data = await self.client.async_get_family_members()
			family_members = members_data.get("members", [])

			# Find ALL supervised children (not just the first one)
			for member in family_members:
				supervision_info = member.get("memberSupervisionInfo")
				if supervision_info and supervision_info.get("isSupervisedMember"):
					supervised_children.append(member)

			_LOGGER.debug(f"Fetched {len(family_members)} family members, {len(supervised_children)} supervised children")
		except SessionExpiredError:
			raise  # Re-raise to trigger auth notification
		except Exception as err:
			_LOGGER.warning(f"Failed to fetch family members: {err}")

		if not supervised_children:
			_LOGGER.warning("No supervised children found — entities will not be created. Check your Family Link account configuration.")

		# Fetch data for each supervised child
		children_data = []
		for child in supervised_children:
			child_id = child.get("userId")
			if not child_id:
				_LOGGER.warning("Skipping child with missing userId: %s", child)
				continue
			child_name = child.get("profile", {}).get("displayName", "Unknown")

			_LOGGER.debug(f"Fetching data for child: {child_name} (ID: {child_id})")

			# Fetch complete apps and usage data for this child
			apps_usage_data = None
			cached_devices = None  # Populated from cache only if the fetch fails
			try:
				apps_usage_data = await self.client.async_get_apps_and_usage(account_id=child_id)
				_LOGGER.debug(
					f"Fetched for {child_name}: {len(apps_usage_data.get('apps', []))} apps, "
					f"{len(apps_usage_data.get('deviceInfo', []))} devices, "
					f"{len(apps_usage_data.get('appUsageSessions', []))} usage sessions"
				)
			except SessionExpiredError:
				raise  # Re-raise to trigger auth notification
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch apps and usage data for {child_name}: {err}")
				# Try to recover apps_usage_data from last known data cache.
				# Note: deviceInfo is intentionally left out here — the cached
				# child stores already-parsed `devices`, not raw deviceInfo, so
				# we restore the device list directly below (cached_devices)
				# rather than re-deriving it from an empty deviceInfo (which
				# would otherwise wipe every device on a transient 503).
				if self._last_known_data:
					for cached_child in self._last_known_data.get("children_data", []):
						if cached_child.get("child_id") == child_id:
							apps_usage_data = {
								"apps": cached_child.get("apps", []),
								"deviceInfo": [],
								"appUsageSessions": cached_child.get("app_usage_sessions", []),
							}
							cached_devices = cached_child.get("devices")
							_LOGGER.debug(f"Using cached apps/usage data for {child_name}")
							break

			# Extract devices from apps_usage_data
			devices = []
			if apps_usage_data:
				for device_info in apps_usage_data.get("deviceInfo", []):
					display_info = device_info.get("displayInfo", {})
					device = {
						"id": device_info.get("deviceId"),
						"name": display_info.get("friendlyName", "Unknown Device"),
						"model": display_info.get("model", "Unknown"),
						"last_activity": display_info.get("lastActivityTimeMillis"),
						"capabilities": device_info.get("capabilityInfo", {}).get("capabilities", []),
						"child_id": child_id,  # Link device to child
						"child_name": child_name,
					}
					devices.append(device)

			# If the apps/usage fetch failed, deviceInfo is empty, so the loop
			# above produced no devices. Fall back to the cached device list so
			# a transient error doesn't make every device disappear.
			if not devices and cached_devices:
				devices = [dict(device) for device in cached_devices]
				_LOGGER.debug(f"Restored {len(devices)} cached device(s) for {child_name}")

			# Fetch time limit configuration (bedtime/school time schedules and enabled states)
			bedtime_enabled = None
			school_time_enabled = None
			bedtime_schedule = None
			school_time_schedule = None
			daily_limit_week_rows = None
			# Today-effective bedtime state derived from the per-day type-9
			# override in the timeLimit response (issue #113). This is the
			# authoritative source for the bedtime switch — it reflects the
			# "Only today" override Google actually applies — and takes
			# precedence over the appliedTimeLimits heuristic below.
			bedtime_enabled_today_from_rules = None
			school_time_enabled_today_from_rules = None
			# Policy ids from the revisions, handed to the appliedTimeLimits
			# parser so UUID-keyed windows are classified by policy instead of
			# by list order (issue #151).
			bedtime_rule_id = None
			schooltime_rule_id = None

			try:
				time_limit_config = await self.client.async_get_time_limit(account_id=child_id)
				bedtime_enabled = time_limit_config.get("bedtime_enabled")
				school_time_enabled = time_limit_config.get("school_time_enabled")
				bedtime_rule_id = time_limit_config.get("bedtime_rule_id")
				schooltime_rule_id = time_limit_config.get("schooltime_rule_id")
				bedtime_enabled_today_from_rules = time_limit_config.get("bedtime_enabled_today")
				school_time_enabled_today_from_rules = time_limit_config.get("school_time_enabled_today")
				bedtime_schedule = time_limit_config.get("bedtime_schedule")
				school_time_schedule = time_limit_config.get("school_time_schedule")
				daily_limit_week_rows = time_limit_config.get("daily_limit_week")
				_LOGGER.debug(
					f"Fetched time limit config for {child_name}: "
					f"bedtime={bedtime_enabled}, bedtime_today={bedtime_enabled_today_from_rules}, "
					f"school_time={school_time_enabled}, "
					f"school_time_today={school_time_enabled_today_from_rules}"
				)
			except SessionExpiredError:
				raise  # Re-raise to trigger auth notification
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch time limit config for {child_name}: {err}")
				# Try to recover from last known data cache
				if self._last_known_data:
					for cached_child in self._last_known_data.get("children_data", []):
						if cached_child.get("child_id") == child_id:
							bedtime_enabled = cached_child.get("bedtime_enabled")
							school_time_enabled = cached_child.get("school_time_enabled")
							bedtime_enabled_today_from_rules = cached_child.get("bedtime_enabled_today")
							school_time_enabled_today_from_rules = cached_child.get("school_time_enabled_today")
							bedtime_schedule = cached_child.get("bedtime_schedule")
							school_time_schedule = cached_child.get("school_time_schedule")
							daily_limit_week_rows = cached_child.get("daily_limit_week")
							_LOGGER.debug(f"Using cached time limit config for {child_name}")
							break

			# Fetch applied time limits (lock states and per-device time data)
			device_lock_states = {}
			devices_time_data = {}
			# Today-effective flags from appliedTimeLimits — combine the weekly
			# policy with any daily override that's been posted. The switches
			# read these instead of the weekly revisions so they reflect what
			# Google actually applies on the child device right now (issue #114).
			bedtime_enabled_today = None
			schooltime_enabled_today = None

			try:
				applied_limits_data = await self.client.async_get_applied_time_limits(
					account_id=child_id,
					bedtime_rule_id=bedtime_rule_id,
					schooltime_rule_id=schooltime_rule_id,
				)
				device_lock_states = applied_limits_data.get("device_lock_states", {})
				devices_time_data = applied_limits_data.get("devices", {})
				bedtime_enabled_today = applied_limits_data.get("bedtime_enabled_today")
				schooltime_enabled_today = applied_limits_data.get("schooltime_enabled_today")
				_LOGGER.debug(
					f"Fetched applied time limits for {child_name}: "
					f"{len(device_lock_states)} device lock states, "
					f"{len(devices_time_data)} devices with time data, "
					f"bedtime_today={bedtime_enabled_today}, schooltime_today={schooltime_enabled_today}"
				)
			except SessionExpiredError:
				raise  # Re-raise to trigger auth notification
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch applied time limits for {child_name}: {err}")
				# Try to recover from last known data cache
				if self._last_known_data:
					for cached_child in self._last_known_data.get("children_data", []):
						if cached_child.get("child_id") == child_id:
							devices_time_data = cached_child.get("devices_time_data", {})
							bedtime_enabled_today = cached_child.get("bedtime_enabled_today")
							schooltime_enabled_today = cached_child.get("school_time_enabled_today")
							_LOGGER.debug(f"Using cached applied time limits for {child_name}")
							break

			# The timeLimit response carries the authoritative per-day bedtime
			# override (issue #113): action 2/1 for today's day_code directly
			# states what Google applies. Prefer it over the appliedTimeLimits
			# window heuristic, which can miss the effective state (e.g. an
			# "Only today" OFF override leaves no enabled window to detect).
			if bedtime_enabled_today_from_rules is not None:
				bedtime_enabled_today = bedtime_enabled_today_from_rules

			# Same for school time (issue #140). School time overrides are keyed
			# by [weekday, rule_uuid] rather than a day code, so they are read by
			# a dedicated parser, but the precedence rule is identical: an
			# explicit override for today beats the appliedTimeLimits window
			# scan, which only tells us a school time window is SCHEDULED today,
			# not whether it is actually enabled.
			#
			# The raw appliedTimeLimits value is kept as
			# school_time_scheduled_today and exposed as a switch attribute, so
			# a "scheduled but overridden off" day is visible without a debug log.
			school_time_scheduled_today = schooltime_enabled_today
			if school_time_enabled_today_from_rules is not None:
				schooltime_enabled_today = school_time_enabled_today_from_rules

			# A window cannot be active when the policy that owns it is off for
			# today (issue #155). appliedTimeLimits keeps listing the window rows
			# with their own state flag set even after the bedtime or school
			# time policy has been switched off, so the per-device parser alone
			# reports "bedtime active" in the evening while the switch (which
			# reads the policy state above) correctly shows off. Apply the same
			# today-effective state to the device windows the sensors read.
			_gate_windows_on_policy_state(
				devices_time_data, bedtime_enabled_today, schooltime_enabled_today, child_name
			)

			# Update device cache with real lock states from API
			current_time = time.time()
			for device in devices:
				device_id = device["id"]

				# Check if we have a pending lock state change (within last 5 seconds)
				if device_id in self._pending_lock_states:
					pending_locked, timestamp = self._pending_lock_states[device_id]
					age = current_time - timestamp

					if age < 5.0:  # Use pending state for 5 seconds
						device["locked"] = pending_locked
						_LOGGER.debug(
							f"Using pending lock state for {device_id}: {pending_locked} "
							f"(age: {age:.1f}s, API says: {device_lock_states.get(device_id)})"
						)
						continue
					else:
						# Expired, remove from pending
						del self._pending_lock_states[device_id]

				# Use real lock state from API if available, otherwise default to False
				device["locked"] = device_lock_states.get(device_id, False)

				# Enrich device with time data from devices_time_data
				if device_id in devices_time_data:
					time_data = devices_time_data[device_id]
					device["total_allowed_minutes"] = time_data.get("total_allowed_minutes")
					device["used_minutes"] = time_data.get("used_minutes")
					device["remaining_minutes"] = time_data.get("remaining_minutes")
					device["daily_limit_enabled"] = time_data.get("daily_limit_enabled")
					device["daily_limit_minutes"] = time_data.get("daily_limit_minutes")
					device["daily_limit_remaining"] = time_data.get("daily_limit_remaining")
					device["bedtime_window"] = time_data.get("bedtime_window")
					device["schooltime_window"] = time_data.get("schooltime_window")
					device["bedtime_active"] = time_data.get("bedtime_active")
					device["schooltime_active"] = time_data.get("schooltime_active")
					device["bonus_minutes"] = time_data.get("bonus_minutes")
					device["bonus_override_id"] = time_data.get("bonus_override_id")

			# Aggregate daily_limit_enabled from devices
			# If ANY device has daily_limit enabled, consider it globally enabled
			daily_limit_enabled = False
			for device in devices:
				if device.get("daily_limit_enabled"):
					daily_limit_enabled = True
					break
			_LOGGER.debug(f"Aggregated daily_limit_enabled for {child_name}: {daily_limit_enabled}")

			# Compute daily screen time for this child from the already-fetched
			# apps/usage data (avoids a duplicate appsandusage API call per child)
			screen_time = None
			try:
				screen_time = await self.client.async_get_daily_screen_time(
					account_id=child_id, data=apps_usage_data
				)
				_LOGGER.debug(
					f"Successfully fetched screen time for {child_name}: {screen_time['formatted']} "
					f"({len(screen_time['app_breakdown'])} apps)"
				)
			except SessionExpiredError:
				raise  # Re-raise to trigger auth notification
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch screen time data for {child_name}: {err}")
				# Try to recover from last known data cache
				if self._last_known_data:
					for cached_child in self._last_known_data.get("children_data", []):
						if cached_child.get("child_id") == child_id:
							screen_time = cached_child.get("screen_time")
							if screen_time:
								_LOGGER.debug(f"Using cached screen time for {child_name}")
							break

			# Fetch location data for this child (if enabled)
			location = None
			if self._location_tracking_enabled:
				try:
					location = await self.client.async_get_location(account_id=child_id)
					if location:
						# Resolve source device name from device ID
						source_device_id = location.get("source_device_id")
						source_device_name = None
						if source_device_id:
							for device in devices:
								if device.get("id") == source_device_id:
									source_device_name = device.get("name")
									break
						location["source_device_name"] = source_device_name
						_LOGGER.debug(
							f"Fetched location for {child_name}: "
							f"({location['latitude']}, {location['longitude']}) "
							f"place={location.get('place_name') or 'unknown'}"
						)
				except SessionExpiredError:
					raise  # Re-raise to trigger auth notification
				except Exception as err:
					_LOGGER.warning(f"Failed to fetch location data for {child_name}: {err}")

			# Who can call and text the child (select entity). One call per
			# child; on a transient error keep the last known level.
			contact_restriction = None
			try:
				contact_restriction = await self.client.async_get_contact_restriction(account_id=child_id)
			except SessionExpiredError:
				raise  # Re-raise to trigger auth notification
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch contact restriction for {child_name}: {err}")
				if self._last_known_data:
					for cached_child in self._last_known_data.get("children_data", []):
						if cached_child.get("child_id") == child_id:
							contact_restriction = cached_child.get("contact_restriction")
							_LOGGER.debug(f"Using cached contact restriction for {child_name}")
							break

			# Store data for this child
			child_data = {
				"child": child,
				"child_id": child_id,
				"child_name": child_name,
				"devices": devices,
				"screen_time": screen_time,
				"location": location,
				"contact_restriction": contact_restriction,
				"apps": apps_usage_data.get("apps", []) if apps_usage_data else [],
				"app_usage_sessions": apps_usage_data.get("appUsageSessions", []) if apps_usage_data else [],
				"bedtime_enabled": bedtime_enabled,
				"school_time_enabled": school_time_enabled,
				# Effective state for today (issue #114) — read from
				# appliedTimeLimits, which already merges weekly policy with
				# daily overrides. The switches use these instead of the
				# weekly-only revisions above.
				"bedtime_enabled_today": bedtime_enabled_today,
				"school_time_enabled_today": schooltime_enabled_today,
				# Whether a school time window exists in today's weekly policy,
				# independent of any "today only" override (issue #140).
				"school_time_scheduled_today": school_time_scheduled_today,
				"bedtime_schedule": bedtime_schedule,
				"school_time_schedule": school_time_schedule,
				"daily_limit_week": daily_limit_week_rows,
				"daily_limit_enabled": daily_limit_enabled,
				"devices_time_data": devices_time_data,
			}
			children_data.append(child_data)

			# Update devices cache with child_id prefix to avoid conflicts
			for device in devices:
				self._devices[f"{child_id}_{device['id']}"] = device

		_LOGGER.debug("Successfully updated all Family Link data")
		return {
			"family_members": family_members,
			"supervised_children": supervised_children,
			"children_data": children_data,
		}

	async def _async_setup_client(self) -> None:
		"""Set up the Family Link client."""
		if self.client is not None:
			return

		try:
			self.client = FamilyLinkClient(
				hass=self.hass,
				config=self.entry.data,
			)

			await self.client.async_authenticate()
			_LOGGER.debug("Successfully set up Family Link client")

		except Exception as err:
			_LOGGER.error("Failed to setup Family Link client: %s", err)
			raise

	async def _async_refresh_auth(self) -> None:
		"""Refresh authentication when session expires."""
		if self.client is None:
			return

		try:
			await self.client.async_refresh_session()
			_LOGGER.info("Successfully refreshed authentication")
		except Exception as err:
			_LOGGER.error("Failed to refresh authentication: %s", err)
			# Clear client to force re-authentication on next update
			self.client = None
			raise

	async def async_control_device(
		self, device_id: str, action: str, child_id: str | None = None
	) -> bool:
		"""Control a Family Link device.

		Args:
			device_id: The device ID to control
			action: "lock" or "unlock"
			child_id: The child's user ID (optional, will be extracted from device data if not provided)
		"""
		if self.client is None:
			await self._async_setup_client()

		try:
			# If child_id not provided, find it from device data
			if child_id is None:
				# Look for device in cache
				for cached_key, device in self._devices.items():
					if device["id"] == device_id:
						child_id = device.get("child_id")
						break

			if child_id is None:
				_LOGGER.error(f"Could not determine child_id for device {device_id}")
				return False

			success = await self.client.async_control_device(device_id, action, child_id)

			if success:
				_LOGGER.info(f"Successfully {action}ed device {device_id}")
				# A lock or unlock from HA is the parent's decision for the day (strict mode)
				self.record_device_intent(child_id, device_id, action)

				# Store the expected lock state temporarily (for 5 seconds)
				# This ensures the UI reflects the change immediately, even if the API
				# takes time to propagate the state
				expected_locked = (action == DEVICE_LOCK_ACTION)
				self._pending_lock_states[device_id] = (expected_locked, time.time())
				_LOGGER.debug(f"Set pending lock state for {device_id}: {expected_locked}")

				# Schedule a data refresh to get latest state from API
				await asyncio.sleep(1)  # Brief delay for state to propagate
				await self.async_request_refresh()

			return success

		except Exception as err:
			_LOGGER.error("Failed to control device %s: %s", device_id, err)
			return False

	def set_pending_time_limit_state(self, child_id: str, limit_type: str, enabled: bool | None) -> None:
		"""Set a pending time limit state to reflect UI changes immediately.

		Args:
			child_id: The child's user ID
			limit_type: One of "bedtime", "school_time", or "daily_limit"
			enabled: Whether the limit is being enabled (True) or disabled (False).
				None clears any pending state (e.g. after a failed API call).
		"""
		if enabled is None:
			self._pending_time_limit_states.get(child_id, {}).pop(limit_type, None)
			_LOGGER.debug(f"Cleared pending {limit_type} state for child {child_id}")
			return

		if child_id not in self._pending_time_limit_states:
			self._pending_time_limit_states[child_id] = {}

		self._pending_time_limit_states[child_id][limit_type] = (enabled, time.time())
		_LOGGER.debug(f"Set pending {limit_type} state for child {child_id}: {enabled}")

	def get_pending_time_limit_state(self, child_id: str, limit_type: str) -> bool | None:
		"""Get pending time limit state if it exists and is still valid (< 5 seconds old).

		Args:
			child_id: The child's user ID
			limit_type: One of "bedtime", "school_time", or "daily_limit"

		Returns:
			The pending enabled state if valid, None otherwise
		"""
		if child_id not in self._pending_time_limit_states:
			return None

		if limit_type not in self._pending_time_limit_states[child_id]:
			return None

		enabled, timestamp = self._pending_time_limit_states[child_id][limit_type]
		age = time.time() - timestamp

		if age < 5.0:  # Pending state valid for 5 seconds
			return enabled
		else:
			# Expired, clean up
			del self._pending_time_limit_states[child_id][limit_type]
			return None

	async def async_get_device(self, device_id: str) -> dict[str, Any] | None:
		"""Get device data by ID."""
		return self._devices.get(device_id)

	async def _create_auth_notification(self) -> None:
		"""Create a persistent notification when authentication fails (only once)."""
		if self._auth_notification_sent:
			_LOGGER.debug("Auth notification already sent, skipping")
			return

		await self.hass.services.async_call(
			"persistent_notification",
			"create",
			{
				"title": "Google Family Link - Authentication Required",
				"message": (
					"Your Google Family Link session has expired.\n\n"
					"Please re-authenticate using the **Family Link Auth** add-on:\n"
					"1. Open the add-on in Supervisor\n"
					"2. Click 'Open Web UI'\n"
					"3. Log in with your Google account\n"
					"4. The integration will automatically resume once authenticated."
				),
				"notification_id": "familylink_auth_expired",
			},
		)
		self._auth_notification_sent = True
		_LOGGER.info("Created authentication notification for user")


	# ------------------------------------------------------------------
	# Strict mode
	# ------------------------------------------------------------------

	def is_strict_mode_enabled(self, child_id: str) -> bool:
		"""Return whether strict mode is on for this child (switch, else option default)."""
		return self._strict_mode_children.get(child_id, self.strict_mode_default)

	async def async_load_strict_intents(self) -> None:
		"""Load today's Home Assistant decisions saved before the last restart."""
		try:
			data = await self._strict_store.async_load()
		except Exception as err:
			_LOGGER.warning(f"Strict mode: could not load saved intents: {err}")
			return
		if isinstance(data, dict) and isinstance(data.get("intents"), dict):
			self._strict_intents = data["intents"]
		if isinstance(data, dict) and isinstance(data.get("ha_bonus_until"), dict):
			# An HA-granted bonus must survive a restart, or the first poll
			# after it would cancel the bonus as a Google-side one (live test).
			now = time.time()
			self._ha_bonus_until = {
				d: float(t) for d, t in data["ha_bonus_until"].items()
				if isinstance(t, (int, float)) and t > now
			}

	def _save_strict_intents(self) -> None:
		self._strict_store.async_delay_save(
			lambda: {"intents": self._strict_intents, "ha_bonus_until": self._ha_bonus_until}, 2
		)

	def _intents_for(self, child_id: str) -> dict[str, Any]:
		"""Intents of a child: policy references persist, device decisions expire daily.

		The bedtime / daily limit / school time references are the parent's
		standing choice (the HA switches act on the weekly policy), so they
		stay until HA changes them or strict mode is switched on again; a
		reset at midnight would let a weekly change made on Google's side
		become the reference the next morning. A lock or unlock done from HA
		is a decision for the day: it expires at midnight, and the bypass
		protection of the lock rule resumes.
		"""
		today = dt_util.now().date().isoformat()
		entry = self._strict_intents.get(child_id)
		if not entry:
			entry = {"date": today, "policies": {}, "devices": {}, "values": {}}
			self._strict_intents[child_id] = entry
		elif entry.get("date") != today:
			entry["date"] = today
			entry["devices"] = {}
		entry.setdefault("policies", {})
		entry.setdefault("values", {})
		return entry

	def _resolve_child_id(self, child_id: str | None) -> str | None:
		"""Actions without a child target apply to the first supervised child."""
		if child_id:
			return child_id
		for child_data in (self.data or {}).get("children_data", []):
			return child_data.get("child_id")
		return None

	def record_policy_intent(self, child_id: str | None, policy: str, enabled: bool) -> None:
		"""Remember that bedtime / daily limit / school time was set from HA today."""
		child_id = self._resolve_child_id(child_id)
		if not child_id:
			return
		self._intents_for(child_id)["policies"][policy] = bool(enabled)
		self._save_strict_intents()
		_LOGGER.debug(f"Strict mode: {policy} set to {enabled} from HA for child {child_id} (kept for today)")

	def record_device_intent(self, child_id: str | None, device_id: str, action: str) -> None:
		"""Remember that a device was locked or unlocked from HA today."""
		child_id = self._resolve_child_id(child_id)
		if not child_id or not device_id:
			return
		self._intents_for(child_id)["devices"][device_id] = action
		self._save_strict_intents()
		_LOGGER.debug(f"Strict mode: device {device_id} {action}ed from HA for child {child_id} (kept for today)")

	def record_bedtime_hours(self, child_id: str | None, day: int, start: list[int], end: list[int]) -> None:
		"""A weekly bedtime slot set from HA becomes the reference for that day (strict mode)."""
		child_id = self._resolve_child_id(child_id)
		if not child_id:
			return
		if day is None:
			day = dt_util.now().isoweekday()
		values = self._intents_for(child_id).setdefault("values", {})
		values.setdefault("bedtime", {})[str(day)] = [list(start), list(end)]
		self._save_strict_intents()

	def record_daily_limit_minutes(self, child_id: str | None, minutes: int, day: int | None = None) -> None:
		"""A weekday quota set from HA becomes the reference for that weekday (strict mode)."""
		child_id = self._resolve_child_id(child_id)
		if not child_id:
			return
		if not (isinstance(day, int) and 1 <= day <= 7):
			day = dt_util.now().isoweekday()
		values = self._intents_for(child_id).setdefault("values", {})
		values.setdefault("daily_limit_week", {})[str(day)] = int(minutes)
		self._save_strict_intents()

	def clear_device_intent(self, child_id: str | None, device_id: str) -> None:
		"""Forget the decision of the day for a device (strict mode lock lifted)."""
		child_id = self._resolve_child_id(child_id)
		if not child_id:
			return
		self._intents_for(child_id)["devices"].pop(device_id, None)
		self._save_strict_intents()

	def strict_intents_today(self, child_id: str) -> dict[str, Any]:
		"""References and today's device decisions for the switch attributes (no side effect)."""
		entry = self._strict_intents.get(child_id) or {}
		devices = entry.get("devices", {}) if entry.get("date") == dt_util.now().date().isoformat() else {}
		return {
			"policies": dict(entry.get("policies", {})),
			"devices": dict(devices),
			"values": dict(entry.get("values", {})),
		}

	def register_ha_bonus(self, device_id: str, minutes: int) -> None:
		"""Record a bonus granted from Home Assistant so strict mode leaves it alone.

		Strict mode reverts what is done from the Family Link side; a bonus the
		parent gives through the buttons or the add_time_bonus action is the
		parent's decision and must survive. The allowance lasts the bonus
		duration plus a short grace period.
		"""
		self._ha_bonus_until[device_id] = time.time() + max(int(minutes), 0) * 60 + STRICT_MODE_BONUS_GRACE
		self._save_strict_intents()
		_LOGGER.debug(f"Strict mode: bonus of {minutes} min granted from HA on {device_id}, protected")

	def _ha_bonus_devices(self) -> frozenset[str]:
		"""Devices whose HA-granted bonus is still running (expired entries pruned)."""
		now = time.time()
		self._ha_bonus_until = {d: t for d, t in self._ha_bonus_until.items() if t > now}
		return frozenset(self._ha_bonus_until)

	def set_strict_mode(self, child_id: str, enabled: bool, enforce_now: bool = True) -> None:
		"""Switch strict mode on or off for a child.

		Turning it on runs an enforcement pass right away on the last data,
		so a bonus already running is cancelled without waiting for the next
		poll.
		"""
		self._strict_mode_children[child_id] = enabled
		_LOGGER.info(f"Strict mode {'enabled' if enabled else 'disabled'} for child {child_id}")
		if enabled and enforce_now:
			# Control was Google's while strict mode was off: the policies in
			# force now become the reference again. Device decisions (a lock
			# or unlock done from HA today) are kept: they are still what the
			# parent wants.
			intents = self._intents_for(child_id)
			intents["policies"] = {}
			intents["values"] = {}
			self._save_strict_intents()
		if enabled and enforce_now and self.data:
			self.hass.async_create_task(self._async_enforce_strict_mode(self.data))

	async def _async_enforce_strict_mode(self, data: dict[str, Any] | None) -> None:
		"""Revert restriction changes made from the Family Link side (strict mode).

		Runs after every successful refresh. Never raises: a failed corrective
		action is logged and retried at the next poll, after the cooldown.
		"""
		if not data or self.client is None:
			return
		for child_data in data.get("children_data", []):
			child_id = child_data.get("child_id")
			if not child_id or not self.is_strict_mode_enabled(child_id):
				continue
			try:
				intents = self._intents_for(child_id)
				added = snapshot_policies(child_data, self.strict_rules, intents)
				if added:
					intents["policies"].update(added)
					self._save_strict_intents()
					_LOGGER.info(
						f"Strict mode: reference state for {child_data.get('child_name', child_id)} "
						f"set from Google: {added}"
					)
				added_values = snapshot_values(child_data, self.strict_rules, intents)
				if added_values:
					intents.setdefault("values", {}).update(added_values)
					self._save_strict_intents()
					_LOGGER.info(
						f"Strict mode: reference values for {child_data.get('child_name', child_id)} "
						f"set from Google: {added_values}"
					)
				actions = plan_strict_actions(
					child_data, self.strict_rules, self._ha_bonus_devices(), intents
				)
			except Exception as err:
				_LOGGER.warning(f"Strict mode: could not evaluate child {child_id}: {err}")
				continue
			for action in actions:
				await self._async_run_strict_action(child_data, action)

	async def _async_run_strict_action(self, child_data: dict[str, Any], action: dict[str, Any]) -> None:
		"""Execute one corrective action, with the same guards as the switches."""
		child_id = action["child_id"]
		name = action["action"]
		device_id = action.get("device_id")

		# A change Home Assistant itself just made is still propagating on
		# Google's side: do not fight our own pending state.
		policy_of_action = {
			ACTION_ENABLE_BEDTIME: "bedtime", ACTION_DISABLE_BEDTIME: "bedtime",
			ACTION_ENABLE_DAILY_LIMIT: "daily_limit", ACTION_DISABLE_DAILY_LIMIT: "daily_limit",
			ACTION_ENABLE_SCHOOL_TIME: "school_time", ACTION_DISABLE_SCHOOL_TIME: "school_time",
		}
		policy = policy_of_action.get(name)
		if policy and self.get_pending_time_limit_state(child_id, policy) is not None:
			return
		if name in (ACTION_LOCK_DEVICE, ACTION_UNLOCK_DEVICE) and device_id in self._pending_lock_states:
			return

		key = f"{child_id}:{name}:{device_id or ''}:{action.get('day') or ''}"
		now = time.time()
		if now - self._strict_cooldown.get(key, 0.0) < STRICT_MODE_COOLDOWN:
			_LOGGER.debug(f"Strict mode: {name} for {child_id}/{device_id} skipped, cooldown active")
			return
		self._strict_cooldown[key] = now

		_LOGGER.info(
			f"Strict mode: {name} for child {child_data.get('child_name', child_id)}"
			f"{f' device {device_id}' if device_id else ''} ({action.get('reason')})"
		)
		success = False
		try:
			if name == ACTION_CANCEL_BONUS:
				success = await self.client.async_cancel_time_bonus(
					override_id=action["override_id"], account_id=child_id
				)
			elif name in (ACTION_LOCK_DEVICE, ACTION_UNLOCK_DEVICE):
				# Direct client call: async_control_device() requests a refresh,
				# which must not run from inside the refresh in progress. The
				# next poll picks the new state up; the pending state covers the UI.
				google_action = DEVICE_LOCK_ACTION if name == ACTION_LOCK_DEVICE else DEVICE_UNLOCK_ACTION
				success = await self.client.async_control_device(device_id, google_action, child_id)
				if success:
					self._pending_lock_states[device_id] = (name == ACTION_LOCK_DEVICE, time.time())
					if action.get("clear_intent"):
						self.clear_device_intent(child_id, device_id)
					elif action.get("record"):
						self.record_device_intent(child_id, device_id, action["record"])
			elif name == ACTION_SET_BEDTIME:
				start, end = action["start"], action["end"]
				success = await self.client.async_set_bedtime(
					f"{start[0]:02d}:{start[1]:02d}", f"{end[0]:02d}:{end[1]:02d}",
					day=action["day"], account_id=child_id, scope="weekly",
				)
			elif name == ACTION_SET_DAILY_LIMIT:
				success = await self.client.async_set_daily_limit(
					daily_minutes=action["minutes"], device_id=device_id, account_id=child_id, day=action.get("day")
				)
			elif policy:
				enable = name in (ACTION_ENABLE_BEDTIME, ACTION_ENABLE_DAILY_LIMIT, ACTION_ENABLE_SCHOOL_TIME)
				client_calls = {
					("bedtime", True): self.client.async_enable_bedtime,
					("bedtime", False): self.client.async_disable_bedtime,
					("daily_limit", True): self.client.async_enable_daily_limit,
					("daily_limit", False): self.client.async_disable_daily_limit,
					("school_time", True): self.client.async_enable_school_time,
					("school_time", False): self.client.async_disable_school_time,
				}
				self.set_pending_time_limit_state(child_id, policy, enable)
				success = await client_calls[(policy, enable)](account_id=child_id)
				if not success:
					self.set_pending_time_limit_state(child_id, policy, None)
		except Exception as err:
			_LOGGER.error(f"Strict mode: {name} failed for child {child_id}: {err}")

		if not success:
			_LOGGER.warning(f"Strict mode: {name} for child {child_id} was not applied, will retry after cooldown")

		status = self.strict_mode_status.setdefault(child_id, {"actions_count": 0})
		status["actions_count"] += 1
		status["last_action"] = name
		status["last_action_at"] = dt_util.now().isoformat()
		status["last_reason"] = action.get("reason")
		status["last_device_id"] = device_id
		status["last_success"] = success

		self.hass.bus.async_fire(EVENT_STRICT_MODE_ACTION, {
			"child_id": child_id,
			"child_name": child_data.get("child_name"),
			"device_id": device_id,
			"action": name,
			"reason": action.get("reason"),
			"success": success,
		})

	async def async_cleanup(self) -> None:
		"""Clean up coordinator resources."""
		if self.client is not None:
			await self.client.async_cleanup()
			self.client = None

		_LOGGER.debug("Coordinator cleanup completed")
