"""Binary sensor platform for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
	BinarySensorDeviceClass,
	BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
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
	"""Set up Family Link binary sensor entities from a config entry."""
	coordinator = hass.data[DOMAIN][entry.entry_id]

	entities = [
		FamilyLinkSessionValidSensor(coordinator, entry),
	]

	async_add_entities(entities)
	_LOGGER.debug("Family Link binary sensors set up successfully")


class FamilyLinkSessionValidSensor(CoordinatorEntity, BinarySensorEntity):
	"""Binary sensor indicating if the Family Link session is valid."""

	_attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
	_attr_has_entity_name = True

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		entry: ConfigEntry,
	) -> None:
		"""Initialize the session validity sensor."""
		super().__init__(coordinator)
		self._attr_unique_id = f"{entry.entry_id}_session_valid"
		self._attr_name = "Session valide"
		self._entry = entry

	@property
	def is_on(self) -> bool:
		"""Return True if the session is valid."""
		# If we have valid data from the coordinator, the session is valid
		# If the coordinator has data, it means the last update was successful
		return self.coordinator.last_update_success

	@property
	def available(self) -> bool:
		"""Return if entity is available."""
		# Always available to show session status
		return True

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information for this sensor."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"familylink_{self._entry.entry_id}")},
			name=f"{INTEGRATION_NAME}",
			manufacturer="Google",
			model="Family Link Integration",
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return additional state attributes."""
		attrs = {}

		if self.coordinator.last_update_success:
			attrs["status"] = "connecté"
			if self.coordinator.data:
				supervised_count = len(self.coordinator.data.get("supervised_children", []))
				attrs["enfants_supervisés"] = supervised_count
		else:
			attrs["status"] = "déconnecté"
			attrs["message"] = "Cookie expiré - Ré-authentification requise"

		return attrs

	@property
	def icon(self) -> str:
		"""Return the icon to use in the frontend."""
		return "mdi:cookie-check" if self.is_on else "mdi:cookie-remove"
