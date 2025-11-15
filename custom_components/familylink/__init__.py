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

from .const import (
	DOMAIN,
	LOGGER_NAME,
	SERVICE_ADD_TIME_BONUS,
	SERVICE_BLOCK_APP,
	SERVICE_BLOCK_DEVICE_FOR_SCHOOL,
	SERVICE_DISABLE_BEDTIME,
	SERVICE_DISABLE_DAILY_LIMIT,
	SERVICE_DISABLE_SCHOOL_TIME,
	SERVICE_ENABLE_BEDTIME,
	SERVICE_ENABLE_DAILY_LIMIT,
	SERVICE_ENABLE_SCHOOL_TIME,
	SERVICE_SET_DAILY_LIMIT,
	SERVICE_UNBLOCK_ALL_APPS,
	SERVICE_UNBLOCK_APP,
)
from .coordinator import FamilyLinkDataUpdateCoordinator
from .exceptions import FamilyLinkException

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]

# Service schemas
SCHEMA_BLOCK_DEVICE_FOR_SCHOOL = vol.Schema({
	vol.Optional("whitelist"): vol.All(cv.ensure_list, [cv.string]),
})

SCHEMA_BLOCK_APP = vol.Schema({
	vol.Required("package_name"): cv.string,
})

SCHEMA_UNBLOCK_APP = vol.Schema({
	vol.Required("package_name"): cv.string,
})

# Time management service schemas
SCHEMA_ADD_TIME_BONUS = vol.Schema({
	vol.Required("device_id"): cv.string,
	vol.Required("bonus_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
	vol.Optional("child_id"): cv.string,
})

SCHEMA_ENABLE_BEDTIME = vol.Schema({
	vol.Optional("child_id"): cv.string,
})

SCHEMA_DISABLE_BEDTIME = vol.Schema({
	vol.Optional("child_id"): cv.string,
})

SCHEMA_ENABLE_SCHOOL_TIME = vol.Schema({
	vol.Optional("child_id"): cv.string,
})

SCHEMA_DISABLE_SCHOOL_TIME = vol.Schema({
	vol.Optional("child_id"): cv.string,
})

SCHEMA_ENABLE_DAILY_LIMIT = vol.Schema({
	vol.Optional("child_id"): cv.string,
})

SCHEMA_DISABLE_DAILY_LIMIT = vol.Schema({
	vol.Optional("child_id"): cv.string,
})

SCHEMA_SET_DAILY_LIMIT = vol.Schema({
	vol.Required("device_id"): cv.string,
	vol.Required("daily_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
	vol.Optional("child_id"): cv.string,
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

	async def handle_add_time_bonus(call: ServiceCall) -> None:
		"""Handle add_time_bonus service call."""
		device_id = call.data["device_id"]
		bonus_minutes = call.data["bonus_minutes"]
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: add_time_bonus ({bonus_minutes} minutes) for device {device_id}")

		try:
			success = await coordinator.client.async_add_time_bonus(
				bonus_minutes=bonus_minutes,
				device_id=device_id,
				account_id=child_id
			)
			if success:
				_LOGGER.info(f"Successfully added {bonus_minutes} minutes bonus to device {device_id}")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error(f"Failed to add time bonus to device {device_id}")
		except Exception as err:
			_LOGGER.error(f"Error adding time bonus: {err}")
			raise

	async def handle_enable_bedtime(call: ServiceCall) -> None:
		"""Handle enable_bedtime service call."""
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: enable_bedtime")

		try:
			success = await coordinator.client.async_enable_bedtime(account_id=child_id)
			if success:
				_LOGGER.info("Successfully enabled bedtime")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error("Failed to enable bedtime")
		except Exception as err:
			_LOGGER.error(f"Error enabling bedtime: {err}")
			raise

	async def handle_disable_bedtime(call: ServiceCall) -> None:
		"""Handle disable_bedtime service call."""
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: disable_bedtime")

		try:
			success = await coordinator.client.async_disable_bedtime(account_id=child_id)
			if success:
				_LOGGER.info("Successfully disabled bedtime")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error("Failed to disable bedtime")
		except Exception as err:
			_LOGGER.error(f"Error disabling bedtime: {err}")
			raise

	async def handle_enable_school_time(call: ServiceCall) -> None:
		"""Handle enable_school_time service call."""
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: enable_school_time")

		try:
			success = await coordinator.client.async_enable_school_time(account_id=child_id)
			if success:
				_LOGGER.info("Successfully enabled school time")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error("Failed to enable school time")
		except Exception as err:
			_LOGGER.error(f"Error enabling school time: {err}")
			raise

	async def handle_disable_school_time(call: ServiceCall) -> None:
		"""Handle disable_school_time service call."""
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: disable_school_time")

		try:
			success = await coordinator.client.async_disable_school_time(account_id=child_id)
			if success:
				_LOGGER.info("Successfully disabled school time")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error("Failed to disable school time")
		except Exception as err:
			_LOGGER.error(f"Error disabling school time: {err}")
			raise

	async def handle_enable_daily_limit(call: ServiceCall) -> None:
		"""Handle enable_daily_limit service call."""
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: enable_daily_limit")

		try:
			success = await coordinator.client.async_enable_daily_limit(account_id=child_id)
			if success:
				_LOGGER.info("Successfully enabled daily limit")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error("Failed to enable daily limit")
		except Exception as err:
			_LOGGER.error(f"Error enabling daily limit: {err}")
			raise

	async def handle_disable_daily_limit(call: ServiceCall) -> None:
		"""Handle disable_daily_limit service call."""
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: disable_daily_limit")

		try:
			success = await coordinator.client.async_disable_daily_limit(account_id=child_id)
			if success:
				_LOGGER.info("Successfully disabled daily limit")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error("Failed to disable daily limit")
		except Exception as err:
			_LOGGER.error(f"Error disabling daily limit: {err}")
			raise

	async def handle_set_daily_limit(call: ServiceCall) -> None:
		"""Handle set_daily_limit service call."""
		device_id = call.data["device_id"]
		daily_minutes = call.data["daily_minutes"]
		child_id = call.data.get("child_id")
		_LOGGER.info(f"Service called: set_daily_limit ({daily_minutes} minutes) for device {device_id}")

		try:
			success = await coordinator.client.async_set_daily_limit(
				daily_minutes=daily_minutes,
				device_id=device_id,
				account_id=child_id
			)
			if success:
				_LOGGER.info(f"Successfully set daily limit to {daily_minutes} minutes for device {device_id}")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error(f"Failed to set daily limit for device {device_id}")
		except Exception as err:
			_LOGGER.error(f"Error setting daily limit: {err}")
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

	# Register time management services
	hass.services.async_register(
		DOMAIN,
		SERVICE_ADD_TIME_BONUS,
		handle_add_time_bonus,
		schema=SCHEMA_ADD_TIME_BONUS,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_ENABLE_BEDTIME,
		handle_enable_bedtime,
		schema=SCHEMA_ENABLE_BEDTIME,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_DISABLE_BEDTIME,
		handle_disable_bedtime,
		schema=SCHEMA_DISABLE_BEDTIME,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_ENABLE_SCHOOL_TIME,
		handle_enable_school_time,
		schema=SCHEMA_ENABLE_SCHOOL_TIME,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_DISABLE_SCHOOL_TIME,
		handle_disable_school_time,
		schema=SCHEMA_DISABLE_SCHOOL_TIME,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_ENABLE_DAILY_LIMIT,
		handle_enable_daily_limit,
		schema=SCHEMA_ENABLE_DAILY_LIMIT,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_DISABLE_DAILY_LIMIT,
		handle_disable_daily_limit,
		schema=SCHEMA_DISABLE_DAILY_LIMIT,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_SET_DAILY_LIMIT,
		handle_set_daily_limit,
		schema=SCHEMA_SET_DAILY_LIMIT,
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
			hass.services.async_remove(DOMAIN, SERVICE_ADD_TIME_BONUS)
			hass.services.async_remove(DOMAIN, SERVICE_ENABLE_BEDTIME)
			hass.services.async_remove(DOMAIN, SERVICE_DISABLE_BEDTIME)
			hass.services.async_remove(DOMAIN, SERVICE_ENABLE_SCHOOL_TIME)
			hass.services.async_remove(DOMAIN, SERVICE_DISABLE_SCHOOL_TIME)
			hass.services.async_remove(DOMAIN, SERVICE_ENABLE_DAILY_LIMIT)
			hass.services.async_remove(DOMAIN, SERVICE_DISABLE_DAILY_LIMIT)
			hass.services.async_remove(DOMAIN, SERVICE_SET_DAILY_LIMIT)
			_LOGGER.debug("Family Link services unregistered")

	return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Reload config entry."""
	await async_unload_entry(hass, entry)
	await async_setup_entry(hass, entry) 