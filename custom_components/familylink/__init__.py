"""The Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator
from .exceptions import FamilyLinkException

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

# Service schemas
SERVICE_BLOCK_DEVICE_FOR_SCHOOL = "block_device_for_school"
SERVICE_UNBLOCK_ALL_APPS = "unblock_all_apps"
SERVICE_BLOCK_APP = "block_app"
SERVICE_UNBLOCK_APP = "unblock_app"

SCHEMA_BLOCK_DEVICE_FOR_SCHOOL = vol.Schema({
	vol.Optional("whitelist"): vol.All(cv.ensure_list, [cv.string]),
})

SCHEMA_BLOCK_APP = vol.Schema({
	vol.Required("package_name"): cv.string,
})

SCHEMA_UNBLOCK_APP = vol.Schema({
	vol.Required("package_name"): cv.string,
})


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

		# Register services
		await async_setup_services(hass, coordinator)

		_LOGGER.info("Successfully set up Family Link integration")
		return True

	except FamilyLinkException as err:
		_LOGGER.error("Failed to set up Family Link: %s", err)
		raise ConfigEntryNotReady from err
	except Exception as err:
		_LOGGER.exception("Unexpected error setting up Family Link: %s", err)
		raise ConfigEntryNotReady from err


async def async_setup_services(hass: HomeAssistant, coordinator: FamilyLinkDataUpdateCoordinator) -> None:
	"""Set up services for Family Link."""

	async def handle_block_device_for_school(call: ServiceCall) -> None:
		"""Handle block_device_for_school service call."""
		_LOGGER.info("Service called: block_device_for_school")
		whitelist = call.data.get("whitelist")

		try:
			result = await coordinator.client.async_block_device_for_school(whitelist=whitelist)
			_LOGGER.info(
				f"School mode activated: {result['blocked_count']} apps blocked, "
				f"{result['failed_count']} failed"
			)
			# Refresh coordinator data
			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Failed to block device for school: {err}")
			raise

	async def handle_unblock_all_apps(call: ServiceCall) -> None:
		"""Handle unblock_all_apps service call."""
		_LOGGER.info("Service called: unblock_all_apps")

		try:
			result = await coordinator.client.async_unblock_all_apps()
			_LOGGER.info(
				f"All apps unblocked: {result['unblocked_count']} apps unblocked, "
				f"{result['failed_count']} failed"
			)
			# Refresh coordinator data
			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Failed to unblock all apps: {err}")
			raise

	async def handle_block_app(call: ServiceCall) -> None:
		"""Handle block_app service call."""
		package_name = call.data["package_name"]
		_LOGGER.info(f"Service called: block_app for {package_name}")

		try:
			success = await coordinator.client.async_block_app(package_name)
			if success:
				_LOGGER.info(f"Successfully blocked app: {package_name}")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error(f"Failed to block app: {package_name}")
		except Exception as err:
			_LOGGER.error(f"Error blocking app {package_name}: {err}")
			raise

	async def handle_unblock_app(call: ServiceCall) -> None:
		"""Handle unblock_app service call."""
		package_name = call.data["package_name"]
		_LOGGER.info(f"Service called: unblock_app for {package_name}")

		try:
			success = await coordinator.client.async_unblock_app(package_name)
			if success:
				_LOGGER.info(f"Successfully unblocked app: {package_name}")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error(f"Failed to unblock app: {package_name}")
		except Exception as err:
			_LOGGER.error(f"Error unblocking app {package_name}: {err}")
			raise

	# Register services
	hass.services.async_register(
		DOMAIN,
		SERVICE_BLOCK_DEVICE_FOR_SCHOOL,
		handle_block_device_for_school,
		schema=SCHEMA_BLOCK_DEVICE_FOR_SCHOOL,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_UNBLOCK_ALL_APPS,
		handle_unblock_all_apps,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_BLOCK_APP,
		handle_block_app,
		schema=SCHEMA_BLOCK_APP,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_UNBLOCK_APP,
		handle_unblock_app,
		schema=SCHEMA_UNBLOCK_APP,
	)

	_LOGGER.debug("Family Link services registered")


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

		# Unregister services if this was the last entry
		if not hass.data[DOMAIN]:
			hass.services.async_remove(DOMAIN, SERVICE_BLOCK_DEVICE_FOR_SCHOOL)
			hass.services.async_remove(DOMAIN, SERVICE_UNBLOCK_ALL_APPS)
			hass.services.async_remove(DOMAIN, SERVICE_BLOCK_APP)
			hass.services.async_remove(DOMAIN, SERVICE_UNBLOCK_APP)
			_LOGGER.debug("Family Link services unregistered")

	return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Reload config entry."""
	await async_unload_entry(hass, entry)
	await async_setup_entry(hass, entry) 