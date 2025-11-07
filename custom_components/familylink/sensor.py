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

	# Screen time sensors
	entities.append(FamilyLinkScreenTimeSensor(coordinator, "total"))
	entities.append(FamilyLinkScreenTimeFormattedSensor(coordinator))

	# App statistics sensors
	entities.append(FamilyLinkAppCountSensor(coordinator))
	entities.append(FamilyLinkBlockedAppsSensor(coordinator))
	entities.append(FamilyLinkAppsWithLimitsSensor(coordinator))

	# Top apps sensors (top 10)
	for i in range(1, 11):
		entities.append(FamilyLinkTopAppSensor(coordinator, i))

	# Device sensors
	entities.append(FamilyLinkDeviceCountSensor(coordinator))

	# Child info sensor
	entities.append(FamilyLinkChildInfoSensor(coordinator))

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


class FamilyLinkAppCountSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for total number of installed apps."""

	_attr_icon = "mdi:apps"
	_attr_state_class = SensorStateClass.MEASUREMENT

	def __init__(self, coordinator: FamilyLinkDataUpdateCoordinator) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Installed Apps"
		self._attr_unique_id = f"{DOMAIN}_app_count"

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
	def native_value(self) -> int | None:
		"""Return the number of installed apps."""
		if not self.coordinator.data or "apps" not in self.coordinator.data:
			return None
		return len(self.coordinator.data["apps"])

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "apps" in self.coordinator.data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "apps" not in self.coordinator.data:
			return {}

		apps = self.coordinator.data["apps"]
		blocked = sum(1 for app in apps if app.get("supervisionSetting", {}).get("hidden", False))
		with_limits = sum(1 for app in apps if app.get("supervisionSetting", {}).get("usageLimit"))
		always_allowed = sum(1 for app in apps if app.get("supervisionSetting", {}).get("alwaysAllowedAppInfo"))

		return {
			"total_apps": len(apps),
			"blocked_apps": blocked,
			"apps_with_time_limits": with_limits,
			"always_allowed_apps": always_allowed,
		}


class FamilyLinkBlockedAppsSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for blocked/hidden apps."""

	_attr_icon = "mdi:block-helper"

	def __init__(self, coordinator: FamilyLinkDataUpdateCoordinator) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Blocked Apps"
		self._attr_unique_id = f"{DOMAIN}_blocked_apps"

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
	def native_value(self) -> int:
		"""Return the number of blocked apps."""
		if not self.coordinator.data or "apps" not in self.coordinator.data:
			return 0

		apps = self.coordinator.data["apps"]
		return sum(1 for app in apps if app.get("supervisionSetting", {}).get("hidden", False))

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "apps" in self.coordinator.data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "apps" not in self.coordinator.data:
			return {}

		apps = self.coordinator.data["apps"]
		blocked_apps = [
			{
				"name": app.get("title", "Unknown"),
				"package": app.get("packageName", ""),
			}
			for app in apps
			if app.get("supervisionSetting", {}).get("hidden", False)
		]

		return {
			"count": len(blocked_apps),
			"apps": blocked_apps[:20],  # Limit to 20 to avoid attribute size issues
		}


class FamilyLinkAppsWithLimitsSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for apps with time limits."""

	_attr_icon = "mdi:timer-sand"

	def __init__(self, coordinator: FamilyLinkDataUpdateCoordinator) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Apps with Time Limits"
		self._attr_unique_id = f"{DOMAIN}_apps_with_limits"

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
	def native_value(self) -> int:
		"""Return the number of apps with time limits."""
		if not self.coordinator.data or "apps" not in self.coordinator.data:
			return 0

		apps = self.coordinator.data["apps"]
		return sum(1 for app in apps if app.get("supervisionSetting", {}).get("usageLimit"))

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "apps" in self.coordinator.data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "apps" not in self.coordinator.data:
			return {}

		apps = self.coordinator.data["apps"]
		apps_with_limits = []

		for app in apps:
			usage_limit = app.get("supervisionSetting", {}).get("usageLimit")
			if usage_limit:
				apps_with_limits.append({
					"name": app.get("title", "Unknown"),
					"package": app.get("packageName", ""),
					"limit_minutes": usage_limit.get("dailyUsageLimitMins", 0),
					"enabled": usage_limit.get("enabled", False),
				})

		return {
			"count": len(apps_with_limits),
			"apps": apps_with_limits[:20],  # Limit to 20
		}


class FamilyLinkTopAppSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for individual top app usage."""

	_attr_device_class = SensorDeviceClass.DURATION
	_attr_native_unit_of_measurement = UnitOfTime.MINUTES
	_attr_icon = "mdi:star"

	def __init__(self, coordinator: FamilyLinkDataUpdateCoordinator, rank: int) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._rank = rank
		self._attr_name = f"Family Link Top App #{rank}"
		self._attr_unique_id = f"{DOMAIN}_top_app_{rank}"

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
		"""Return usage time in minutes for this top app."""
		if not self.coordinator.data or "screen_time" not in self.coordinator.data:
			return None

		screen_time = self.coordinator.data["screen_time"]
		if not screen_time:
			return None

		app_breakdown = screen_time.get("app_breakdown", {})
		if not app_breakdown:
			return None

		# Sort apps by usage
		sorted_apps = sorted(app_breakdown.items(), key=lambda x: x[1], reverse=True)

		# Check if this rank exists
		if len(sorted_apps) < self._rank:
			return None

		# Return usage in minutes
		package, seconds = sorted_apps[self._rank - 1]
		return round(seconds / 60, 1)

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		if not (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "screen_time" in self.coordinator.data
		):
			return False

		screen_time = self.coordinator.data["screen_time"]
		if not screen_time:
			return False

		app_breakdown = screen_time.get("app_breakdown", {})
		return len(app_breakdown) >= self._rank

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "screen_time" not in self.coordinator.data:
			return {}

		screen_time = self.coordinator.data["screen_time"]
		if not screen_time:
			return {}

		app_breakdown = screen_time.get("app_breakdown", {})
		if not app_breakdown or len(app_breakdown) < self._rank:
			return {}

		sorted_apps = sorted(app_breakdown.items(), key=lambda x: x[1], reverse=True)
		package, seconds = sorted_apps[self._rank - 1]

		# Find app details
		app_name = package
		apps = self.coordinator.data.get("apps", [])
		for app in apps:
			if app.get("packageName") == package:
				app_name = app.get("title", package)
				break

		hours = int(seconds // 3600)
		mins = int((seconds % 3600) // 60)
		secs = int(seconds % 60)

		return {
			"rank": self._rank,
			"app_name": app_name,
			"package_name": package,
			"total_seconds": seconds,
			"formatted_time": f"{hours:02d}:{mins:02d}:{secs:02d}",
			"hours": hours,
			"minutes": mins,
		}


class FamilyLinkDeviceCountSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for number of devices."""

	_attr_icon = "mdi:devices"
	_attr_state_class = SensorStateClass.MEASUREMENT

	def __init__(self, coordinator: FamilyLinkDataUpdateCoordinator) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Device Count"
		self._attr_unique_id = f"{DOMAIN}_device_count"

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
	def native_value(self) -> int:
		"""Return the number of devices."""
		if not self.coordinator.data or "devices" not in self.coordinator.data:
			return 0
		return len(self.coordinator.data["devices"])

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "devices" in self.coordinator.data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "devices" not in self.coordinator.data:
			return {}

		devices = self.coordinator.data["devices"]
		device_list = [
			{
				"name": device.get("name", "Unknown"),
				"model": device.get("model", "Unknown"),
				"id": device.get("id", ""),
			}
			for device in devices
		]

		return {
			"count": len(devices),
			"devices": device_list,
		}


class FamilyLinkChildInfoSensor(CoordinatorEntity, SensorEntity):
	"""Sensor for supervised child information."""

	_attr_icon = "mdi:account-child"

	def __init__(self, coordinator: FamilyLinkDataUpdateCoordinator) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Child Info"
		self._attr_unique_id = f"{DOMAIN}_child_info"

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
		"""Return the child's display name."""
		if not self.coordinator.data or "supervised_child" not in self.coordinator.data:
			return None

		child = self.coordinator.data["supervised_child"]
		if not child:
			return None

		return child.get("profile", {}).get("displayName", "Unknown")

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return (
			self.coordinator.last_update_success
			and self.coordinator.data is not None
			and "supervised_child" in self.coordinator.data
			and self.coordinator.data["supervised_child"] is not None
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		if not self.coordinator.data or "supervised_child" not in self.coordinator.data:
			return {}

		child = self.coordinator.data["supervised_child"]
		if not child:
			return {}

		profile = child.get("profile", {})
		birthday = profile.get("birthday", {})

		attrs = {
			"user_id": child.get("userId"),
			"role": child.get("role"),
			"display_name": profile.get("displayName"),
			"given_name": profile.get("givenName"),
			"family_name": profile.get("familyName"),
			"email": profile.get("email"),
		}

		if birthday:
			attrs["birthday"] = f"{birthday.get('year')}-{birthday.get('month'):02d}-{birthday.get('day'):02d}"

		if "ageBandLabel" in child:
			attrs["age_band"] = child["ageBandLabel"]

		return attrs
