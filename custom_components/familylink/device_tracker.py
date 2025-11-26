"""Device tracker platform for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_LOCATION_TRACKING, DOMAIN, INTEGRATION_NAME, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up Family Link device tracker entities from a config entry."""
	# Check if location tracking is enabled
	if not entry.data.get(CONF_ENABLE_LOCATION_TRACKING, False):
		_LOGGER.debug("Location tracking is disabled, skipping device_tracker setup")
		return

	coordinator: FamilyLinkDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

	entities = []

	# Check if data is available
	if not coordinator.data or "children_data" not in coordinator.data:
		_LOGGER.error("No children data available for device tracker setup")
		return

	# Create a device tracker for each child
	for child_data in coordinator.data["children_data"]:
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]

		entities.append(
			FamilyLinkDeviceTracker(
				coordinator=coordinator,
				child_id=child_id,
				child_name=child_name,
			)
		)
		_LOGGER.debug(f"Created device tracker for child: {child_name}")

	if entities:
		async_add_entities(entities)
		_LOGGER.info(f"Added {len(entities)} device tracker(s)")


class FamilyLinkDeviceTracker(CoordinatorEntity[FamilyLinkDataUpdateCoordinator], TrackerEntity):
	"""Representation of a Family Link device tracker for a child."""

	_attr_has_entity_name = True

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the device tracker."""
		super().__init__(coordinator)
		self._child_id = child_id
		self._child_name = child_name
		# _attr_name = None means entity uses device name only (no suffix)
		# Result: device_tracker.child_name_family_link
		self._attr_name = None
		self._attr_unique_id = f"{DOMAIN}_{child_id}_location"

	def _get_child_data(self) -> dict[str, Any] | None:
		"""Get data for this specific child."""
		if not self.coordinator.data or "children_data" not in self.coordinator.data:
			return None

		for child_data in self.coordinator.data["children_data"]:
			if child_data["child_id"] == self._child_id:
				return child_data

		return None

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information for this child."""
		return DeviceInfo(
			identifiers={(DOMAIN, self._child_id)},
			name=f"{self._child_name} (Family Link)",
			manufacturer="Google",
			model="Family Link Account",
		)

	@property
	def source_type(self) -> SourceType:
		"""Return the source type of the device tracker."""
		return SourceType.GPS

	@property
	def latitude(self) -> float | None:
		"""Return latitude value of the device."""
		child_data = self._get_child_data()
		if not child_data or not child_data.get("location"):
			return None
		return child_data["location"].get("latitude")

	@property
	def longitude(self) -> float | None:
		"""Return longitude value of the device."""
		child_data = self._get_child_data()
		if not child_data or not child_data.get("location"):
			return None
		return child_data["location"].get("longitude")

	@property
	def location_accuracy(self) -> int:
		"""Return the location accuracy of the device."""
		child_data = self._get_child_data()
		if not child_data or not child_data.get("location"):
			return 0
		return child_data["location"].get("accuracy") or 0

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or not child_data.get("location"):
			return {}

		location = child_data["location"]
		attrs = {}

		# Source device name (resolved from device ID)
		if location.get("source_device_name"):
			attrs["source_device"] = location["source_device_name"]

		# Place information
		if location.get("place_name"):
			attrs["place_name"] = location["place_name"]
		if location.get("place_address"):
			attrs["address"] = location["place_address"]

		# Timestamp of the location
		if location.get("timestamp_iso"):
			attrs["location_timestamp"] = location["timestamp_iso"]

		return attrs

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		if not self.coordinator.last_update_success:
			return False

		child_data = self._get_child_data()
		if not child_data:
			return False

		# Device tracker is available even without location data
		# (state will be "unknown" if no location)
		return True
