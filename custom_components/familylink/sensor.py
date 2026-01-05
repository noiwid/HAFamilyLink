"""Sensor platform for Google Family Link integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENABLE_LOCATION_TRACKING, DOMAIN, INTEGRATION_NAME, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(LOGGER_NAME)

# Day of week mapping
DAYS_OF_WEEK = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


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
            identifiers={(DOMAIN, self._child_id)},
            name=f"{self._child_name} (Family Link)",
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

    # Check if data is available (should be after async_config_entry_first_refresh)
    if not coordinator.data or "children_data" not in coordinator.data:
        _LOGGER.error(
            "CRITICAL: No children data in coordinator after first refresh! "
            "Sensors will NOT be created. "
            f"coordinator.data keys: {list(coordinator.data.keys()) if coordinator.data else 'None'}"
        )
        # Don't return - this prevents entities from ever being created!

    # Create sensor entities for each child and their devices
    for child_data in coordinator.data.get("children_data", []):
        child_id = child_data["child_id"]
        child_name = child_data["child_name"]

        _LOGGER.debug(f"Creating sensors for {child_name}")

        # Original sensors (apps, screen time, etc.)
        entities.append(FamilyLinkScreenTimeSensor(coordinator, "total", child_id, child_name))
        entities.append(FamilyLinkScreenTimeFormattedSensor(coordinator, child_id, child_name))
        entities.append(FamilyLinkAppCountSensor(coordinator, child_id, child_name))
        entities.append(FamilyLinkBlockedAppsSensor(coordinator, child_id, child_name))
        entities.append(FamilyLinkAppsWithLimitsSensor(coordinator, child_id, child_name))

        # Top apps sensors (top 10)
        for i in range(1, 11):
            entities.append(FamilyLinkTopAppSensor(coordinator, i, child_id, child_name))

        # Device sensors
        entities.append(FamilyLinkDeviceCountSensor(coordinator, child_id, child_name))
        entities.append(FamilyLinkChildInfoSensor(coordinator, child_id, child_name))

        # Battery sensor (only if location tracking is enabled, as battery comes from location data)
        if entry.data.get(CONF_ENABLE_LOCATION_TRACKING, False):
            entities.append(FamilyLinkBatteryLevelSensor(coordinator, child_id, child_name))

        # Time management schedule sensors removed - data not available at child level
        # Schedules are available in binary_sensor attributes per device instead
        # entities.append(BedtimeScheduleSensor(coordinator, child_id, child_name))
        # entities.append(SchoolTimeScheduleSensor(coordinator, child_id, child_name))
        # entities.append(DailyLimitSensor(coordinator, child_id, child_name))

        # Create device sensors for each device (4 sensors per device)
        for device in child_data.get("devices", []):
            device_id = device["id"]
            device_name = device.get("name", "Unknown Device")

            entities.append(ScreenTimeRemainingSensor(coordinator, child_id, child_name, device_id, device_name))
            entities.append(NextRestrictionSensor(coordinator, child_id, child_name, device_id, device_name))
            entities.append(DailyLimitDeviceSensor(coordinator, child_id, child_name, device_id, device_name))
            entities.append(ActiveBonusSensor(coordinator, child_id, child_name, device_id, device_name))

    _LOGGER.debug(f"Created {len(entities)} total sensor entities")
    async_add_entities(entities, update_before_add=True)


class BedtimeScheduleSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing bedtime schedule for a child."""

    def __init__(
        self,
        coordinator: FamilyLinkDataUpdateCoordinator,
        child_id: str,
        child_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._child_id = child_id
        self._child_name = child_name
        self._attr_name = f"{child_name} Bedtime Schedule"
        self._attr_unique_id = f"{DOMAIN}_{child_id}_bedtime_schedule"
        self._attr_icon = "mdi:bed-clock"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=f"{self._child_name} (Family Link)",
            manufacturer="Google",
            model="Family Link Account",
        )

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    bedtime_schedule = child_data.get("bedtime_schedule", [])

                    if not bedtime_schedule:
                        return "Not configured"

                    # Get first schedule entry to display as main state
                    first_entry = bedtime_schedule[0]
                    start = first_entry.get("start", [0, 0])
                    end = first_entry.get("end", [0, 0])

                    start_str = f"{start[0]:02d}:{start[1]:02d}"
                    end_str = f"{end[0]:02d}:{end[1]:02d}"

                    return f"{start_str}-{end_str}"

        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "child_id": self._child_id,
            "child_name": self._child_name,
        }

        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    bedtime_schedule = child_data.get("bedtime_schedule", [])
                    bedtime_enabled = child_data.get("bedtime_enabled", False)

                    attributes["enabled"] = bedtime_enabled
                    attributes["schedule_count"] = len(bedtime_schedule)

                    # Add schedule for each day
                    for entry in bedtime_schedule:
                        day = entry.get("day")
                        start = entry.get("start", [0, 0])
                        end = entry.get("end", [0, 0])

                        if day is not None:
                            day_name = DAYS_OF_WEEK.get(day, f"Day{day}")
                            start_str = f"{start[0]:02d}:{start[1]:02d}"
                            end_str = f"{end[0]:02d}:{end[1]:02d}"
                            attributes[day_name.lower()] = f"{start_str}-{end_str}"

        return attributes


class SchoolTimeScheduleSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing school time schedule for a child."""

    def __init__(
        self,
        coordinator: FamilyLinkDataUpdateCoordinator,
        child_id: str,
        child_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._child_id = child_id
        self._child_name = child_name
        self._attr_name = f"{child_name} School Time Schedule"
        self._attr_unique_id = f"{DOMAIN}_{child_id}_school_time_schedule"
        self._attr_icon = "mdi:school-outline"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=f"{self._child_name} (Family Link)",
            manufacturer="Google",
            model="Family Link Account",
        )

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    school_time_schedule = child_data.get("school_time_schedule", [])

                    if not school_time_schedule:
                        return "Not configured"

                    # Get first schedule entry to display as main state
                    first_entry = school_time_schedule[0]
                    start = first_entry.get("start", [0, 0])
                    end = first_entry.get("end", [0, 0])

                    start_str = f"{start[0]:02d}:{start[1]:02d}"
                    end_str = f"{end[0]:02d}:{end[1]:02d}"

                    return f"{start_str}-{end_str}"

        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "child_id": self._child_id,
            "child_name": self._child_name,
        }

        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    school_time_schedule = child_data.get("school_time_schedule", [])
                    school_time_enabled = child_data.get("school_time_enabled", False)

                    attributes["enabled"] = school_time_enabled
                    attributes["schedule_count"] = len(school_time_schedule)

                    # Add schedule for each day
                    for entry in school_time_schedule:
                        day = entry.get("day")
                        start = entry.get("start", [0, 0])
                        end = entry.get("end", [0, 0])

                        if day is not None:
                            day_name = DAYS_OF_WEEK.get(day, f"Day{day}")
                            start_str = f"{start[0]:02d}:{start[1]:02d}"
                            end_str = f"{end[0]:02d}:{end[1]:02d}"
                            attributes[day_name.lower()] = f"{start_str}-{end_str}"

        return attributes


class DailyLimitSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing daily limit configuration for a child."""

    def __init__(
        self,
        coordinator: FamilyLinkDataUpdateCoordinator,
        child_id: str,
        child_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._child_id = child_id
        self._child_name = child_name
        self._attr_name = f"{child_name} Daily Limit"
        self._attr_unique_id = f"{DOMAIN}_{child_id}_daily_limit_config"
        self._attr_icon = "mdi:timer-outline"
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._child_id)},
            name=f"{self._child_name} (Family Link)",
            manufacturer="Google",
            model="Family Link Account",
        )

    @property
    def native_value(self) -> int | None:
        """Return the configured daily limit in minutes."""
        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    # Get daily limit from devices_time_data
                    devices_time_data = child_data.get("devices_time_data", {})

                    # Return the daily limit from the first device that has it configured
                    for device_id, time_data in devices_time_data.items():
                        if time_data.get("daily_limit_enabled"):
                            return time_data.get("daily_limit_minutes", 0)

                    # If no device has daily limit enabled, try to return the configured value anyway
                    for device_id, time_data in devices_time_data.items():
                        daily_limit = time_data.get("daily_limit_minutes", 0)
                        if daily_limit > 0:
                            return daily_limit

        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "child_id": self._child_id,
            "child_name": self._child_name,
        }

        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    daily_limit_enabled = child_data.get("daily_limit_enabled", False)
                    attributes["enabled"] = daily_limit_enabled

                    # Add per-device daily limits
                    devices_time_data = child_data.get("devices_time_data", {})
                    device_limits = {}

                    for device_id, time_data in devices_time_data.items():
                        if time_data.get("daily_limit_minutes", 0) > 0:
                            # Find device name
                            device_name = device_id
                            for device in child_data.get("devices", []):
                                if device["id"] == device_id:
                                    device_name = device.get("name", device_id)
                                    break

                            device_limits[device_name] = {
                                "enabled": time_data.get("daily_limit_enabled", False),
                                "minutes": time_data.get("daily_limit_minutes", 0),
                            }

                    if device_limits:
                        attributes["device_limits"] = device_limits

        return attributes


class ScreenTimeRemainingSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing remaining screen time for a device."""

    def __init__(
        self,
        coordinator: FamilyLinkDataUpdateCoordinator,
        child_id: str,
        child_name: str,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._child_id = child_id
        self._child_name = child_name
        self._device_id = device_id
        self._device_name = device_name
        self._attr_name = f"{device_name} Screen Time Remaining"
        self._attr_unique_id = f"{DOMAIN}_{child_id}_{device_id}_screen_time_remaining"
        self._attr_icon = "mdi:clock-time-four-outline"
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
            name=self._device_name,
            manufacturer="Google",
            model="Family Link Device",
            via_device=(DOMAIN, self._child_id),
        )

    @property
    def native_value(self) -> int | None:
        """Return remaining screen time in minutes."""
        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    devices_time_data = child_data.get("devices_time_data", {})

                    _LOGGER.debug(
                        f"ScreenTimeRemaining for device '{self._device_id}': "
                        f"devices_time_data keys = {list(devices_time_data.keys())}"
                    )

                    if self._device_id in devices_time_data:
                        time_data = devices_time_data[self._device_id]
                        remaining = time_data.get("remaining_minutes", 0)
                        _LOGGER.debug(
                            f"Found data for {self._device_id}: remaining={remaining}, "
                            f"total={time_data.get('total_allowed_minutes')}, used={time_data.get('used_minutes')}"
                        )
                        return remaining
                    else:
                        _LOGGER.debug(
                            f"Device ID '{self._device_id}' not found in devices_time_data "
                            f"(available: {list(devices_time_data.keys())})"
                        )

        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "child_id": self._child_id,
            "child_name": self._child_name,
            "device_id": self._device_id,
            "device_name": self._device_name,
        }

        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    devices_time_data = child_data.get("devices_time_data", {})

                    if self._device_id in devices_time_data:
                        time_data = devices_time_data[self._device_id]

                        attributes["total_allowed_minutes"] = time_data.get("total_allowed_minutes", 0)
                        attributes["used_minutes"] = time_data.get("used_minutes", 0)
                        attributes["daily_limit_enabled"] = time_data.get("daily_limit_enabled", False)
                        attributes["daily_limit_minutes"] = time_data.get("daily_limit_minutes", 0)

                        # Calculate percentage used
                        total = time_data.get("total_allowed_minutes", 0)
                        used = time_data.get("used_minutes", 0)
                        if total > 0:
                            attributes["percentage_used"] = round((used / total) * 100, 1)
                        else:
                            attributes["percentage_used"] = 0

        return attributes


class NextRestrictionSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the next upcoming time restriction."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: FamilyLinkDataUpdateCoordinator,
        child_id: str,
        child_name: str,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._child_id = child_id
        self._child_name = child_name
        self._device_id = device_id
        self._device_name = device_name
        self._attr_name = f"{device_name} Next Restriction"
        self._attr_unique_id = f"{DOMAIN}_{child_id}_{device_id}_next_restriction"
        self._attr_icon = "mdi:clock-alert-outline"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
            name=self._device_name,
            manufacturer="Google",
            model="Family Link Device",
            via_device=(DOMAIN, self._child_id),
        )

    def _calculate_time_until(self, target_ms: int) -> str | None:
        """Calculate human-readable time until target timestamp."""
        now_ms = int(datetime.now().timestamp() * 1000)
        diff_ms = target_ms - now_ms

        if diff_ms <= 0:
            return "Active now"

        diff_seconds = diff_ms // 1000
        hours = diff_seconds // 3600
        minutes = (diff_seconds % 3600) // 60

        if hours > 0:
            return f"in {hours}h{minutes:02d}"
        else:
            return f"in {minutes}min"

    @property
    def native_value(self) -> str | None:
        """Return description of next restriction."""
        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    devices_time_data = child_data.get("devices_time_data", {})

                    if self._device_id in devices_time_data:
                        time_data = devices_time_data[self._device_id]

                        # Check if bedtime is active
                        if time_data.get("bedtime_active"):
                            bedtime_window = time_data.get("bedtime_window")
                            if bedtime_window:
                                end_ms = bedtime_window.get("end_ms")
                                if end_ms:
                                    return f"Bedtime (ends {self._calculate_time_until(end_ms)})"

                        # Check if school time is active
                        if time_data.get("schooltime_active"):
                            schooltime_window = time_data.get("schooltime_window")
                            if schooltime_window:
                                end_ms = schooltime_window.get("end_ms")
                                if end_ms:
                                    return f"School time (ends {self._calculate_time_until(end_ms)})"

                        # Check upcoming bedtime
                        bedtime_window = time_data.get("bedtime_window")
                        if bedtime_window:
                            start_ms = bedtime_window.get("start_ms")
                            if start_ms:
                                time_until = self._calculate_time_until(start_ms)
                                if time_until and time_until != "Active now":
                                    return f"Bedtime {time_until}"

                        # Check upcoming school time
                        schooltime_window = time_data.get("schooltime_window")
                        if schooltime_window:
                            start_ms = schooltime_window.get("start_ms")
                            if start_ms:
                                time_until = self._calculate_time_until(start_ms)
                                if time_until and time_until != "Active now":
                                    return f"School time {time_until}"

                        # Check if daily limit is about to be reached
                        remaining = time_data.get("remaining_minutes", 0)
                        if time_data.get("daily_limit_enabled") and remaining > 0 and remaining <= 30:
                            return f"Daily limit {remaining}min remaining"

                        return "No restrictions"

        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = {
            "child_id": self._child_id,
            "child_name": self._child_name,
            "device_id": self._device_id,
            "device_name": self._device_name,
        }

        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    devices_time_data = child_data.get("devices_time_data", {})

                    if self._device_id in devices_time_data:
                        time_data = devices_time_data[self._device_id]

                        attributes["bedtime_active"] = time_data.get("bedtime_active", False)
                        attributes["schooltime_active"] = time_data.get("schooltime_active", False)

                        # Add window details if available
                        bedtime_window = time_data.get("bedtime_window")
                        if bedtime_window:
                            attributes["bedtime_start"] = datetime.fromtimestamp(
                                bedtime_window.get("start_ms", 0) / 1000
                            ).isoformat()
                            attributes["bedtime_end"] = datetime.fromtimestamp(
                                bedtime_window.get("end_ms", 0) / 1000
                            ).isoformat()

                        schooltime_window = time_data.get("schooltime_window")
                        if schooltime_window:
                            attributes["schooltime_start"] = datetime.fromtimestamp(
                                schooltime_window.get("start_ms", 0) / 1000
                            ).isoformat()
                            attributes["schooltime_end"] = datetime.fromtimestamp(
                                schooltime_window.get("end_ms", 0) / 1000
                            ).isoformat()

        return attributes


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


class DailyLimitDeviceSensor(CoordinatorEntity, SensorEntity):
	"""Sensor showing daily limit quota for a specific device."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
		device_id: str,
		device_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)

		self._child_id = child_id
		self._child_name = child_name
		self._device_id = device_id
		self._device_name = device_name
		self._attr_name = f"{device_name} Daily Limit"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_{device_id}_daily_limit"
		self._attr_icon = "mdi:timer-outline"
		self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
		self._attr_device_class = SensorDeviceClass.DURATION
		self._attr_state_class = SensorStateClass.MEASUREMENT

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
			name=self._device_name,
			manufacturer="Google",
			model="Family Link Device",
			via_device=(DOMAIN, self._child_id),
		)

	@property
	def native_value(self) -> int | None:
		"""Return configured daily limit in minutes."""
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					devices_time_data = child_data.get("devices_time_data", {})

					if self._device_id in devices_time_data:
						time_data = devices_time_data[self._device_id]
						return time_data.get("daily_limit_minutes", 0)

		return None

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		attributes = {
			"child_id": self._child_id,
			"child_name": self._child_name,
			"device_id": self._device_id,
			"device_name": self._device_name,
		}

		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					devices_time_data = child_data.get("devices_time_data", {})

					if self._device_id in devices_time_data:
						time_data = devices_time_data[self._device_id]
						attributes["enabled"] = time_data.get("daily_limit_enabled", False)

		return attributes


class ActiveBonusSensor(CoordinatorEntity, SensorEntity):
	"""Sensor showing active time bonus for a device."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
		device_id: str,
		device_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator)

		self._child_id = child_id
		self._child_name = child_name
		self._device_id = device_id
		self._device_name = device_name
		self._attr_name = f"{device_name} Active Bonus"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_{device_id}_active_bonus"
		self._attr_icon = "mdi:clock-plus-outline"
		self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
		self._attr_device_class = SensorDeviceClass.DURATION
		self._attr_state_class = SensorStateClass.MEASUREMENT

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
			name=self._device_name,
			manufacturer="Google",
			model="Family Link Device",
			via_device=(DOMAIN, self._child_id),
		)

	@property
	def native_value(self) -> int | None:
		"""Return active bonus time in minutes."""
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					devices_time_data = child_data.get("devices_time_data", {})

					if self._device_id in devices_time_data:
						time_data = devices_time_data[self._device_id]
						bonus = time_data.get("bonus_minutes", 0)
						# Return None instead of 0 when no bonus, so it shows as "unknown"
						return bonus if bonus > 0 else 0

		return None

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		attributes = {
			"child_id": self._child_id,
			"child_name": self._child_name,
			"device_id": self._device_id,
			"device_name": self._device_name,
		}

		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					devices_time_data = child_data.get("devices_time_data", {})

					if self._device_id in devices_time_data:
						time_data = devices_time_data[self._device_id]
						bonus_mins = time_data.get("bonus_minutes", 0)
						attributes["has_bonus"] = bonus_mins > 0

		return attributes


class FamilyLinkBatteryLevelSensor(ChildDataMixin, CoordinatorEntity, SensorEntity):
	"""Sensor for device battery level (from location data)."""

	_attr_device_class = SensorDeviceClass.BATTERY
	_attr_state_class = SensorStateClass.MEASUREMENT
	_attr_native_unit_of_measurement = PERCENTAGE
	_attr_icon = "mdi:battery"

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the sensor."""
		super().__init__(coordinator=coordinator, child_id=child_id, child_name=child_name)

		self._attr_name = f"{child_name} Battery Level"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_battery_level"

	@property
	def native_value(self) -> int | None:
		"""Return the battery level percentage."""
		child_data = self._get_child_data()
		if not child_data or "location" not in child_data:
			return None

		location = child_data["location"]
		if not location:
			return None

		return location.get("battery_level")

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		child_data = self._get_child_data()
		if not (
			self.coordinator.last_update_success
			and child_data is not None
			and "location" in child_data
			and child_data["location"] is not None
		):
			return False

		# Only available if we have battery data
		return child_data["location"].get("battery_level") is not None

	@property
	def icon(self) -> str:
		"""Return the icon based on battery level."""
		child_data = self._get_child_data()
		if not child_data or not child_data.get("location"):
			return "mdi:battery-unknown"

		location = child_data["location"]
		battery_level = location.get("battery_level")

		if battery_level is None:
			return "mdi:battery-unknown"

		if battery_level >= 90:
			return "mdi:battery"
		elif battery_level >= 70:
			return "mdi:battery-80"
		elif battery_level >= 50:
			return "mdi:battery-60"
		elif battery_level >= 30:
			return "mdi:battery-40"
		elif battery_level >= 10:
			return "mdi:battery-20"
		else:
			return "mdi:battery-alert-variant-outline"

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes."""
		child_data = self._get_child_data()
		if not child_data or "location" not in child_data:
			return {}

		location = child_data["location"]
		if not location:
			return {}

		attrs = {}

		if location.get("source_device_name"):
			attrs["source_device"] = location["source_device_name"]

		if location.get("timestamp_iso"):
			attrs["last_update"] = location["timestamp_iso"]

		return attrs
