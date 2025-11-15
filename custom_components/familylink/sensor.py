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
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTEGRATION_NAME, LOGGER_NAME
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

    # Create sensor entities for each child and their devices
    for child_data in coordinator.data.get("children_data", []):
        child_id = child_data["child_id"]
        child_name = child_data["child_name"]

        _LOGGER.debug(f"Creating sensors for {child_name}")

        # Create schedule sensors for this child (3 sensors per child)
        entities.append(BedtimeScheduleSensor(coordinator, child_id, child_name))
        entities.append(SchoolTimeScheduleSensor(coordinator, child_id, child_name))
        entities.append(DailyLimitSensor(coordinator, child_id, child_name))

        # Create device sensors for each device (2 sensors per device)
        for device in child_data.get("devices", []):
            device_id = device["id"]
            device_name = device.get("name", "Unknown Device")

            entities.append(ScreenTimeRemainingSensor(coordinator, child_id, child_name, device_id, device_name))
            entities.append(NextRestrictionSensor(coordinator, child_id, child_name, device_id, device_name))

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
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"familylink_{self._child_id}")},
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
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"familylink_{self._child_id}")},
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
            identifiers={(DOMAIN, f"familylink_{self._child_id}")},
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
            via_device=(DOMAIN, f"familylink_{self._child_id}"),
        )

    @property
    def native_value(self) -> int | None:
        """Return remaining screen time in minutes."""
        if self.coordinator.data and "children_data" in self.coordinator.data:
            for child_data in self.coordinator.data["children_data"]:
                if child_data["child_id"] == self._child_id:
                    devices_time_data = child_data.get("devices_time_data", {})

                    if self._device_id in devices_time_data:
                        time_data = devices_time_data[self._device_id]
                        return time_data.get("remaining_minutes", 0)

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
            via_device=(DOMAIN, f"familylink_{self._child_id}"),
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
