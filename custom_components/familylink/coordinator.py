"""Data update coordinator for Google Family Link integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client.api import FamilyLinkClient
from .const import (
	DEFAULT_UPDATE_INTERVAL,
	DOMAIN,
	LOGGER_NAME,
)
from .exceptions import FamilyLinkException, SessionExpiredError

_LOGGER = logging.getLogger(LOGGER_NAME)


class FamilyLinkDataUpdateCoordinator(DataUpdateCoordinator):
	"""Class to manage fetching data from the Family Link API."""

	def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
		"""Initialize the coordinator."""
		self.entry = entry
		self.client: FamilyLinkClient | None = None
		self._devices: dict[str, dict[str, Any]] = {}
		self._is_retrying_auth = False  # Prevent infinite retry loops
		self._pending_lock_states: dict[str, tuple[bool, float]] = {}  # device_id -> (locked, timestamp)
		self._pending_time_limit_states: dict[str, dict[str, tuple[bool, float]]] = {}  # child_id -> {"bedtime": (enabled, timestamp), "school_time": (enabled, timestamp), "daily_limit": (enabled, timestamp)}

		super().__init__(
			hass,
			_LOGGER,
			name=DOMAIN,
			update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
		)

	async def _async_update_data(self) -> dict[str, Any]:
		"""Fetch data from Family Link API."""
		try:
			return await self._async_fetch_data()

		except SessionExpiredError as err:
			# Prevent infinite retry loops
			if self._is_retrying_auth:
				_LOGGER.error("Session still expired after refresh - cookies are invalid")
				raise UpdateFailed("Session expired, please re-authenticate via Family Link Auth add-on") from err

			_LOGGER.warning("Session expired, attempting to refresh authentication")
			self._is_retrying_auth = True

			try:
				await self._async_refresh_auth()

				# Retry ONCE after refreshing authentication
				_LOGGER.info("Retrying data fetch after authentication refresh...")
				result = await self._async_fetch_data()
				self._is_retrying_auth = False  # Reset flag on success
				return result

			except SessionExpiredError:
				# If it still fails after refresh, cookies are truly invalid
				_LOGGER.error("Session still expired after refresh - please re-authenticate via add-on")
				raise UpdateFailed("Session expired, please re-authenticate via Family Link Auth add-on") from err
			except Exception as retry_err:
				_LOGGER.error(f"Retry after auth refresh failed: {retry_err}")
				raise UpdateFailed(f"Failed after auth refresh: {retry_err}") from retry_err
			finally:
				self._is_retrying_auth = False  # Always reset flag

		except FamilyLinkException as err:
			_LOGGER.error("Error fetching Family Link data: %s", err)
			raise UpdateFailed(f"Error communicating with Family Link: {err}") from err

		except Exception as err:
			_LOGGER.exception("Unexpected error fetching Family Link data")
			raise UpdateFailed(f"Unexpected error: {err}") from err

	async def _async_fetch_data(self) -> dict[str, Any]:
		"""Perform the actual data fetch from Family Link API."""
		if self.client is None:
			await self._async_setup_client()

		# Initialize empty device cache (will be populated per-child below)
		self._devices = {}

		# Fetch family members info
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
		except Exception as err:
			_LOGGER.warning(f"Failed to fetch family members: {err}")

		# Fetch data for each supervised child
		children_data = []
		for child in supervised_children:
			child_id = child["userId"]
			child_name = child.get("profile", {}).get("displayName", "Unknown")

			_LOGGER.debug(f"Fetching data for child: {child_name} (ID: {child_id})")

			# Fetch complete apps and usage data for this child
			apps_usage_data = None
			try:
				apps_usage_data = await self.client.async_get_apps_and_usage(account_id=child_id)
				_LOGGER.debug(
					f"Fetched for {child_name}: {len(apps_usage_data.get('apps', []))} apps, "
					f"{len(apps_usage_data.get('deviceInfo', []))} devices, "
					f"{len(apps_usage_data.get('appUsageSessions', []))} usage sessions"
				)
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch apps and usage data for {child_name}: {err}")

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

			# Fetch time limit configuration (bedtime/school time schedules and enabled states)
			bedtime_enabled = None
			school_time_enabled = None
			bedtime_schedule = None
			school_time_schedule = None

			try:
				time_limit_config = await self.client.async_get_time_limit(account_id=child_id)
				bedtime_enabled = time_limit_config.get("bedtime_enabled")
				school_time_enabled = time_limit_config.get("school_time_enabled")
				bedtime_schedule = time_limit_config.get("bedtime_schedule")
				school_time_schedule = time_limit_config.get("school_time_schedule")
				_LOGGER.debug(
					f"Fetched time limit config for {child_name}: "
					f"bedtime={bedtime_enabled}, school_time={school_time_enabled}"
				)
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch time limit config for {child_name}: {err}")

			# Fetch applied time limits (lock states and per-device time data)
			device_lock_states = {}
			devices_time_data = {}

			try:
				applied_limits_data = await self.client.async_get_applied_time_limits(account_id=child_id)
				device_lock_states = applied_limits_data.get("device_lock_states", {})
				devices_time_data = applied_limits_data.get("devices", {})
				_LOGGER.debug(
					f"Fetched applied time limits for {child_name}: "
					f"{len(device_lock_states)} device lock states, "
					f"{len(devices_time_data)} devices with time data"
				)
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch applied time limits for {child_name}: {err}")

			# Update device cache with real lock states from API
			import time
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

			# Fetch daily screen time data for this child
			screen_time = None
			try:
				screen_time = await self.client.async_get_daily_screen_time(account_id=child_id)
				_LOGGER.debug(
					f"Successfully fetched screen time for {child_name}: {screen_time['formatted']} "
					f"({len(screen_time['app_breakdown'])} apps)"
				)
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch screen time data for {child_name}: {err}")

			# Store data for this child
			child_data = {
				"child": child,
				"child_id": child_id,
				"child_name": child_name,
				"devices": devices,
				"screen_time": screen_time,
				"apps": apps_usage_data.get("apps", []) if apps_usage_data else [],
				"app_usage_sessions": apps_usage_data.get("appUsageSessions", []) if apps_usage_data else [],
				"bedtime_enabled": bedtime_enabled,
				"school_time_enabled": school_time_enabled,
				"bedtime_schedule": bedtime_schedule,
				"school_time_schedule": school_time_schedule,
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
			# Import here to avoid circular imports
			from .client.api import FamilyLinkClient

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

				# Store the expected lock state temporarily (for 5 seconds)
				# This ensures the UI reflects the change immediately, even if the API
				# takes time to propagate the state
				import time
				from .const import DEVICE_LOCK_ACTION
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

	def set_pending_time_limit_state(self, child_id: str, limit_type: str, enabled: bool) -> None:
		"""Set a pending time limit state to reflect UI changes immediately.

		Args:
			child_id: The child's user ID
			limit_type: One of "bedtime", "school_time", or "daily_limit"
			enabled: Whether the limit is being enabled (True) or disabled (False)
		"""
		import time

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
		import time

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

	async def async_cleanup(self) -> None:
		"""Clean up coordinator resources."""
		if self.client is not None:
			await self.client.async_cleanup()
			self.client = None

		_LOGGER.debug("Coordinator cleanup completed")
