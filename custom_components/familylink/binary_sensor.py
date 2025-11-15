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

	entities = []

	# Wait for first data fetch to get children
	if not coordinator.data or "children_data" not in coordinator.data:
		_LOGGER.warning("No children data available yet, binary sensors will be added on first update")
		return

	# Create binary sensors for each child's devices
	for child_data in coordinator.data.get("children_data", []):
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]

		_LOGGER.debug(f"Creating binary sensors for child: {child_name}")

		# Create binary sensors for each device
		for device in child_data.get("devices", []):
			device_id = device["id"]
			device_name = device.get("name", f"Device {device_id}")

			# Bedtime active sensor
			entities.append(
				BedtimeActiveBinarySensor(
					coordinator,
					device_id,
					device_name,
					device,
					child_id,
					child_name,
				)
			)

			# School time active sensor
			entities.append(
				SchoolTimeActiveBinarySensor(
					coordinator,
					device_id,
					device_name,
					device,
					child_id,
					child_name,
				)
			)

			# Daily limit reached sensor
			entities.append(
				DailyLimitReachedBinarySensor(
					coordinator,
					device_id,
					device_name,
					device,
					child_id,
					child_name,
				)
			)

	_LOGGER.debug(f"Created {len(entities)} binary sensor entities")
	async_add_entities(entities, update_before_add=True)


class DeviceTimeBinarySensor(CoordinatorEntity, BinarySensorEntity):
	"""Base class for device time binary sensors."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device_id: str,
		device_name: str,
		device: dict[str, Any],
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the binary sensor."""
		super().__init__(coordinator)

		self._device_id = device_id
		self._device_name = device_name
		self._device = device
		self._child_id = child_id
		self._child_name = child_name

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
			name=self._device_name,
			manufacturer="Google",
			model=self._device.get("model", "Family Link Device"),
			sw_version=self._device.get("version"),
			via_device=(DOMAIN, f"familylink_{self._child_id}"),
		)

	def _get_device_time_data(self) -> dict[str, Any] | None:
		"""Get time data for this specific device."""
		if not self.coordinator.data or "children_data" not in self.coordinator.data:
			return None

		for child_data in self.coordinator.data["children_data"]:
			if child_data["child_id"] == self._child_id:
				devices_time_data = child_data.get("devices_time_data", {})
				return devices_time_data.get(self._device_id)

		return None

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self._get_device_time_data() is not None
		)


class BedtimeActiveBinarySensor(DeviceTimeBinarySensor):
	"""Binary sensor indicating if device is currently in bedtime window."""

	_attr_device_class = BinarySensorDeviceClass.RUNNING

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device_id: str,
		device_name: str,
		device: dict[str, Any],
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the bedtime active sensor."""
		super().__init__(coordinator, device_id, device_name, device, child_id, child_name)

		self._attr_name = f"{device_name} Bedtime Active"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_{device_id}_bedtime_active"

	@property
	def is_on(self) -> bool:
		"""Return True if device is currently in bedtime window."""
		time_data = self._get_device_time_data()
		if not time_data:
			return False

		return time_data.get("bedtime_active", False)

	@property
	def icon(self) -> str:
		"""Return the icon for the sensor."""
		return "mdi:sleep" if self.is_on else "mdi:sleep-off"

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		time_data = self._get_device_time_data()
		if not time_data:
			return {}

		attributes = {
			"device_id": self._device_id,
			"device_name": self._device_name,
			"child_id": self._child_id,
			"child_name": self._child_name,
		}

		bedtime_window = time_data.get("bedtime_window")
		if bedtime_window:
			start_ms = bedtime_window.get("start_ms")
			end_ms = bedtime_window.get("end_ms")
			if start_ms:
				from datetime import datetime
				attributes["bedtime_start"] = datetime.fromtimestamp(start_ms / 1000).isoformat()
			if end_ms:
				from datetime import datetime
				attributes["bedtime_end"] = datetime.fromtimestamp(end_ms / 1000).isoformat()

		return attributes


class SchoolTimeActiveBinarySensor(DeviceTimeBinarySensor):
	"""Binary sensor indicating if device is currently in school time window."""

	_attr_device_class = BinarySensorDeviceClass.RUNNING

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device_id: str,
		device_name: str,
		device: dict[str, Any],
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the school time active sensor."""
		super().__init__(coordinator, device_id, device_name, device, child_id, child_name)

		self._attr_name = f"{device_name} School Time Active"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_{device_id}_schooltime_active"

	@property
	def is_on(self) -> bool:
		"""Return True if device is currently in school time window."""
		time_data = self._get_device_time_data()
		if not time_data:
			return False

		return time_data.get("schooltime_active", False)

	@property
	def icon(self) -> str:
		"""Return the icon for the sensor."""
		return "mdi:school" if self.is_on else "mdi:school-outline"

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		time_data = self._get_device_time_data()
		if not time_data:
			return {}

		attributes = {
			"device_id": self._device_id,
			"device_name": self._device_name,
			"child_id": self._child_id,
			"child_name": self._child_name,
		}

		schooltime_window = time_data.get("schooltime_window")
		if schooltime_window:
			start_ms = schooltime_window.get("start_ms")
			end_ms = schooltime_window.get("end_ms")
			if start_ms:
				from datetime import datetime
				attributes["schooltime_start"] = datetime.fromtimestamp(start_ms / 1000).isoformat()
			if end_ms:
				from datetime import datetime
				attributes["schooltime_end"] = datetime.fromtimestamp(end_ms / 1000).isoformat()

		return attributes


class DailyLimitReachedBinarySensor(DeviceTimeBinarySensor):
	"""Binary sensor indicating if device has reached its daily time limit."""

	_attr_device_class = BinarySensorDeviceClass.PROBLEM

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		device_id: str,
		device_name: str,
		device: dict[str, Any],
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the daily limit reached sensor."""
		super().__init__(coordinator, device_id, device_name, device, child_id, child_name)

		self._attr_name = f"{device_name} Daily Limit Reached"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_{device_id}_daily_limit_reached"

	@property
	def is_on(self) -> bool:
		"""Return True if device has reached or exceeded its daily limit."""
		time_data = self._get_device_time_data()
		if not time_data:
			return False

		remaining_minutes = time_data.get("remaining_minutes")
		if remaining_minutes is None:
			return False

		return remaining_minutes <= 0

	@property
	def icon(self) -> str:
		"""Return the icon for the sensor."""
		return "mdi:timer-alert" if self.is_on else "mdi:timer-check"

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		time_data = self._get_device_time_data()
		if not time_data:
			return {}

		attributes = {
			"device_id": self._device_id,
			"device_name": self._device_name,
			"child_id": self._child_id,
			"child_name": self._child_name,
		}

		remaining_minutes = time_data.get("remaining_minutes")
		if remaining_minutes is not None:
			attributes["remaining_minutes"] = remaining_minutes

		return attributes
