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

			# Fetch device data
			devices = await self.client.async_get_devices()

			# Update internal device cache
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

			_LOGGER.debug("Successfully updated device data: %d devices", len(devices))
			return {
				"devices": devices,
				"screen_time": screen_time,
			}

		except SessionExpiredError:
			_LOGGER.warning("Session expired, attempting to refresh authentication")
			await self._async_refresh_auth()
			raise UpdateFailed("Session expired, please re-authenticate")

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
				# Update local cache immediately for responsive UI
				if device_id in self._devices:
					self._devices[device_id]["locked"] = (action == "lock")
				
				# Schedule a data refresh to get latest state
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