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

		super().__init__(
			hass,
			_LOGGER,
			name=DOMAIN,
			update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
		)

	async def _async_update_data(self) -> dict[str, Any]:
		"""Fetch data from Family Link API."""
		try:
			if self.client is None:
				await self._async_setup_client()

			# Fetch complete apps and usage data (includes devices, apps, and usage)
			apps_usage_data = None
			try:
				apps_usage_data = await self.client.async_get_apps_and_usage()
				_LOGGER.debug(
					f"Fetched {len(apps_usage_data.get('apps', []))} apps, "
					f"{len(apps_usage_data.get('deviceInfo', []))} devices, "
					f"{len(apps_usage_data.get('appUsageSessions', []))} usage sessions"
				)
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch apps and usage data: {err}")

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
					}
					devices.append(device)

			# Fetch real lock states from appliedTimeLimits API
			device_lock_states = {}
			try:
				device_lock_states = await self.client.async_get_applied_time_limits()
				_LOGGER.debug(f"Fetched lock states for {len(device_lock_states)} devices")
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch device lock states: {err}")

			# Update device cache with real lock states from API
			for device in devices:
				device_id = device["id"]
				# Use real lock state from API if available, otherwise default to False
				device["locked"] = device_lock_states.get(device_id, False)

			self._devices = {device["id"]: device for device in devices}

			# Fetch daily screen time data
			screen_time = None
			try:
				screen_time = await self.client.async_get_daily_screen_time()
				_LOGGER.debug(
					f"Successfully fetched screen time: {screen_time['formatted']} "
					f"({len(screen_time['app_breakdown'])} apps)"
				)
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch screen time data: {err}")
				# Don't fail entire update if screen time fetch fails

			# Fetch family members info
			family_members = None
			supervised_child = None
			try:
				members_data = await self.client.async_get_family_members()
				family_members = members_data.get("members", [])

				# Find supervised child
				for member in family_members:
					supervision_info = member.get("memberSupervisionInfo")
					if supervision_info and supervision_info.get("isSupervisedMember"):
						supervised_child = member
						break

				_LOGGER.debug(f"Fetched {len(family_members)} family members")
			except Exception as err:
				_LOGGER.warning(f"Failed to fetch family members: {err}")

			_LOGGER.debug("Successfully updated all Family Link data")
			return {
				"devices": devices,
				"screen_time": screen_time,
				"apps": apps_usage_data.get("apps", []) if apps_usage_data else [],
				"app_usage_sessions": apps_usage_data.get("appUsageSessions", []) if apps_usage_data else [],
				"family_members": family_members,
				"supervised_child": supervised_child,
			}

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
				result = await self._async_update_data()
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
		self, device_id: str, action: str
	) -> bool:
		"""Control a Family Link device."""
		if self.client is None:
			await self._async_setup_client()

		try:
			success = await self.client.async_control_device(device_id, action)

			if success:
				_LOGGER.info(f"Successfully {action}ed device {device_id}")
				# Schedule a data refresh to get latest state from API
				await asyncio.sleep(1)  # Brief delay for state to propagate
				await self.async_request_refresh()

			return success

		except Exception as err:
			_LOGGER.error("Failed to control device %s: %s", device_id, err)
			return False

	async def async_get_device(self, device_id: str) -> dict[str, Any] | None:
		"""Get device data by ID."""
		return self._devices.get(device_id)

	async def async_cleanup(self) -> None:
		"""Clean up coordinator resources."""
		if self.client is not None:
			await self.client.async_cleanup()
			self.client = None

		_LOGGER.debug("Coordinator cleanup completed") 