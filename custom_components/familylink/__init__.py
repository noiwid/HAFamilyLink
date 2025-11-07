"""The Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator
from .exceptions import FamilyLinkException

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Set up Google Family Link from a config entry."""
	_LOGGER.debug("Setting up Family Link integration")

	try:
		# Create coordinator for data updates
		coordinator = FamilyLinkDataUpdateCoordinator(hass, entry)
		
		# Perform initial data fetch
		await coordinator.async_config_entry_first_refresh()
		
		# Store coordinator in hass data
		hass.data.setdefault(DOMAIN, {})
		hass.data[DOMAIN][entry.entry_id] = coordinator

		# Forward setup to platforms
		await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

		_LOGGER.info("Successfully set up Family Link integration")
		return True

	except FamilyLinkException as err:
		_LOGGER.error("Failed to set up Family Link: %s", err)
		raise ConfigEntryNotReady from err
	except Exception as err:
		_LOGGER.exception("Unexpected error setting up Family Link: %s", err)
		raise ConfigEntryNotReady from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	_LOGGER.debug("Unloading Family Link integration")

	# Unload platforms
	unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

	if unload_ok:
		# Remove coordinator from hass data
		coordinator = hass.data[DOMAIN].pop(entry.entry_id)
		
		# Clean up coordinator resources
		if hasattr(coordinator, 'async_cleanup'):
			await coordinator.async_cleanup()

	return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Reload config entry."""
	await async_unload_entry(hass, entry)
	await async_setup_entry(hass, entry) 