"""Switch platform for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
	ATTR_DEVICE_ID,
	ATTR_DEVICE_NAME,
	ATTR_DEVICE_TYPE,
	ATTR_LAST_SEEN,
	ATTR_LOCKED,
	DEVICE_LOCK_ACTION,
	DEVICE_UNLOCK_ACTION,
	DOMAIN,
	INTEGRATION_NAME,
	LOGGER_NAME,
)
from .coordinator import FamilyLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up Family Link switch entities from a config entry."""
	coordinator = hass.data[DOMAIN][entry.entry_id]

	entities = []
	
	# Create switch entities for each device
	if coordinator.data and "devices" in coordinator.data:
		for device in coordinator.data["devices"]:
			entities.append(FamilyLinkDeviceSwitch(coordinator, device))

	async_add_entities(entities, update_before_add=True)


class FamilyLinkDeviceSwitch(CoordinatorEntity, SwitchEntity):
	"""Representation of a Family Link device as a switch."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device: dict[str, Any],
	) -> None:
		"""Initialize the switch."""
		super().__init__(coordinator)

		self._device = device
		self._device_id = device["id"]
		self._attr_name = device.get("name", f"Family Link Device {self._device_id}")
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_{self._device_id}"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, self._device_id)},
			name=self._attr_name,
			manufacturer="Google",
			model="Family Link Device",
			sw_version=self._device.get("version"),
		)

	@property
	def is_on(self) -> bool:
		"""Return True if device is unlocked (switch on = unlocked)."""
		if self.coordinator.data and "devices" in self.coordinator.data:
			# Find current device data
			for device in self.coordinator.data["devices"]:
				if device["id"] == self._device_id:
					# Switch is "on" when device is unlocked
					return not device.get("locked", False)
		
		# Fallback to cached device data
		return not self._device.get("locked", False)

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	@property
	def icon(self) -> str:
		"""Return the icon for the switch."""
		return "mdi:cellphone-lock" if not self.is_on else "mdi:cellphone"

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		attributes = {
			ATTR_DEVICE_ID: self._device_id,
			ATTR_DEVICE_NAME: self._attr_name,
		}

		# Add additional device information if available
		if self.coordinator.data and "devices" in self.coordinator.data:
			for device in self.coordinator.data["devices"]:
				if device["id"] == self._device_id:
					if "type" in device:
						attributes[ATTR_DEVICE_TYPE] = device["type"]
					if "last_seen" in device:
						attributes[ATTR_LAST_SEEN] = device["last_seen"]
					if "locked" in device:
						attributes[ATTR_LOCKED] = device["locked"]
					break

		return attributes

	async def async_turn_on(self) -> None:
		"""Turn the switch on (unlock device)."""
		_LOGGER.debug("Unlocking device %s", self._device_id)
		
		success = await self.coordinator.async_control_device(
			self._device_id, DEVICE_UNLOCK_ACTION
		)
		
		if not success:
			_LOGGER.error("Failed to unlock device %s", self._device_id)
		else:
			_LOGGER.info("Successfully unlocked device %s", self._device_id)

	async def async_turn_off(self) -> None:
		"""Turn the switch off (lock device)."""
		_LOGGER.debug("Locking device %s", self._device_id)
		
		success = await self.coordinator.async_control_device(
			self._device_id, DEVICE_LOCK_ACTION
		)
		
		if not success:
			_LOGGER.error("Failed to lock device %s", self._device_id)
		else:
			_LOGGER.info("Successfully locked device %s", self._device_id) 