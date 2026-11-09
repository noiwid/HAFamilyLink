"""Data update coordinator for Google Family Link integration."""
from __future__ import annotations

import asyncio
import copy
import logging
import time
from contextlib import asynccontextmanager
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
	CONF_LOCK_KEEPS_ALLOWED_APPS,
	DEFAULT_STRICT_MODE,
	DEFAULT_STRICT_MODE_RULES,
	DEFAULT_LOCK_KEEPS_ALLOWED_APPS,
	EVENT_STRICT_MODE_ACTION,
	STRICT_MODE_BONUS_GRACE,
	STRICT_MODE_COOLDOWN,
	STRICT_MODE_MAX_ATTEMPTS,
	CONF_ENABLE_LOCATION_TRACKING,
	CONF_UPDATE_INTERVAL,
	DEFAULT_UPDATE_INTERVAL,
	DEVICE_LOCK_ACTION,
	DEVICE_UNLOCK_ACTION,
	DOMAIN,
	LOGGER_NAME,
	WEBSITES_REFRESH,
)
from .exceptions import FamilyLinkException, SessionExpiredError
from .schedules import morning_window_from_yesterday
from .strict_mode import (
	ACTION_CANCEL_BONUS,
	ACTION_ENABLE_BEDTIME,
	ACTION_ENABLE_DAILY_LIMIT,
	ACTION_ENABLE_SCHOOL_TIME,
	ACTION_LOCK_DEVICE,
	ACTION_SET_BEDTIME,
	ACTION_SET_DAILY_LIMIT,
	ACTION_SET_WEEKLY_LIMIT,
	ACTION_UNLOCK_DEVICE,
	DEVICE_INTENT_AUTO_LOCK,
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


def _strict_key(action: dict[str, Any]) -> str:
	"""Identity of a corrective action, for its cooldown and its tries.

	Dated: a correction given up one day is tried again the next.
	"""
	return (
		f"{action['child_id']}:{action['action']}:{action.get('device_id') or ''}:"
		f"{action.get('day') or ''}:{dt_util.now().date().isoformat()}"
	)


class FamilyLinkDataUpdateCoordinator(DataUpdateCoordinator):
	"""Class to manage fetching data from the Family Link API."""

	def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
		"""Initialize the coordinator."""
		self.entry = entry
		# Options in force since this setup: the options listener reloads the
		# entry only when something other than the strict mode flag changed.
		self.applied_options: dict[str, Any] = dict(entry.options)
		self.client: FamilyLinkClient | None = None
		self._devices: dict[str, dict[str, Any]] = {}
		self._is_retrying_auth = False  # Prevent infinite retry loops
		self._auth_notification_sent = False  # Only send auth notification once
		self._pending_lock_states: dict[str, tuple[bool, float]] = {}  # device_id -> (locked, timestamp)
		self._pending_time_limit_states: dict[str, dict[str, tuple[bool, float]]] = {}  # child_id -> {"bedtime": (enabled, timestamp), "school_time": (enabled, timestamp), "daily_limit": (enabled, timestamp)}
		self._last_known_data: dict[str, Any] | None = None  # Cache for last successful fetch
		self.child_device_ids: dict[str, str] = {}  # child_id -> registry id of the child's hub device
		# Chrome site lists change rarely: read every WEBSITES_REFRESH seconds,
		# and taken from the answer of a change made from Home Assistant (store_websites).
		self._websites: dict[str, tuple[float, dict[str, Any] | None]] = {}  # child_id -> (read at, lists)
		self._websites_warned: set[str] = set()  # children whose last site list read failed (warned once)

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
		self._strict_attempts: dict[str, int] = {}  # action key -> tries in a row while still planned
		# Writes made from HA, keyed "child:policy" or device id: strict mode
		# leaves a target alone while one runs and for a moment after (D-038)
		self._ha_writes_running: dict[str, int] = {}
		self._ha_write_ended: dict[str, float] = {}
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
			# Fail the refresh instead of continuing with zero children. An empty
			# result creates no entities at startup and blanks every child's data
			# afterwards; raising lets _async_update_data return _last_known_data,
			# or raise UpdateFailed (ConfigEntryNotReady during setup) on first run.
			raise FamilyLinkException(f"Failed to fetch family members: {err}") from err

		if not supervised_children:
			if self._last_known_data and self._last_known_data.get("children_data"):
				# The read succeeded but lists no supervised child where the last
				# good refresh had some: a transient answer, not a family that lost
				# its children. Fail the refresh like a failed read, so
				# _async_update_data keeps _last_known_data instead of blanking
				# every child's entities and overwriting the cache with nothing.
				raise FamilyLinkException("Family members read returned no supervised children")
			_LOGGER.warning("No supervised children found — entities will not be created. Check your Family Link account configuration.")

		# Fetch data for each supervised child
		children_data = []
		for child in supervised_children:
			child_id = child.get("userId")
			if not child_id:
				# Field names only: the member record holds the child's name, e-mail and photo,
				# and logs end up pasted in public issues
				_LOGGER.warning("Skipping child with missing userId (fields: %s)", sorted(child))
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
			# The app's daily limit switch, None when not read (cache keeps the last)
			daily_limit_switch = None
			# "Allow apps with unlimited time during downtime", None when not reported
			downtime_unlimited_apps = None
			# Today-effective bedtime state derived from the per-day type-9
			# override in the timeLimit response (issue #113). This is the
			# authoritative source for the bedtime switch — it reflects the
			# "Only today" override Google actually applies — and takes
			# precedence over the appliedTimeLimits heuristic below.
			bedtime_enabled_today_from_rules = None
			school_time_enabled_today_from_rules = None
			school_time_today_override = None
			# Policy ids from the revisions, handed to the appliedTimeLimits
			# parser so UUID-keyed windows are classified by policy instead of
			# by list order (issue #151).
			bedtime_rule_id = None
			schooltime_rule_id = None
			# False when this refresh could not read the rules (cache or nothing):
			# strict mode then skips the child, there is nothing to correct on that basis
			time_limit_fresh = True

			try:
				time_limit_config = await self.client.async_get_time_limit(account_id=child_id)
				bedtime_enabled = time_limit_config.get("bedtime_enabled")
				school_time_enabled = time_limit_config.get("school_time_enabled")
				bedtime_rule_id = time_limit_config.get("bedtime_rule_id")
				schooltime_rule_id = time_limit_config.get("schooltime_rule_id")
				bedtime_enabled_today_from_rules = time_limit_config.get("bedtime_enabled_today")
				school_time_enabled_today_from_rules = time_limit_config.get("school_time_enabled_today")
				school_time_today_override = time_limit_config.get("school_time_today_override")
				bedtime_schedule = time_limit_config.get("bedtime_schedule")
				school_time_schedule = time_limit_config.get("school_time_schedule")
				daily_limit_week_rows = time_limit_config.get("daily_limit_week")
				daily_limit_switch = time_limit_config.get("daily_limit_enabled")
				downtime_unlimited_apps = time_limit_config.get("downtime_unlimited_apps")
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
				time_limit_fresh = False
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
							daily_limit_switch = cached_child.get("daily_limit_enabled")
							downtime_unlimited_apps = cached_child.get("downtime_unlimited_apps")
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
			applied_limits_fresh = True

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
				applied_limits_fresh = False
				# Try to recover from last known data cache
				if self._last_known_data:
					for cached_child in self._last_known_data.get("children_data", []):
						if cached_child.get("child_id") == child_id:
							devices_time_data = cached_child.get("devices_time_data", {})
							# Without it every device would read unlocked for this poll
							device_lock_states = {
								device["id"]: device.get("locked", False)
								for device in cached_child.get("devices") or []
								if device.get("id")
							}
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
			# The morning of an overnight window read on today's row: yesterday's
			# weekly row decides (#229). Before the policy gate, which still wins.
			for time_data in devices_time_data.values():
				for kind, schedule in (("bedtime", bedtime_schedule), ("schooltime", school_time_schedule)):
					window = (time_data or {}).get(f"{kind}_window") or {}
					if not window.pop("morning_from_today_row", False):
						continue
					fixed = morning_window_from_yesterday(window, schedule, dt_util.now())
					if fixed:
						time_data[f"{kind}_window"], time_data[f"{kind}_active"] = fixed
			_gate_windows_on_policy_state(
				devices_time_data, bedtime_enabled_today, schooltime_enabled_today, child_name
			)

			# Update device cache with real lock states from API
			current_time = time.time()
			for device in devices:
				device_id = device["id"]

				# Check if we have a pending lock state change (within last 5 seconds).
				# Only the lock state is provisional: the time data below must be
				# copied whatever the lock state, otherwise the refresh that follows
				# a lock or unlock from HA leaves the device without its daily limit
				# fields and the child-level daily_limit_enabled aggregate reads
				# False for one poll (the switch blinked off, and strict mode
				# "re-enabled" a limit nobody had touched).
				locked = device_lock_states.get(device_id, False)
				if device_id in self._pending_lock_states:
					pending_locked, timestamp = self._pending_lock_states[device_id]
					age = current_time - timestamp

					if age < 5.0:  # Use pending state for 5 seconds
						locked = pending_locked
						_LOGGER.debug(
							f"Using pending lock state for {device_id}: {pending_locked} "
							f"(age: {age:.1f}s, API says: {device_lock_states.get(device_id)})"
						)
					else:
						# Expired, remove from pending
						del self._pending_lock_states[device_id]

				# Use real lock state from API if available, otherwise default to False
				device["locked"] = locked

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
			# If ANY device has daily_limit enabled, consider it globally enabled;
			# unknown (None) when no device reports today's row
			states = [device.get("daily_limit_enabled") for device in devices]
			daily_limit_enabled = True if True in states else (False if False in states else None)
			# The app's switch wins when it was read: today's rows keep an
			# override's "on" after the limit is switched off
			if daily_limit_switch is not None:
				daily_limit_enabled = daily_limit_switch
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
						_LOGGER.debug(f"Fetched location for {child_name}")
				except SessionExpiredError:
					raise  # Re-raise to trigger auth notification
				except Exception as err:
					_LOGGER.warning(f"Failed to fetch location data for {child_name}: {err}")
					# Keep the last position: a cleared one sends the tracker to
					# unknown and fires zone automations on a Google hiccup
					for cached_child in (self._last_known_data or {}).get("children_data", []):
						if cached_child.get("child_id") == child_id:
							location = cached_child.get("location")
							break

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

			# Battery of each device. One call per child; on a transient error
			# keep the last readings.
			device_batteries = {}
			try:
				device_batteries = await self.client.async_get_device_batteries(account_id=child_id)
			except SessionExpiredError:
				raise  # Re-raise to trigger auth notification
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch device batteries for {child_name}: {err}")
				for cached_child in (self._last_known_data or {}).get("children_data", []):
					if cached_child.get("child_id") == child_id:
						device_batteries = cached_child.get("device_batteries", {})
						break

			websites = await self._async_child_websites(child_id, child_name)

			# Store data for this child
			child_data = {
				"child": child,
				"child_id": child_id,
				"child_name": child_name,
				"devices": devices,
				"time_limit_fresh": time_limit_fresh,
				"applied_limits_fresh": applied_limits_fresh,
				"screen_time": screen_time,
				"location": location,
				"contact_restriction": contact_restriction,
				"device_batteries": device_batteries,
				"websites": websites,
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
				# Today's explicit school time override from timeLimit (True on, False
				# off), None when none: tells strict mode a "today only" change apart
				# from a day without school time
				"school_time_today_override": school_time_today_override,
				"bedtime_schedule": bedtime_schedule,
				"school_time_schedule": school_time_schedule,
				"daily_limit_week": daily_limit_week_rows,
				"daily_limit_enabled": daily_limit_enabled,
				"downtime_unlimited_apps": downtime_unlimited_apps,
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
			self.client.lock_keeps_allowed_apps = bool(self.entry.options.get(
				CONF_LOCK_KEEPS_ALLOWED_APPS,
				self.entry.data.get(CONF_LOCK_KEEPS_ALLOWED_APPS, DEFAULT_LOCK_KEEPS_ALLOWED_APPS),
			))

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

			async with self._ha_write(device_id):
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
			# The per-device daily limit reference of earlier builds is replaced
			# by the seven weekday quotas (daily_limit_week).
			for entry in self._strict_intents.values():
				if isinstance(entry, dict) and isinstance(entry.get("values"), dict):
					entry["values"].pop("daily_limit", None)
					# 2026-09-03: effective-minutes reference replaced by the weekly values
					entry["values"].pop("daily_limit_week", None)
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
		protection of the lock rule resumes. A lock strict mode placed itself
		is carried over one midnight, no more: it is lifted when the
		restriction it protects ends, and a bedtime crossing midnight ends the
		next morning, but a lock rule switched off meanwhile must not lift a
		lock days later. "carried" lists the locks already carried once.
		"""
		now = dt_util.now().date()
		today = now.isoformat()
		yesterday = (now - timedelta(days=1)).isoformat()
		entry = self._strict_intents.get(child_id)
		if not entry:
			entry = {"date": today, "policies": {}, "devices": {}, "values": {}}
			self._strict_intents[child_id] = entry
		elif entry.get("date") != today:
			kept = entry.get("date") == yesterday
			carried = set(entry.get("carried") or [])
			entry["date"] = today
			entry["devices"] = {
				device_id: intent
				for device_id, intent in (entry.get("devices") or {}).items()
				if kept and intent == DEVICE_INTENT_AUTO_LOCK and device_id not in carried
			}
			entry["carried"] = list(entry["devices"])
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

	@asynccontextmanager
	async def _ha_write(self, key: str):
		"""Mark a write from HA as running on ``key`` (see _ha_write_recent)."""
		self._ha_writes_running[key] = self._ha_writes_running.get(key, 0) + 1
		try:
			yield
		finally:
			self._ha_writes_running[key] -= 1
			self._ha_write_ended[key] = time.time()

	def _ha_write_recent(self, key: str) -> bool:
		"""A write from HA on ``key`` runs, or ended too recently for Google to show it."""
		return self._ha_writes_running.get(key, 0) > 0 or time.time() - self._ha_write_ended.get(key, 0.0) < 5.0

	async def async_set_policy(self, child_id: str, policy: str, enable: bool) -> bool:
		"""Switch bedtime, school time or the daily limit from HA, as the parent's decision of the day."""
		method = getattr(self.client, f"async_{'enable' if enable else 'disable'}_{policy}")
		async with self._ha_write(f"{child_id}:{policy}"):
			success = await method(account_id=child_id)
			if success:
				self.record_policy_intent(child_id, policy, enable)
		return success

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
		entry = self._intents_for(child_id)
		entry["devices"][device_id] = action
		# Recorded today: no longer a lock carried over from yesterday
		if device_id in (entry.get("carried") or []):
			entry["carried"].remove(device_id)
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

	async def _async_child_websites(self, child_id: str, child_name: str) -> dict[str, Any] | None:
		"""The child's Chrome site lists, read at most every WEBSITES_REFRESH seconds.

		On an error the last lists read are kept; None until a first read works.
		A failed read is retried after WEBSITES_REFRESH too, not on every refresh:
		an account without "Google Chrome and Web" fails for good, and would
		otherwise cost a call and a log line per refresh. Warned once per child.
		"""
		cached = self._websites.get(child_id)
		if cached and time.monotonic() - cached[0] < WEBSITES_REFRESH:
			return cached[1]
		try:
			lists = await self.client.async_get_website_restrictions(child_id)
		except SessionExpiredError:
			raise
		except Exception as err:
			previous = cached[1] if cached else None
			self._websites[child_id] = (time.monotonic(), previous)
			if child_id in self._websites_warned:
				_LOGGER.debug(f"Failed to fetch website restrictions for {child_name} again: {err}")
			else:
				self._websites_warned.add(child_id)
				_LOGGER.warning(
					f"Failed to fetch website restrictions for {child_name}: {err}. "
					f"Retried every {WEBSITES_REFRESH // 60} minutes, logged at debug level from now on"
				)
			return previous
		self._websites_warned.discard(child_id)
		self._websites[child_id] = (time.monotonic(), lists)
		return lists

	def store_websites(self, child_id: str, lists: dict[str, Any]) -> None:
		"""Keep the lists an update returned, so entities show them without a new read."""
		self._websites[child_id] = (time.monotonic(), {k: lists.get(k) for k in ("filter_level", "approved", "blocked")})

	def record_daily_limit_minutes(
		self, child_id: str | None, minutes: int, day: int | None = None, limit_on: bool = True
	) -> tuple[int | None, bool | None] | None:
		"""A weekday quota set from HA becomes the reference for that weekday (strict mode).

		Call it BEFORE writing to Google: the write verifies the applied value
		for several seconds, and a refresh in between must not find the old
		reference and put the old quota back. Returns what it replaced (the
		weekday quota and the daily limit reference, None when absent) for
		restore_daily_limit_minutes; None without a child.
		"""
		child_id = self._resolve_child_id(child_id)
		if not child_id:
			return None
		if not (isinstance(day, int) and 1 <= day <= 7):
			day = dt_util.now().isoweekday()
		intents = self._intents_for(child_id)
		limits = intents.setdefault("values", {}).setdefault("weekly_limits", {})
		previous = (limits.get(str(day)), intents["policies"].get("daily_limit"))
		limits[str(day)] = int(minutes)
		# A quota set while the limit is switched off only changes the schedule:
		# the limit stays off (limit_on False) and so does its reference
		if limit_on:
			intents["policies"]["daily_limit"] = True
		self._save_strict_intents()
		return previous

	def restore_daily_limit_minutes(
		self, child_id: str | None, day: int, previous: tuple[int | None, bool | None] | None
	) -> None:
		"""Undo record_daily_limit_minutes after a write Google did not take."""
		child_id = self._resolve_child_id(child_id)
		if not child_id or previous is None:
			return
		minutes, limit_on = previous
		intents = self._intents_for(child_id)
		limits = intents.setdefault("values", {}).setdefault("weekly_limits", {})
		if minutes is None:
			limits.pop(str(day), None)
		else:
			limits[str(day)] = int(minutes)
		# Nothing reached Google: the limit is still what the parent had chosen
		if limit_on is None:
			intents["policies"].pop("daily_limit", None)
		else:
			intents["policies"]["daily_limit"] = limit_on
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
		# Deep copies: the switch attributes must not share the nested dicts,
		# or an in-place update of a reference leaves the last state unchanged
		# in HA's eyes and the attributes go stale.
		return {
			"policies": dict(entry.get("policies", {})),
			"devices": dict(devices),
			"values": copy.deepcopy(entry.get("values", {})),
		}

	def restore_ha_bonus(self, device_id: str, previous: float | None) -> None:
		"""Undo register_ha_bonus after a bonus Google did not take."""
		if previous is None:
			self._ha_bonus_until.pop(device_id, None)
		else:
			self._ha_bonus_until[device_id] = previous
		self._save_strict_intents()

	def register_ha_bonus(self, device_id: str, minutes: int) -> float | None:
		"""Record a bonus granted from Home Assistant so strict mode leaves it alone.

		Strict mode reverts what is done from the Family Link side; a bonus the
		parent gives through the buttons or the add_time_bonus action is the
		parent's decision and must survive. The allowance lasts the bonus
		duration plus a short grace period. Returns the previous allowance, for
		restore_ha_bonus.
		"""
		previous = self._ha_bonus_until.get(device_id)
		self._ha_bonus_until[device_id] = time.time() + max(int(minutes), 0) * 60 + STRICT_MODE_BONUS_GRACE
		self._save_strict_intents()
		_LOGGER.debug(f"Strict mode: bonus of {minutes} min granted from HA on {device_id}, protected")
		return previous

	def _ha_bonus_devices(self) -> frozenset[str]:
		"""Devices whose HA-granted bonus is still running (expired entries pruned)."""
		now = time.time()
		self._ha_bonus_until = {d: t for d, t in self._ha_bonus_until.items() if t > now}
		return frozenset(self._ha_bonus_until)

	def apply_strict_mode_option(self, enabled: bool) -> None:
		"""The Strict mode option drives the switch of every child."""
		self.strict_mode_default = bool(enabled)
		for child_data in (self.data or {}).get("children_data", []):
			child_id = child_data.get("child_id")
			if child_id and self._strict_mode_children.get(child_id) != bool(enabled):
				self.set_strict_mode(child_id, bool(enabled))
		self.async_update_listeners()

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
			if child_data.get("time_limit_fresh") is False or child_data.get("applied_limits_fresh") is False:
				# A refresh that could not read the rules or the applied limits:
				# neither a reference to take from Google nor anything to correct
				_LOGGER.debug(f"Strict mode: refresh incomplete for {child_id}, evaluation skipped")
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
					child_data, self.strict_rules, self._ha_bonus_devices(), intents,
					today=dt_util.now().isoweekday(),
				)
				planned = copy.deepcopy({"policies": intents["policies"], "devices": intents["devices"]})
			except Exception as err:
				_LOGGER.warning(f"Strict mode: could not evaluate child {child_id}: {err}")
				continue
			# A correction no longer planned took effect (or is moot): its count restarts
			planned_keys = {_strict_key(a) for a in actions}
			for key in [k for k in self._strict_attempts if k.startswith(f"{child_id}:") and k not in planned_keys]:
				del self._strict_attempts[key]
			today_key = dt_util.now().date().isoformat()
			self._strict_cooldown = {k: t for k, t in self._strict_cooldown.items() if k.endswith(today_key)}
			for action in actions:
				await self._async_run_strict_action(child_data, action, planned)

	async def _async_run_strict_action(
		self, child_data: dict[str, Any], action: dict[str, Any], planned: dict[str, Any] | None = None
	) -> None:
		"""Execute one corrective action, with the same guards as the switches."""
		child_id = action["child_id"]
		name = action["action"]
		device_id = action.get("device_id")

		# A change Home Assistant itself just made is still propagating on
		# Google's side: do not fight our own pending state.
		# Strict mode only ever switches a restriction back on
		policy_of_action = {
			ACTION_ENABLE_BEDTIME: "bedtime",
			ACTION_ENABLE_DAILY_LIMIT: "daily_limit",
			ACTION_ENABLE_SCHOOL_TIME: "school_time",
		}
		policy = policy_of_action.get(name)
		if policy and self.get_pending_time_limit_state(child_id, policy) is not None:
			return
		if name in (ACTION_LOCK_DEVICE, ACTION_UNLOCK_DEVICE) and device_id in self._pending_lock_states:
			return
		# The parent's own clicks: a write from HA still running or just
		# done (the refresh may predate it), or a decision taken after this
		# plan was made (earlier actions take seconds each)
		if policy:
			target, kind = policy, "policies"
			if self._ha_write_recent(f"{child_id}:{policy}"):
				return
		elif name in (ACTION_LOCK_DEVICE, ACTION_UNLOCK_DEVICE):
			target, kind = device_id, "devices"
			if self._ha_write_recent(device_id):
				return
		else:
			kind = None
		if kind and planned is not None and self._intents_for(child_id)[kind].get(target) != planned[kind].get(target):
			_LOGGER.debug(f"Strict mode: {name} for {child_id} dropped, decided otherwise from HA since")
			return

		key = _strict_key(action)
		now = time.time()
		if now - self._strict_cooldown.get(key, 0.0) < STRICT_MODE_COOLDOWN:
			_LOGGER.debug(f"Strict mode: {name} for {child_id}/{device_id} skipped, cooldown active")
			return
		# Google answers 200 to writes it does not apply: a correction still
		# planned after a few tries is given up instead of looping all night
		attempts = self._strict_attempts.get(key, 0)
		if attempts >= STRICT_MODE_MAX_ATTEMPTS:
			_LOGGER.debug(f"Strict mode: {name} for {child_id}/{device_id} given up, no effect after {attempts} tries")
			return
		self._strict_attempts[key] = attempts + 1
		if attempts + 1 == STRICT_MODE_MAX_ATTEMPTS:
			_LOGGER.warning(
				f"Strict mode: {name} for child {child_data.get('child_name', child_id)} had no effect "
				f"after {STRICT_MODE_MAX_ATTEMPTS} tries, given up until the state changes ({action.get('reason')})"
			)
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
			elif name == ACTION_SET_WEEKLY_LIMIT:
				success = await self.client.async_set_weekly_daily_limit(
					action["day"], action["minutes"], child_id
				)
			elif name == ACTION_SET_DAILY_LIMIT:
				success = await self.client.async_set_daily_limit(
					daily_minutes=action["minutes"], device_id=device_id, account_id=child_id, day=action.get("day")
				)
			elif policy:
				self.set_pending_time_limit_state(child_id, policy, True)
				# School time goes back to the weekly schedule: async_enable_school_time
				# posts an override "now -> 23:59", school time until midnight
				enable_call = (
					self.client.async_restore_school_time if policy == "school_time"
					else getattr(self.client, f"async_enable_{policy}")
				)
				success = await enable_call(account_id=child_id)
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

		device_name = next(
			(d.get("name") for d in child_data.get("devices") or [] if isinstance(d, dict) and d.get("id") == device_id),
			None,
		)
		created_by = self._member_name(
			((child_data.get("devices_time_data") or {}).get(device_id) or {}).get("override_by")
		) if device_id and name in (ACTION_CANCEL_BONUS, ACTION_LOCK_DEVICE) else None
		status["last_created_by"] = created_by
		if created_by:
			_LOGGER.warning(f"Strict mode: the override countered by {name} was created by {created_by}")
		self.hass.bus.async_fire(EVENT_STRICT_MODE_ACTION, {
			"child_id": child_id,
			"child_name": child_data.get("child_name"),
			"device_id": device_id,
			"device_name": device_name,
			"action": name,
			"reason": action.get("reason"),
			"success": success,
			# Account that created the bonus or unlock override countered (None
			# when Google gives none, e.g. a lock lifted without any override)
			"created_by": created_by,
			# Structured details for notifications: weekday (1 = Monday), minutes,
			# bedtime bounds, and what Google reported before the correction.
			"day": action.get("day"),
			"minutes": action.get("minutes"),
			"start": action.get("start"),
			"end": action.get("end"),
			"observed": action.get("observed"),
		})

	def _member_name(self, user_id: str | None) -> str | None:
		"""Family member's display name for a Google user id, the id when unknown."""
		if not user_id:
			return None
		for member in (self.data or {}).get("family_members") or []:
			if isinstance(member, dict) and member.get("userId") == user_id:
				return (member.get("profile") or {}).get("displayName") or user_id
		return user_id

	async def async_cleanup(self) -> None:
		"""Clean up coordinator resources."""
		if self.client is not None:
			await self.client.async_cleanup()
			self.client = None

		_LOGGER.debug("Coordinator cleanup completed")
