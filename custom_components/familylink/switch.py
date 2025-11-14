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

	# Wait for first data fetch to get children
	if not coordinator.data or "children_data" not in coordinator.data:
		_LOGGER.warning("No children data available yet, switches will be added on first update")
		return

	# Create switch entities for each device of each child
	for child_data in coordinator.data.get("children_data", []):
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]

		_LOGGER.debug(f"Creating switches for {child_name}'s devices")

		for device in child_data.get("devices", []):
			entities.append(FamilyLinkDeviceSwitch(coordinator, device, child_id, child_name))

	async_add_entities(entities, update_before_add=True)


class FamilyLinkDeviceSwitch(CoordinatorEntity, SwitchEntity):
	"""Representation of a Family Link device as a switch."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device: dict[str, Any],
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the switch."""
		super().__init__(coordinator)

		self._device = device
		self._device_id = device["id"]
		self._attr_name = device.get("name", f"Family Link Device {self._device_id}")
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_{self._device_id}"
		self._child_id = child_id
		self._child_name = child_name
		self._attr_name = device.get("name", f"{child_name} Device {self._device_id}")
		self._attr_unique_id = f"{DOMAIN}_{child_id}_{self._device_id}"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
			name=self._attr_name,
			manufacturer="Google",
			model=self._device.get("model", "Family Link Device"),
			sw_version=self._device.get("version"),
			via_device=(DOMAIN, f"familylink_{self._child_id}"),  # Link to parent (child's account device)
		)

	@property
	def is_on(self) -> bool:
		"""Return True if device is unlocked (switch on = unlocked)."""
		if self.coordinator.data and "children_data" in self.coordinator.data:
			# Find current device data for this child
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					for device in child_data.get("devices", []):
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
			"child_id": self._child_id,
			"child_name": self._child_name,
		}

		# Add additional device information if available
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					for device in child_data.get("devices", []):
						if device["id"] == self._device_id:
							if "type" in device:
								attributes[ATTR_DEVICE_TYPE] = device["type"]
							if "last_activity" in device:
								attributes[ATTR_LAST_SEEN] = device["last_activity"]
							if "locked" in device:
								attributes[ATTR_LOCKED] = device["locked"]
							if "model" in device:
								attributes["model"] = device["model"]
							break
					break

		return attributes

	async def async_turn_on(self) -> None:
		"""Turn the switch on (unlock device)."""
		_LOGGER.debug("Unlocking device %s for child %s", self._device_id, self._child_name)

		success = await self.coordinator.async_control_device(
			self._device_id, DEVICE_UNLOCK_ACTION, self._child_id
		)

		if not success:
			_LOGGER.error("Failed to unlock device %s", self._device_id)
		else:
			_LOGGER.info("Successfully unlocked device %s", self._device_id)

	async def async_turn_off(self) -> None:
		"""Turn the switch off (lock device)."""
		_LOGGER.debug("Locking device %s for child %s", self._device_id, self._child_name)

		success = await self.coordinator.async_control_device(
			self._device_id, DEVICE_LOCK_ACTION, self._child_id
		)

		if not success:
			_LOGGER.error("Failed to lock device %s", self._device_id)
		else:
			_LOGGER.info("Successfully locked device %s", self._device_id) 