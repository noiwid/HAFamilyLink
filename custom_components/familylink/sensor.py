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


class ChildDataMixin:
	"""Mixin to provide child-specific data access."""

	def __init__(self, *args, child_id: str, child_name: str, **kwargs):
		"""Initialize with child information."""
		self._child_id = child_id
		self._child_name = child_name
		super().__init__(*args, **kwargs)

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
			identifiers={(DOMAIN, f"familylink_{self._child_id}")},
			name=f"Google Family Link ({self._child_name})",
			manufacturer="Google",
			model="Family Link Account",
		)


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up Family Link sensor entities from a config entry."""
	coordinator = hass.data[DOMAIN][entry.entry_id]

	entities = []

	# Wait for first data fetch to get children
	if not coordinator.data or "children_data" not in coordinator.data:
		_LOGGER.warning("No children data available yet, sensors will be added on first update")
		return

	# Create sensors for each supervised child
	for child_data in coordinator.data.get("children_data", []):
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]

		_LOGGER.debug(f"Creating sensors for child: {child_name}")

		# Screen time sensors
		entities.append(FamilyLinkScreenTimeSensor(coordinator, "total", child_id, child_name))
		entities.append(FamilyLinkScreenTimeFormattedSensor(coordinator, child_id, child_name))

		# App statistics sensors
		entities.append(FamilyLinkAppCountSensor(coordinator, child_id, child_name))
		entities.append(FamilyLinkBlockedAppsSensor(coordinator, child_id, child_name))
		entities.append(FamilyLinkAppsWithLimitsSensor(coordinator, child_id, child_name))

		# Top apps sensors (top 10)
		for i in range(1, 11):
			entities.append(FamilyLinkTopAppSensor(coordinator, i, child_id, child_name))

		# Device sensors
		entities.append(FamilyLinkDeviceCountSensor(coordinator, child_id, child_name))

		# Child info sensor
		entities.append(FamilyLinkChildInfoSensor(coordinator, child_id, child_name))

	async_add_entities(entities, update_before_add=True)


class FamilyLinkScreenTimeSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for daily screen time in minutes."""

	_attr_device_class = SensorDeviceClass.DURATION
	_attr_state_class = SensorStateClass.TOTAL
	_attr_native_unit_of_measurement = UnitOfTime.MINUTES
	_attr_icon = "mdi:timer-outline"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		sensor_type: str,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)

		self._sensor_type = sensor_type
		self._attr_name = f"Family Link Daily Screen Time"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_screen_time_{sensor_type}"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)
		self._attr_name = f"{child_name} Daily Screen Time"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_screen_time_{sensor_type}"

	@property
	def native_value(self) -> float | None:
		"""Return the state of the sensor in minutes."""
		child_data = self._get_child_data()
		if not child_data or "screen_time" not in child_data:
			return None

		screen_time = child_data["screen_time"]
		if not screen_time:
			return None

		# Convert seconds to minutes (rounded to 1 decimal place)
		total_seconds = screen_time.get("total_seconds", 0)
		return round(total_seconds / 60, 1)

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		return (
			self.coordinator.last_update_success
			and child_data is not None
			and "screen_time" in child_data
			and child_data["screen_time"] is not None
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "screen_time" not in child_data:
			return {}

		screen_time = child_data["screen_time"]
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


class FamilyLinkScreenTimeFormattedSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for daily screen time in formatted HH:MM:SS."""

	_attr_icon = "mdi:clock-time-eight-outline"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)

		self._attr_name = f"Family Link Screen Time Formatted"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_screen_time_formatted"
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)

		self._attr_name = f"{child_name} Screen Time Formatted"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_screen_time_formatted"

	@property
	def native_value(self) -> str | None:
		"""Return the state of the sensor as formatted time."""
		child_data = self._get_child_data()
		if not child_data or "screen_time" not in child_data:
			return None

		screen_time = child_data["screen_time"]
		if not screen_time:
			return None

		return screen_time.get("formatted", "00:00:00")

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		return (
			self.coordinator.last_update_success
			and child_data is not None
			and "screen_time" in child_data
			and child_data["screen_time"] is not None
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "screen_time" not in child_data:
			return {}

		screen_time = child_data["screen_time"]
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


class FamilyLinkAppCountSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for total number of installed apps."""

	_attr_icon = "mdi:apps"
	_attr_state_class = SensorStateClass.MEASUREMENT

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Installed Apps"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_app_count"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)
		self._attr_name = f"{child_name} Installed Apps"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_app_count"

	@property
	def native_value(self) -> int | None:
		"""Return the number of installed apps."""
		child_data = self._get_child_data()
		if not child_data or "apps" not in child_data:
			return None
		return len(child_data["apps"])

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		return (
			self.coordinator.last_update_success
			and child_data is not None
			and "apps" in child_data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "apps" not in child_data:
			return {}

		apps = child_data["apps"]
		blocked = sum(1 for app in apps if app.get("supervisionSetting", {}).get("hidden", False))
		with_limits = sum(1 for app in apps if app.get("supervisionSetting", {}).get("usageLimit"))
		always_allowed = sum(1 for app in apps if app.get("supervisionSetting", {}).get("alwaysAllowedAppInfo"))

		return {
			"total_apps": len(apps),
			"blocked_apps": blocked,
			"apps_with_time_limits": with_limits,
			"always_allowed_apps": always_allowed,
		}


class FamilyLinkBlockedAppsSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for blocked/hidden apps."""

	_attr_icon = "mdi:block-helper"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Blocked Apps"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_blocked_apps"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)
		self._attr_name = f"{child_name} Blocked Apps"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_blocked_apps"

	@property
	def native_value(self) -> int:
		"""Return the number of blocked apps."""
		child_data = self._get_child_data()
		if not child_data or "apps" not in child_data:
			return 0

		apps = child_data["apps"]
		return sum(1 for app in apps if app.get("supervisionSetting", {}).get("hidden", False))

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		return (
			self.coordinator.last_update_success
			and child_data is not None
			and "apps" in child_data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "apps" not in child_data:
			return {}

		apps = child_data["apps"]
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


class FamilyLinkAppsWithLimitsSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for apps with time limits."""

	_attr_icon = "mdi:timer-sand"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Apps with Time Limits"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_apps_with_limits"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)
		self._attr_name = f"{child_name} Apps with Time Limits"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_apps_with_limits"

	@property
	def native_value(self) -> int:
		"""Return the number of apps with time limits."""
		child_data = self._get_child_data()
		if not child_data or "apps" not in child_data:
			return 0

		apps = child_data["apps"]
		return sum(1 for app in apps if app.get("supervisionSetting", {}).get("usageLimit"))

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		return (
			self.coordinator.last_update_success
			and child_data is not None
			and "apps" in child_data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "apps" not in child_data:
			return {}

		apps = child_data["apps"]
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


class FamilyLinkTopAppSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for individual top app usage."""

	_attr_device_class = SensorDeviceClass.DURATION
	_attr_native_unit_of_measurement = UnitOfTime.MINUTES
	_attr_icon = "mdi:star"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		rank: int,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)
		self._rank = rank
		self._attr_name = f"Family Link Top App #{rank}"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_top_app_{rank}"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)
		self._attr_name = f"{child_name} Top App #{rank}"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_top_app_{rank}"

	@property
	def native_value(self) -> float | None:
		"""Return usage time in minutes for this top app."""
		child_data = self._get_child_data()
		if not child_data or "screen_time" not in child_data:
			return None

		screen_time = child_data["screen_time"]
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
		child_data = self._get_child_data()
		if not (
			self.coordinator.last_update_success
			and child_data is not None
			and "screen_time" in child_data
		):
			return False

		screen_time = child_data["screen_time"]
		if not screen_time:
			return False

		app_breakdown = screen_time.get("app_breakdown", {})
		return len(app_breakdown) >= self._rank

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "screen_time" not in child_data:
			return {}

		screen_time = child_data["screen_time"]
		if not screen_time:
			return {}

		app_breakdown = screen_time.get("app_breakdown", {})
		if not app_breakdown or len(app_breakdown) < self._rank:
			return {}

		sorted_apps = sorted(app_breakdown.items(), key=lambda x: x[1], reverse=True)
		package, seconds = sorted_apps[self._rank - 1]

		# Find app details
		app_name = package
		apps = child_data.get("apps", [])
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


class FamilyLinkDeviceCountSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for number of devices."""

	_attr_icon = "mdi:devices"
	_attr_state_class = SensorStateClass.MEASUREMENT

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Device Count"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_device_count"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)
		self._attr_name = f"{child_name} Device Count"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_device_count"

	@property
	def native_value(self) -> int:
		"""Return the number of devices."""
		child_data = self._get_child_data()
		if not child_data or "devices" not in child_data:
			return 0
		return len(child_data["devices"])

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		return (
			self.coordinator.last_update_success
			and child_data is not None
			and "devices" in child_data
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "devices" not in child_data:
			return {}

		devices = child_data["devices"]
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


class FamilyLinkChildInfoSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for supervised child information."""

	_attr_icon = "mdi:account-child"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)
		self._attr_name = "Family Link Child Info"
		self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_child_info"

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, "familylink_account")},
			name="Google Family Link",
			manufacturer="Google",
			model="Family Link Account",
		)
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)
		self._attr_name = f"{child_name} Child Info"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_child_info"

	@property
	def native_value(self) -> str | None:
		"""Return the child's display name."""
		child_data = self._get_child_data()
		if not child_data or "child" not in child_data:
			return None

		child = child_data["child"]
		if not child:
			return None

		return child.get("profile", {}).get("displayName", "Unknown")

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		return (
			self.coordinator.last_update_success
			and child_data is not None
			and "child" in child_data
			and child_data["child"] is not None
		)

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "child" not in child_data:
			return {}

		child = child_data["child"]
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
