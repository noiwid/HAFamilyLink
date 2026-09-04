"""Number platform: the daily screen time quota of each weekday, per child.

One entity per weekday, ``number.<child>_<weekday>_limit``, mirrors the
"Weekly limits" screen of Family Link: its value is the weekly quota of that
day, or today's override when Google applies one. Setting it writes the
weekly quota of that weekday as the app does; today's entity also posts
today's override on every device so the change applies at once.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator
from .devices import ensure_child_device
from .schedules import DAY_NAMES

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up the weekday quota numbers for every supervised child."""
	coordinator: FamilyLinkDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
	if not coordinator.data or "children_data" not in coordinator.data:
		_LOGGER.error("No children data in coordinator after first refresh, no number entities created")
		return

	entities = []
	for child_data in coordinator.data.get("children_data", []):
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]
		ensure_child_device(hass, coordinator, entry.entry_id, child_id, child_name)
		for day in range(1, 8):
			entities.append(FamilyLinkDailyLimitNumber(coordinator, child_id, child_name, day))
	async_add_entities(entities)


class FamilyLinkDailyLimitNumber(CoordinatorEntity, NumberEntity):
	"""Daily screen time quota of one weekday, in minutes."""

	_attr_native_min_value = 0
	_attr_native_max_value = 1440
	_attr_native_step = 5
	_attr_native_unit_of_measurement = UnitOfTime.MINUTES
	_attr_mode = NumberMode.BOX
	_attr_icon = "mdi:timer-sand"
	_attr_entity_category = EntityCategory.CONFIG

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
		day: int,
	) -> None:
		"""Initialize the number."""
		super().__init__(coordinator)
		self._child_id = child_id
		self._child_name = child_name
		self._day = day
		self._attr_name = f"{child_name} {DAY_NAMES[day]} Limit"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_daily_limit_{day}"

	@property
	def device_info(self) -> DeviceInfo:
		"""Attach to the child's hub device."""
		return DeviceInfo(
			identifiers={(DOMAIN, self._child_id)},
			name=f"{self._child_name} (Family Link)",
			manufacturer="Google",
			model="Family Link Account",
		)

	def _week_entry(self) -> dict[str, Any] | None:
		for child_data in (self.coordinator.data or {}).get("children_data", []):
			if child_data.get("child_id") == self._child_id:
				for entry in child_data.get("daily_limit_week") or []:
					if entry.get("day") == self._day:
						return entry
		return None

	@property
	def native_value(self) -> float | None:
		"""Quota in force for this weekday."""
		entry = self._week_entry()
		if not entry:
			return None
		return entry.get("effective_minutes")

	@property
	def available(self) -> bool:
		"""Available once the weekly schedule has been read."""
		return self.coordinator.last_update_success and self._week_entry() is not None

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""Weekly value, override and source of the value shown."""
		entry = self._week_entry() or {}
		return {
			"child_id": self._child_id,
			"child_name": self._child_name,
			"day": self._day,
			"day_name": DAY_NAMES[self._day],
			"weekly_minutes": entry.get("weekly_minutes"),
			"override_minutes": entry.get("override_minutes"),
			"applied_override": entry.get("applied_override"),
			"source": entry.get("source"),
			"enabled": entry.get("enabled"),
		}

	async def async_set_native_value(self, value: float) -> None:
		"""Write the weekly quota of this weekday; for today, also post today's override.

		The weekly row is what the app's weekly screen writes (captured
		2026-09-03). Google keeps applying today's override while one is in
		force, so today's entity also posts the override on every device, and
		the value applies at once.
		"""
		minutes = int(round(value))
		today = dt_util.now().isoweekday()
		client = self.coordinator.client
		if client is None:
			_LOGGER.error("Cannot set the daily limit: client not connected")
			return
		_LOGGER.info(f"Setting the {DAY_NAMES[self._day]} weekly daily limit of {self._child_name} to {minutes} min")
		ok = await client.async_set_weekly_daily_limit(self._day, minutes, self._child_id)
		if ok and self._day == today:
			device_ids = [
				device["id"]
				for child_data in (self.coordinator.data or {}).get("children_data", [])
				if child_data.get("child_id") == self._child_id
				for device in child_data.get("devices", [])
				if device.get("id")
			]
			for device_id in device_ids:
				success = await client.async_set_daily_limit(
					daily_minutes=minutes, device_id=device_id, account_id=self._child_id
				)
				ok = ok and success
		if ok:
			# The value chosen in Home Assistant is the reference for strict mode
			self.coordinator.record_daily_limit_minutes(self._child_id, minutes, self._day)
		else:
			_LOGGER.error(f"Failed to set the {DAY_NAMES[self._day]} daily limit of {self._child_name}")
		await self.coordinator.async_request_refresh()
