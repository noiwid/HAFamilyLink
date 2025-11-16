"""Button platform for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up Family Link button entities from a config entry."""
	coordinator = hass.data[DOMAIN][entry.entry_id]

	entities = []

	# Check if data is available (should be after async_config_entry_first_refresh)
	if not coordinator.data or "children_data" not in coordinator.data:
		_LOGGER.error(
			"CRITICAL: No children data in coordinator after first refresh! "
			"Buttons will NOT be created. "
			f"coordinator.data keys: {list(coordinator.data.keys()) if coordinator.data else 'None'}"
		)
		# Don't return - this prevents entities from ever being created!

	# Get device registry
	device_registry = dr.async_get(hass)

	# Create button entities for each device of each child
	for child_data in coordinator.data.get("children_data", []):
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]

		_LOGGER.debug(f"Creating time bonus buttons for {child_name}'s devices")

		# Ensure parent device (child account) exists in device registry
		device_registry.async_get_or_create(
			config_entry_id=entry.entry_id,
			identifiers={(DOMAIN, child_id)},
			name=f"{child_name} (Family Link)",
			manufacturer="Google",
			model="Family Link Account",
		)

		for device in child_data.get("devices", []):
			# Create 4 time bonus buttons per device (15min, 30min, 60min, cancel)
			entities.append(FamilyLinkTimeBonusButton(coordinator, device, child_id, child_name, 15))
			entities.append(FamilyLinkTimeBonusButton(coordinator, device, child_id, child_name, 30))
			entities.append(FamilyLinkTimeBonusButton(coordinator, device, child_id, child_name, 60))
			entities.append(CancelTimeBonusButton(coordinator, device, child_id, child_name))

	_LOGGER.debug(f"Created {len(entities)} time bonus button entities")
	async_add_entities(entities, update_before_add=True)


class FamilyLinkTimeBonusButton(CoordinatorEntity, ButtonEntity):
	"""Representation of a time bonus button for a Family Link device."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device: dict[str, Any],
		child_id: str,
		child_name: str,
		bonus_minutes: int,
	) -> None:
		"""Initialize the button."""
		super().__init__(coordinator)

		self._device_id = device["id"]
		self._device_name = device["name"]
		self._child_id = child_id
		self._child_name = child_name
		self._bonus_minutes = bonus_minutes

		self._attr_name = f"{device['name']} +{bonus_minutes}min"
		self._attr_unique_id = f"{DOMAIN}_{device['id']}_bonus_{bonus_minutes}min"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
			name=self._device_name,
			manufacturer="Google",
			model="Family Link Device",
		)

	@property
	def icon(self) -> str:
		"""Return the icon for the button."""
		return "mdi:clock-plus-outline"

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	async def async_press(self) -> None:
		"""Handle the button press."""
		_LOGGER.info(
			f"Adding {self._bonus_minutes} minutes bonus to device {self._device_name} for {self._child_name}"
		)

		success = await self.coordinator.client.async_add_time_bonus(
			bonus_minutes=self._bonus_minutes,
			device_id=self._device_id,
			account_id=self._child_id,
		)

		if not success:
			_LOGGER.error(
				f"Failed to add {self._bonus_minutes} minutes bonus to device {self._device_name}"
			)
		else:
			_LOGGER.info(
				f"Successfully added {self._bonus_minutes} minutes bonus to device {self._device_name}"
			)
			# Refresh to update bonus sensor
			await self.coordinator.async_request_refresh()


class CancelTimeBonusButton(CoordinatorEntity, ButtonEntity):
	"""Button to cancel/reset an active time bonus for a Family Link device."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device: dict[str, Any],
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the button."""
		super().__init__(coordinator)

		self._device_id = device["id"]
		self._device_name = device["name"]
		self._child_id = child_id
		self._child_name = child_name

		self._attr_name = f"{device['name']} Reset Bonus"
		self._attr_unique_id = f"{DOMAIN}_{device['id']}_reset_bonus"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
			name=self._device_name,
			manufacturer="Google",
			model="Family Link Device",
		)

	@property
	def icon(self) -> str:
		"""Return the icon for the button."""
		return "mdi:clock-remove-outline"

	@property
	def available(self) -> bool:
		"""Return True if entity is available and bonus is active."""
		if not self.coordinator.last_update_success:
			return False

		# Only available if there's an active bonus to cancel
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					devices_time_data = child_data.get("devices_time_data", {})

					if self._device_id in devices_time_data:
						time_data = devices_time_data[self._device_id]
						override_id = time_data.get("bonus_override_id")
						return override_id is not None

		return False

	async def async_press(self) -> None:
		"""Handle the button press - cancel active bonus."""
		# Get the override_id from coordinator data
		override_id = None

		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					devices_time_data = child_data.get("devices_time_data", {})

					if self._device_id in devices_time_data:
						time_data = devices_time_data[self._device_id]
						override_id = time_data.get("bonus_override_id")
						break

		if not override_id:
			_LOGGER.warning(
				f"Cannot cancel bonus for device {self._device_name}: no active bonus found"
			)
			return

		_LOGGER.info(
			f"Cancelling time bonus (override_id: {override_id}) for device {self._device_name}"
		)

		success = await self.coordinator.client.async_cancel_time_bonus(
			override_id=override_id,
			account_id=self._child_id,
		)

		if not success:
			_LOGGER.error(
				f"Failed to cancel time bonus for device {self._device_name}"
			)
		else:
			_LOGGER.info(
				f"Successfully cancelled time bonus for device {self._device_name}"
			)
			# Refresh to update sensors
			await self.coordinator.async_request_refresh()
