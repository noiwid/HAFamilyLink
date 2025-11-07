"""Sensor platform for Google Family Link integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
	SensorDeviceClass,
	SensorEntity,
	SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
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
	"""Set up Family Link sensor entities from a config entry."""
	coordinator = hass.data[DOMAIN][entry.entry_id]

	entities = []

	# Create screen time sensors
	entities.append(FamilyLinkScreenTimeSensor(coordinator, "total"))
	entities.append(FamilyLinkScreenTimeFormattedSensor(coordinator))

	async_add_entities(entities, update_before_add=True)


class FamilyLinkScreenTimeSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for daily screen time in minutes."""

	_attr_device_class = SensorDeviceClass.DURATION
	_attr_state_class = SensorStateClass.TOTAL
	_attr_native_unit_of_measurement = UnitOfTime.MINUTES
	_attr_icon = "mdi:timer-outline"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		sensor_type: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)

		self._sensor_type = sensor_type
		self._attr_name = f"Family Link Daily Screen Time"
		self._attr_unique_id = f"{DOMAIN}_screen_time_{sensor_type}"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)

	@property
	def native_value(self) -> float | None:
		"""Return the state of the sensor in minutes."""
		if not self.coordinator.data or "screen_time" not in self.coordinator.data:
			return None

		screen_time = self.coordinator.data["screen_time"]
		if not screen_time:
			return None

		# Convert seconds to minutes (rounded to 1 decimal place)
		total_seconds = screen_time.get("total_seconds", 0)
		return round(total_seconds / 60, 1)

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "screen_time" in self.coordinator.data
			and self.coordinator.data["screen_time"] is not None
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "screen_time" not in self.coordinator.data:
			return {}

		screen_time = self.coordinator.data["screen_time"]
		if not screen_time:
			return {}

		attributes = {
			"total_seconds": screen_time.get("total_seconds", 0),
			"formatted_time": screen_time.get("formatted", "00:00:00"),
			"hours": screen_time.get("hours", 0),
			"minutes": screen_time.get("minutes", 0),
			"seconds": screen_time.get("seconds", 0),
			"date": str(screen_time.get("date", datetime.now().date())),
			"app_count": len(screen_time.get("app_breakdown", {})),
		}

		# Add top 5 apps by usage
		app_breakdown = screen_time.get("app_breakdown", {})
		if app_breakdown:
			sorted_apps = sorted(
				app_breakdown.items(),
				key=lambda x: x[1],
				reverse=True
			)[:5]

			for idx, (package, seconds) in enumerate(sorted_apps, 1):
				hours = int(seconds // 3600)
				mins = int((seconds % 3600) // 60)
				secs = int(seconds % 60)
				attributes[f"top_app_{idx}"] = package
				attributes[f"top_app_{idx}_time"] = f"{hours:02d}:{mins:02d}:{secs:02d}"
				attributes[f"top_app_{idx}_minutes"] = round(seconds / 60, 1)

		return attributes


class FamilyLinkScreenTimeFormattedSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for daily screen time in formatted HH:MM:SS."""

	_attr_icon = "mdi:clock-time-eight-outline"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)

		self._attr_name = f"Family Link Screen Time Formatted"
		self._attr_unique_id = f"{DOMAIN}_screen_time_formatted"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)

	@property
	def native_value(self) -> str | None:
		"""Return the state of the sensor as formatted time."""
		if not self.coordinator.data or "screen_time" not in self.coordinator.data:
			return None

		screen_time = self.coordinator.data["screen_time"]
		if not screen_time:
			return None

		return screen_time.get("formatted", "00:00:00")

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "screen_time" in self.coordinator.data
			and self.coordinator.data["screen_time"] is not None
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "screen_time" not in self.coordinator.data:
			return {}

		screen_time = self.coordinator.data["screen_time"]
		if not screen_time:
			return {}

		return {
			"total_seconds": screen_time.get("total_seconds", 0),
			"total_minutes": round(screen_time.get("total_seconds", 0) / 60, 1),
			"hours": screen_time.get("hours", 0),
			"minutes": screen_time.get("minutes", 0),
			"seconds": screen_time.get("seconds", 0),
			"date": str(screen_time.get("date", datetime.now().date())),
		}
