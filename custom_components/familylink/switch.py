"""Switch platform for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
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

	# Create switch entities for each child and their devices
	for child_data in coordinator.data.get("children_data", []):
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]

		_LOGGER.debug(f"Creating switches for {child_name}")

		# Create time limit control switches for this child
		entities.append(FamilyLinkBedtimeSwitch(coordinator, child_id, child_name))
		entities.append(FamilyLinkSchoolTimeSwitch(coordinator, child_id, child_name))
		entities.append(FamilyLinkDailyLimitSwitch(coordinator, child_id, child_name))

		# Create device lock/unlock switches for each device
		for device in child_data.get("devices", []):
			entities.append(FamilyLinkDeviceSwitch(coordinator, device, child_id, child_name))

	_LOGGER.debug(f"Created {len(entities)} total switch entities")
	async_add_entities(entities, update_before_add=True)


class FamilyLinkDeviceSwitch(CoordinatorEntity, SwitchEntity):
	"""Representation of a Family Link device as a smart switch that accounts for all restrictions."""

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
		self._child_id = child_id
		self._child_name = child_name
		self._attr_name = device.get("name", f"{child_name} Device {self._device_id}")
		self._attr_unique_id = f"{DOMAIN}_{child_id}_{self._device_id}"

	def _get_device_time_data(self) -> dict[str, Any] | None:
		"""Get time data for this device."""
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					devices_time_data = child_data.get("devices_time_data", {})
					return devices_time_data.get(self._device_id)
		return None

	def _get_current_device(self) -> dict[str, Any] | None:
		"""Get current device data."""
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					for device in child_data.get("devices", []):
						if device["id"] == self._device_id:
							return device
		return self._device

	@property
	def device_info(self) -> DeviceInfo:
		"""Return device information."""
		return DeviceInfo(
			identifiers={(DOMAIN, f"{self._child_id}_{self._device_id}")},
			name=self._attr_name,
			manufacturer="Google",
			model=self._device.get("model", "Family Link Device"),
			sw_version=self._device.get("version"),
			via_device=(DOMAIN, self._child_id),  # Link to parent (child's account device)
		)

	@property
	def is_on(self) -> bool:
		"""Return True if device is usable (not restricted)."""
		device = self._get_current_device()
		if not device:
			return True

		# If manually locked, always OFF
		if device.get("locked", False):
			return False

		# Get time restrictions
		time_data = self._get_device_time_data()
		if time_data:
			bedtime_active = time_data.get("bedtime_active", False)
			daily_limit_remaining = time_data.get("daily_limit_remaining", 1)
			bonus_active = time_data.get("bonus_minutes", 0) > 0

			# If bonus is active, device is usable regardless of other restrictions
			if bonus_active:
				return True

			# If restrictions active and no bonus, device is not usable
			if bedtime_active or daily_limit_remaining <= 0:
				return False

		# No restrictions, device is usable
		return True

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	@property
	def icon(self) -> str:
		"""Return dynamic icon based on device state."""
		device = self._get_current_device()
		time_data = self._get_device_time_data()

		if device and device.get("locked", False):
			return "mdi:cellphone-lock"

		if time_data:
			bonus_active = time_data.get("bonus_minutes", 0) > 0
			bedtime_active = time_data.get("bedtime_active", False)
			daily_limit_remaining = time_data.get("daily_limit_remaining", 1)

			if bonus_active:
				return "mdi:cellphone-clock"  # Bonus active
			if bedtime_active:
				return "mdi:cellphone-off"  # Bedtime
			if daily_limit_remaining <= 0:
				return "mdi:cellphone-remove"  # Daily limit reached

		return "mdi:cellphone"  # Normal/usable

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Return extra state attributes including restriction info."""
		attributes = {
			ATTR_DEVICE_ID: self._device_id,
			ATTR_DEVICE_NAME: self._attr_name,
			"child_id": self._child_id,
			"child_name": self._child_name,
		}

		# Get device data
		device = self._get_current_device()
		if device:
			if "type" in device:
				attributes[ATTR_DEVICE_TYPE] = device["type"]
			if "last_activity" in device:
				attributes[ATTR_LAST_SEEN] = device["last_activity"]
			if "locked" in device:
				attributes[ATTR_LOCKED] = device["locked"]
			if "model" in device:
				attributes["model"] = device["model"]

		# Get time restrictions
		time_data = self._get_device_time_data()
		if time_data:
			attributes["bedtime_active"] = time_data.get("bedtime_active", False)
			attributes["school_time_active"] = time_data.get("schooltime_active", False)
			attributes["daily_limit_reached"] = time_data.get("daily_limit_remaining", 1) <= 0
			attributes["bonus_active"] = time_data.get("bonus_minutes", 0) > 0
			attributes["bonus_minutes"] = time_data.get("bonus_minutes", 0)
			attributes["remaining_minutes"] = time_data.get("remaining_minutes", 0)

			# Add restriction reason
			if device and device.get("locked", False):
				attributes["restriction_reason"] = "manually_locked"
			elif time_data.get("bonus_minutes", 0) > 0:
				attributes["restriction_reason"] = "bonus_active"
			elif time_data.get("bedtime_active", False):
				attributes["restriction_reason"] = "bedtime_active"
			elif time_data.get("daily_limit_remaining", 1) <= 0:
				attributes["restriction_reason"] = "daily_limit_reached"
			else:
				attributes["restriction_reason"] = "none"

		return attributes

	async def async_turn_on(self) -> None:
		"""Unlock device (bypass restrictions without disabling bedtime/daily_limit)."""
		_LOGGER.info("Unlocking device %s for child %s (bypass restrictions)", self._device_id, self._child_name)

		success = await self.coordinator.async_control_device(
			self._device_id, DEVICE_UNLOCK_ACTION, self._child_id
		)

		if not success:
			_LOGGER.error("Failed to unlock device %s", self._device_id)
		else:
			_LOGGER.info("Successfully unlocked device %s", self._device_id)
			await self.coordinator.async_request_refresh()

	async def async_turn_off(self) -> None:
		"""Lock device (cancel bonus if active, then lock)."""
		_LOGGER.info("Locking device %s for child %s", self._device_id, self._child_name)

		# First, cancel any active bonus
		time_data = self._get_device_time_data()
		if time_data:
			override_id = time_data.get("bonus_override_id")
			if override_id:
				_LOGGER.info("Cancelling active bonus (override_id=%s) before locking", override_id)
				bonus_cancelled = await self.coordinator.client.async_cancel_time_bonus(
					override_id=override_id,
					account_id=self._child_id,
				)
				if bonus_cancelled:
					_LOGGER.info("Successfully cancelled bonus for device %s", self._device_id)
				else:
					_LOGGER.warning("Failed to cancel bonus for device %s", self._device_id)

		# Then lock the device
		success = await self.coordinator.async_control_device(
			self._device_id, DEVICE_LOCK_ACTION, self._child_id
		)

		if not success:
			_LOGGER.error("Failed to lock device %s", self._device_id)
		else:
			_LOGGER.info("Successfully locked device %s", self._device_id)
			await self.coordinator.async_request_refresh()


class FamilyLinkBedtimeSwitch(CoordinatorEntity, SwitchEntity):
	"""Representation of bedtime (downtime) control as a switch."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the switch."""
		super().__init__(coordinator)

		self._child_id = child_id
		self._child_name = child_name
		self._attr_name = f"{child_name} Bedtime"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_bedtime"
		self._attr_entity_category = EntityCategory.CONFIG

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
	def is_on(self) -> bool:
		"""Return True if bedtime is enabled."""
		# Check for pending state first (takes precedence for 5 seconds after change)
		pending_state = self.coordinator.get_pending_time_limit_state(self._child_id, "bedtime")
		if pending_state is not None:
			return pending_state

		# Otherwise use actual state from API
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					bedtime_state = child_data.get("bedtime_enabled")
					if bedtime_state is not None:
						return bedtime_state
		# Default to False if unknown
		return False

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	@property
	def icon(self) -> str:
		"""Return the icon for the switch."""
		return "mdi:sleep" if self.is_on else "mdi:sleep-off"

	async def async_turn_on(self) -> None:
		"""Enable bedtime."""
		_LOGGER.debug("Enabling bedtime for child %s", self._child_name)

		# Set pending state immediately for instant UI feedback
		self.coordinator.set_pending_time_limit_state(self._child_id, "bedtime", True)
		self.async_write_ha_state()

		success = await self.coordinator.client.async_enable_bedtime(account_id=self._child_id)

		if not success:
			_LOGGER.error("Failed to enable bedtime for %s", self._child_name)
		else:
			_LOGGER.info("Successfully enabled bedtime for %s", self._child_name)
			await self.coordinator.async_request_refresh()

	async def async_turn_off(self) -> None:
		"""Disable bedtime."""
		_LOGGER.debug("Disabling bedtime for child %s", self._child_name)

		# Set pending state immediately for instant UI feedback
		self.coordinator.set_pending_time_limit_state(self._child_id, "bedtime", False)
		self.async_write_ha_state()

		success = await self.coordinator.client.async_disable_bedtime(account_id=self._child_id)

		if not success:
			_LOGGER.error("Failed to disable bedtime for %s", self._child_name)
		else:
			_LOGGER.info("Successfully disabled bedtime for %s", self._child_name)
			await self.coordinator.async_request_refresh()


class FamilyLinkSchoolTimeSwitch(CoordinatorEntity, SwitchEntity):
	"""Representation of school time (evening limit) control as a switch."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the switch."""
		super().__init__(coordinator)

		self._child_id = child_id
		self._child_name = child_name
		self._attr_name = f"{child_name} School Time"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_school_time"
		self._attr_entity_category = EntityCategory.CONFIG

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
	def is_on(self) -> bool:
		"""Return True if school time is enabled."""
		# Check for pending state first (takes precedence for 5 seconds after change)
		pending_state = self.coordinator.get_pending_time_limit_state(self._child_id, "school_time")
		if pending_state is not None:
			return pending_state

		# Otherwise use actual state from API
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					school_time_state = child_data.get("school_time_enabled")
					if school_time_state is not None:
						return school_time_state
		# Default to False if unknown
		return False

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	@property
	def icon(self) -> str:
		"""Return the icon for the switch."""
		return "mdi:school" if self.is_on else "mdi:school-outline"

	async def async_turn_on(self) -> None:
		"""Enable school time."""
		_LOGGER.debug("Enabling school time for child %s", self._child_name)

		# Set pending state immediately for instant UI feedback
		self.coordinator.set_pending_time_limit_state(self._child_id, "school_time", True)
		self.async_write_ha_state()

		success = await self.coordinator.client.async_enable_school_time(account_id=self._child_id)

		if not success:
			_LOGGER.error("Failed to enable school time for %s", self._child_name)
		else:
			_LOGGER.info("Successfully enabled school time for %s", self._child_name)
			await self.coordinator.async_request_refresh()

	async def async_turn_off(self) -> None:
		"""Disable school time."""
		_LOGGER.debug("Disabling school time for child %s", self._child_name)

		# Set pending state immediately for instant UI feedback
		self.coordinator.set_pending_time_limit_state(self._child_id, "school_time", False)
		self.async_write_ha_state()

		success = await self.coordinator.client.async_disable_school_time(account_id=self._child_id)

		if not success:
			_LOGGER.error("Failed to disable school time for %s", self._child_name)
		else:
			_LOGGER.info("Successfully disabled school time for %s", self._child_name)
			await self.coordinator.async_request_refresh()


class FamilyLinkDailyLimitSwitch(CoordinatorEntity, SwitchEntity):
	"""Representation of daily limit control as a switch."""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
	) -> None:
		"""Initialize the switch."""
		super().__init__(coordinator)

		self._child_id = child_id
		self._child_name = child_name
		self._attr_name = f"{child_name} Daily Limit"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_daily_limit"
		self._attr_entity_category = EntityCategory.CONFIG

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
	def is_on(self) -> bool:
		"""Return True if daily limit is enabled."""
		# Check for pending state first (takes precedence for 5 seconds after change)
		pending_state = self.coordinator.get_pending_time_limit_state(self._child_id, "daily_limit")
		if pending_state is not None:
			return pending_state

		# Otherwise use actual state from API (read from time limit configuration)
		if self.coordinator.data and "children_data" in self.coordinator.data:
			for child_data in self.coordinator.data["children_data"]:
				if child_data["child_id"] == self._child_id:
					daily_limit_enabled = child_data.get("daily_limit_enabled")
					if daily_limit_enabled is not None:
						return daily_limit_enabled
		# Default to False if unknown
		return False

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self.coordinator.last_update_success

	@property
	def icon(self) -> str:
		"""Return the icon for the switch."""
		return "mdi:timer" if self.is_on else "mdi:timer-off"

	async def async_turn_on(self) -> None:
		"""Enable daily limit."""
		_LOGGER.debug("Enabling daily limit for child %s", self._child_name)

		# Set pending state immediately for instant UI feedback
		self.coordinator.set_pending_time_limit_state(self._child_id, "daily_limit", True)
		self.async_write_ha_state()

		success = await self.coordinator.client.async_enable_daily_limit(account_id=self._child_id)

		if not success:
			_LOGGER.error("Failed to enable daily limit for %s", self._child_name)
		else:
			_LOGGER.info("Successfully enabled daily limit for %s", self._child_name)
			await self.coordinator.async_request_refresh()

	async def async_turn_off(self) -> None:
		"""Disable daily limit."""
		_LOGGER.debug("Disabling daily limit for child %s", self._child_name)

		# Set pending state immediately for instant UI feedback
		self.coordinator.set_pending_time_limit_state(self._child_id, "daily_limit", False)
		self.async_write_ha_state()

		success = await self.coordinator.client.async_disable_daily_limit(account_id=self._child_id)

		if not success:
			_LOGGER.error("Failed to disable daily limit for %s", self._child_name)
		else:
			_LOGGER.info("Successfully disabled daily limit for %s", self._child_name)
			await self.coordinator.async_request_refresh() 