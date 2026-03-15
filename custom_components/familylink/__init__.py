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
	SERVICE_SET_APP_DAILY_LIMIT,
	SERVICE_SET_BEDTIME,
	SERVICE_SET_DAILY_LIMIT,
	SERVICE_REFRESH_LOCATION,
	SERVICE_UNBLOCK_ALL_APPS,
	SERVICE_UNBLOCK_APP,
)
from .coordinator import FamilyLinkDataUpdateCoordinator
from .exceptions import FamilyLinkException

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.DEVICE_TRACKER, Platform.SENSOR, Platform.SWITCH]

# Service schemas
SCHEMA_BLOCK_DEVICE_FOR_SCHOOL = vol.Schema({
	vol.Optional("whitelist"): vol.All(cv.ensure_list, [cv.string]),
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_UNBLOCK_ALL_APPS = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_BLOCK_APP = vol.Schema({
	vol.Required("package_name"): cv.string,
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_UNBLOCK_APP = vol.Schema({
	vol.Required("package_name"): cv.string,
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_SET_APP_DAILY_LIMIT = vol.Schema({
	vol.Required("package_name"): cv.string,
	vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=-2, max=1440)),
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

# Time management service schemas
# Note: entity_id is optional - if provided, device_id/child_id are extracted from entity attributes
SCHEMA_ADD_TIME_BONUS = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("device_id"): cv.string,
	vol.Required("bonus_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
	vol.Optional("child_id"): cv.string,
})

SCHEMA_ENABLE_BEDTIME = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_DISABLE_BEDTIME = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_ENABLE_SCHOOL_TIME = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_DISABLE_SCHOOL_TIME = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_ENABLE_DAILY_LIMIT = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_DISABLE_DAILY_LIMIT = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
})

SCHEMA_SET_DAILY_LIMIT = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("device_id"): cv.string,
	vol.Required("daily_minutes"): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
	vol.Optional("child_id"): cv.string,
})

SCHEMA_SET_BEDTIME = vol.Schema({
	vol.Required("start_time"): vol.Match(r"^\d{1,2}:\d{2}$"),
	vol.Required("end_time"): vol.Match(r"^\d{1,2}:\d{2}$"),
	vol.Optional("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=7)),
	vol.Optional("child_id"): cv.string,
})

SCHEMA_REFRESH_LOCATION = vol.Schema({
	vol.Optional("entity_id"): cv.entity_id,
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

		# Add options update listener
		entry.async_on_unload(entry.add_update_listener(async_options_updated))

		# Forward setup to platforms
		await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

		# Register services
		await async_setup_services(hass, coordinator)

		_LOGGER.info("Successfully set up Family Link integration")
		return True

	except FamilyLinkException as err:
		_LOGGER.debug("Failed to set up Family Link, will retry: %s", err)
		raise ConfigEntryNotReady(f"Failed to connect: {err}") from err
	except Exception as err:
		_LOGGER.debug("Unexpected error setting up Family Link, will retry: %s", err)
		raise ConfigEntryNotReady(f"Unexpected error: {err}") from err


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Handle options update - reload the config entry."""
	_LOGGER.debug("Options updated, reloading integration")
	await hass.config_entries.async_reload(entry.entry_id)


def extract_ids_from_entity(hass: HomeAssistant, entity_id: str | None, require_device_id: bool = False) -> tuple[str | None, str | None]:
	"""Extract device_id and child_id from entity attributes.

	Args:
		hass: Home Assistant instance
		entity_id: Entity ID to get attributes from
		require_device_id: If True, raises error if device_id not found

	Returns:
		Tuple of (device_id, child_id) - either or both may be None

	Raises:
		ValueError: If entity not found or required attributes missing
	"""
	if not entity_id:
		return None, None

	state = hass.states.get(entity_id)
	if not state:
		raise ValueError(f"Entity {entity_id} not found")

	attributes = state.attributes
	device_id = attributes.get("device_id")
	child_id = attributes.get("child_id")

	if require_device_id and not device_id:
		raise ValueError(f"Entity {entity_id} does not have a device_id attribute. Please select a device switch entity.")

	_LOGGER.debug(f"Extracted from {entity_id}: device_id={device_id}, child_id={child_id}")
	return device_id, child_id


async def async_setup_services(hass: HomeAssistant, coordinator: FamilyLinkDataUpdateCoordinator) -> None:
	"""Set up services for Family Link."""

	def _require_client():
		"""Raise if the API client is not available."""
		if coordinator.client is None:
			raise FamilyLinkException("Family Link client is not connected. Please re-authenticate via the add-on.")

	async def handle_block_device_for_school(call: ServiceCall) -> None:
		"""Handle block_device_for_school service call."""
		_require_client()
		whitelist = call.data.get("whitelist")
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

		try:
			if child_id:
				_LOGGER.info(f"Service called: block_device_for_school (child_id: {child_id})")
				result = await coordinator.client.async_block_device_for_school(
					account_id=child_id, whitelist=whitelist
				)
				_LOGGER.info(
					f"School mode activated for child {child_id}: {result['blocked_count']} apps blocked, "
					f"{result['failed_count']} failed"
				)
			else:
				_LOGGER.info("Service called: block_device_for_school (all children)")
				children = await coordinator.client.async_get_all_supervised_children()
				for child in children:
					child_account_id = child["id"]
					child_name = child["name"]
					result = await coordinator.client.async_block_device_for_school(
						account_id=child_account_id, whitelist=whitelist
					)
					_LOGGER.info(
						f"School mode activated for {child_name}: {result['blocked_count']} apps blocked, "
						f"{result['failed_count']} failed"
					)
			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Failed to block device for school: {err}")
			raise

	async def handle_unblock_all_apps(call: ServiceCall) -> None:
		"""Handle unblock_all_apps service call."""
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

		try:
			if child_id:
				_LOGGER.info(f"Service called: unblock_all_apps (child_id: {child_id})")
				result = await coordinator.client.async_unblock_all_apps(account_id=child_id)
				_LOGGER.info(
					f"All apps unblocked for child {child_id}: {result['unblocked_count']} apps unblocked, "
					f"{result['failed_count']} failed"
				)
			else:
				_LOGGER.info("Service called: unblock_all_apps (all children)")
				children = await coordinator.client.async_get_all_supervised_children()
				for child in children:
					child_account_id = child["id"]
					child_name = child["name"]
					result = await coordinator.client.async_unblock_all_apps(account_id=child_account_id)
					_LOGGER.info(
						f"All apps unblocked for {child_name}: {result['unblocked_count']} apps unblocked, "
						f"{result['failed_count']} failed"
					)
			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Failed to unblock all apps: {err}")
			raise

	async def handle_block_app(call: ServiceCall) -> None:
		"""Handle block_app service call."""
		_require_client()
		package_name = call.data["package_name"]
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

		try:
			if child_id:
				# Apply to specific child
				_LOGGER.info(f"Service called: block_app for {package_name} (child_id: {child_id})")
				success = await coordinator.client.async_block_app(package_name, account_id=child_id)
				if success:
					_LOGGER.info(f"Successfully blocked app: {package_name} for child {child_id}")
				else:
					_LOGGER.error(f"Failed to block app: {package_name} for child {child_id}")
			else:
				# Apply to ALL supervised children
				_LOGGER.info(f"Service called: block_app for {package_name} (all children)")
				children = await coordinator.client.async_get_all_supervised_children()
				success_count = 0
				fail_count = 0

				for child in children:
					child_account_id = child["id"]
					child_name = child["name"]
					result = await coordinator.client.async_block_app(package_name, account_id=child_account_id)
					if result:
						success_count += 1
						_LOGGER.info(f"Successfully blocked app: {package_name} for {child_name}")
					else:
						fail_count += 1
						_LOGGER.error(f"Failed to block app: {package_name} for {child_name}")

				_LOGGER.info(f"Block app {package_name}: {success_count} succeeded, {fail_count} failed")

			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Error blocking app {package_name}: {err}")
			raise

	async def handle_unblock_app(call: ServiceCall) -> None:
		"""Handle unblock_app service call."""
		_require_client()
		package_name = call.data["package_name"]
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

		try:
			if child_id:
				# Apply to specific child
				_LOGGER.info(f"Service called: unblock_app for {package_name} (child_id: {child_id})")
				success = await coordinator.client.async_unblock_app(package_name, account_id=child_id)
				if success:
					_LOGGER.info(f"Successfully unblocked app: {package_name} for child {child_id}")
				else:
					_LOGGER.error(f"Failed to unblock app: {package_name} for child {child_id}")
			else:
				# Apply to ALL supervised children
				_LOGGER.info(f"Service called: unblock_app for {package_name} (all children)")
				children = await coordinator.client.async_get_all_supervised_children()
				success_count = 0
				fail_count = 0

				for child in children:
					child_account_id = child["id"]
					child_name = child["name"]
					result = await coordinator.client.async_unblock_app(package_name, account_id=child_account_id)
					if result:
						success_count += 1
						_LOGGER.info(f"Successfully unblocked app: {package_name} for {child_name}")
					else:
						fail_count += 1
						_LOGGER.error(f"Failed to unblock app: {package_name} for {child_name}")

				_LOGGER.info(f"Unblock app {package_name}: {success_count} succeeded, {fail_count} failed")

			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Error unblocking app {package_name}: {err}")
			raise

	async def handle_set_app_daily_limit(call: ServiceCall) -> None:
		"""Handle set_app_daily_limit service call."""
		_require_client()
		package_name = call.data["package_name"]
		minutes = call.data["minutes"]
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

		try:
			if child_id:
				# Apply to specific child
				_LOGGER.info(f"Service called: set_app_daily_limit for {package_name} = {minutes} min (child_id: {child_id})")
				success = await coordinator.client.async_set_app_daily_limit(package_name, minutes, account_id=child_id)
				if success:
					_LOGGER.info(f"Successfully set app daily limit: {package_name} = {minutes} min for child {child_id}")
				else:
					_LOGGER.error(f"Failed to set app daily limit: {package_name} for child {child_id}")
			else:
				# Apply to ALL supervised children
				_LOGGER.info(f"Service called: set_app_daily_limit for {package_name} = {minutes} min (all children)")
				children = await coordinator.client.async_get_all_supervised_children()
				success_count = 0
				fail_count = 0

				for child in children:
					child_account_id = child["id"]
					child_name = child["name"]
					result = await coordinator.client.async_set_app_daily_limit(package_name, minutes, account_id=child_account_id)
					if result:
						success_count += 1
						_LOGGER.info(f"Successfully set app daily limit: {package_name} = {minutes} min for {child_name}")
					else:
						fail_count += 1
						_LOGGER.error(f"Failed to set app daily limit: {package_name} for {child_name}")

				_LOGGER.info(f"Set app daily limit {package_name}: {success_count} succeeded, {fail_count} failed")

			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Error setting app daily limit for {package_name}: {err}")
			raise

	async def handle_add_time_bonus(call: ServiceCall) -> None:
		"""Handle add_time_bonus service call."""
		_require_client()
		bonus_minutes = call.data["bonus_minutes"]

		# Get device_id and child_id from entity or direct parameters
		entity_id = call.data.get("entity_id")
		device_id = call.data.get("device_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract IDs from entity attributes
		if entity_id:
			extracted_device_id, extracted_child_id = extract_ids_from_entity(hass, entity_id, require_device_id=True)
			device_id = device_id or extracted_device_id
			child_id = child_id or extracted_child_id

		if not device_id:
			raise ValueError("device_id is required. Either select an entity or provide device_id manually.")

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
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

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
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

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
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

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
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

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
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

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
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

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
		_require_client()
		daily_minutes = call.data["daily_minutes"]

		# Get device_id and child_id from entity or direct parameters
		entity_id = call.data.get("entity_id")
		device_id = call.data.get("device_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract IDs from entity attributes
		if entity_id:
			extracted_device_id, extracted_child_id = extract_ids_from_entity(hass, entity_id, require_device_id=True)
			device_id = device_id or extracted_device_id
			child_id = child_id or extracted_child_id

		if not device_id:
			raise ValueError("device_id is required. Either select an entity or provide device_id manually.")

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

	async def handle_set_bedtime(call: ServiceCall) -> None:
		"""Handle set_bedtime service call."""
		_require_client()
		start_time = call.data["start_time"]
		end_time = call.data["end_time"]
		day = call.data.get("day")  # Optional, defaults to today
		child_id = call.data.get("child_id")

		# Convert day to int if provided as string (from UI selector)
		if day is not None:
			day = int(day)

		_LOGGER.info(f"Service called: set_bedtime ({start_time}-{end_time}) for day={day or 'today'}")

		try:
			success = await coordinator.client.async_set_bedtime(
				start_time=start_time,
				end_time=end_time,
				day=day,
				account_id=child_id
			)
			if success:
				_LOGGER.info(f"Successfully set bedtime {start_time}-{end_time}")
				await coordinator.async_request_refresh()
			else:
				_LOGGER.error("Failed to set bedtime")
		except Exception as err:
			_LOGGER.error(f"Error setting bedtime: {err}")
			raise

	async def handle_refresh_location(call: ServiceCall) -> None:
		"""Handle refresh_location service call - request fresh location from device."""
		_require_client()
		entity_id = call.data.get("entity_id")
		child_id = call.data.get("child_id")

		# If entity_id provided, extract child_id from entity attributes
		if entity_id and not child_id:
			_, extracted_child_id = extract_ids_from_entity(hass, entity_id)
			child_id = extracted_child_id

		try:
			if child_id:
				_LOGGER.info(f"Service called: refresh_location (child_id: {child_id})")
				location = await coordinator.client.async_get_location(account_id=child_id, refresh=True)
				if location:
					_LOGGER.info(f"Successfully refreshed location for child {child_id}: ({location['latitude']}, {location['longitude']})")
				else:
					_LOGGER.warning(f"No location data returned for child {child_id}")
			else:
				# Refresh location for ALL supervised children
				_LOGGER.info("Service called: refresh_location (all children)")
				children = await coordinator.client.async_get_all_supervised_children()
				for child in children:
					child_account_id = child["id"]
					child_name = child["name"]
					location = await coordinator.client.async_get_location(account_id=child_account_id, refresh=True)
					if location:
						_LOGGER.info(f"Successfully refreshed location for {child_name}: ({location['latitude']}, {location['longitude']})")
					else:
						_LOGGER.warning(f"No location data returned for {child_name}")

			await coordinator.async_request_refresh()
		except Exception as err:
			_LOGGER.error(f"Error refreshing location: {err}")
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
		schema=SCHEMA_UNBLOCK_ALL_APPS,
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

	hass.services.async_register(
		DOMAIN,
		SERVICE_SET_APP_DAILY_LIMIT,
		handle_set_app_daily_limit,
		schema=SCHEMA_SET_APP_DAILY_LIMIT,
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

	hass.services.async_register(
		DOMAIN,
		SERVICE_SET_BEDTIME,
		handle_set_bedtime,
		schema=SCHEMA_SET_BEDTIME,
	)

	hass.services.async_register(
		DOMAIN,
		SERVICE_REFRESH_LOCATION,
		handle_refresh_location,
		schema=SCHEMA_REFRESH_LOCATION,
	)

	_LOGGER.debug("Family Link services registered")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
	"""Unload a config entry."""
	_LOGGER.debug("Unloading Family Link integration")

	# Unload platforms
	unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

	if unload_ok:
		# Remove coordinator from hass data
		coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)

		# Clean up coordinator resources
		if hasattr(coordinator, 'async_cleanup'):
			await coordinator.async_cleanup()

		# Unregister services if this was the last entry
		if not hass.data[DOMAIN]:
			hass.services.async_remove(DOMAIN, SERVICE_BLOCK_DEVICE_FOR_SCHOOL)
			hass.services.async_remove(DOMAIN, SERVICE_UNBLOCK_ALL_APPS)
			hass.services.async_remove(DOMAIN, SERVICE_BLOCK_APP)
			hass.services.async_remove(DOMAIN, SERVICE_UNBLOCK_APP)
			hass.services.async_remove(DOMAIN, SERVICE_SET_APP_DAILY_LIMIT)
			hass.services.async_remove(DOMAIN, SERVICE_ADD_TIME_BONUS)
			hass.services.async_remove(DOMAIN, SERVICE_ENABLE_BEDTIME)
			hass.services.async_remove(DOMAIN, SERVICE_DISABLE_BEDTIME)
			hass.services.async_remove(DOMAIN, SERVICE_ENABLE_SCHOOL_TIME)
			hass.services.async_remove(DOMAIN, SERVICE_DISABLE_SCHOOL_TIME)
			hass.services.async_remove(DOMAIN, SERVICE_ENABLE_DAILY_LIMIT)
			hass.services.async_remove(DOMAIN, SERVICE_DISABLE_DAILY_LIMIT)
			hass.services.async_remove(DOMAIN, SERVICE_SET_DAILY_LIMIT)
			hass.services.async_remove(DOMAIN, SERVICE_SET_BEDTIME)
			hass.services.async_remove(DOMAIN, SERVICE_REFRESH_LOCATION)
			_LOGGER.debug("Family Link services unregistered")

	return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
	"""Reload config entry."""
	await async_unload_entry(hass, entry)
	await async_setup_entry(hass, entry) 