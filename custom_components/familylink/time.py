"""Time platform: bedtime start and end of each weekday, per child.

Two entities per weekday, ``time.<child>_<weekday>_bedtime_start`` and
``time.<child>_<weekday>_bedtime_end``, read the weekly bedtime schedule and
write it back through the same call as the ``set_bedtime`` action (weekly
scope): setting the start keeps the end, and the reverse.
"""
from __future__ import annotations

from datetime import time
import logging
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER_NAME
from .coordinator import FamilyLinkDataUpdateCoordinator
from .devices import ensure_child_device
from .schedules import DAY_NAMES

_LOGGER = logging.getLogger(LOGGER_NAME)

BOUND_START = "start"
BOUND_END = "end"


async def async_setup_entry(
	hass: HomeAssistant,
	entry: ConfigEntry,
	async_add_entities: AddEntitiesCallback,
) -> None:
	"""Set up the weekday bedtime times for every supervised child."""
	coordinator: FamilyLinkDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
	if not coordinator.data or "children_data" not in coordinator.data:
		_LOGGER.error("No children data in coordinator after first refresh, no time entities created")
		return

	entities = []
	for child_data in coordinator.data.get("children_data", []):
		child_id = child_data["child_id"]
		child_name = child_data["child_name"]
		ensure_child_device(hass, coordinator, entry.entry_id, child_id, child_name)
		for day in range(1, 8):
			entities.append(FamilyLinkBedtimeTime(coordinator, child_id, child_name, day, BOUND_START))
			entities.append(FamilyLinkBedtimeTime(coordinator, child_id, child_name, day, BOUND_END))
	async_add_entities(entities)


class FamilyLinkBedtimeTime(CoordinatorEntity, TimeEntity):
	"""Start or end of the bedtime of one weekday."""

	_attr_entity_category = EntityCategory.CONFIG

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
		day: int,
		bound: str,
	) -> None:
		"""Initialize the time entity."""
		super().__init__(coordinator)
		self._child_id = child_id
		self._child_name = child_name
		self._day = day
		self._bound = bound
		label = "Start" if bound == BOUND_START else "End"
		self._attr_name = f"{child_name} {DAY_NAMES[day]} Bedtime {label}"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_bedtime_{day}_{bound}"
		self._attr_icon = "mdi:weather-night" if bound == BOUND_START else "mdi:weather-sunny"

	@property
	def device_info(self) -> DeviceInfo:
		"""Attach to the child's hub device."""
		return DeviceInfo(
			identifiers={(DOMAIN, self._child_id)},
			name=f"{self._child_name} (Family Link)",
			manufacturer="Google",
			model="Family Link Account",
		)

	def _slot(self) -> dict[str, Any] | None:
		for child_data in (self.coordinator.data or {}).get("children_data", []):
			if child_data.get("child_id") == self._child_id:
				for slot in child_data.get("bedtime_schedule") or []:
					if slot.get("day") == self._day:
						return slot
		return None

	@staticmethod
	def _as_time(pair: Any) -> time | None:
		if isinstance(pair, (list, tuple)) and len(pair) == 2:
			try:
				return time(int(pair[0]), int(pair[1]))
			except (TypeError, ValueError):
				return None
		return None

	@property
	def native_value(self) -> time | None:
		"""Start or end of the weekly bedtime slot of this weekday."""
		slot = self._slot()
		if not slot:
			return None
		return self._as_time(slot.get(self._bound))

	@property
	def available(self) -> bool:
		"""Available once the weekly schedule has been read."""
		return self.coordinator.last_update_success and self._slot() is not None

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""The whole slot, for cards."""
		slot = self._slot() or {}
		return {
			"child_id": self._child_id,
			"child_name": self._child_name,
			"day": self._day,
			"day_name": DAY_NAMES[self._day],
			"enabled": slot.get("enabled"),
			"start": slot.get("start"),
			"end": slot.get("end"),
		}

	async def async_set_value(self, value: time) -> None:
		"""Rewrite the weekly bedtime slot of this weekday with the new bound."""
		client = self.coordinator.client
		if client is None:
			_LOGGER.error("Cannot set the bedtime: client not connected")
			return
		slot = self._slot() or {}
		start = self._as_time(slot.get("start"))
		end = self._as_time(slot.get("end"))
		if self._bound == BOUND_START:
			start = value
		else:
			end = value
		if start is None or end is None:
			_LOGGER.error(f"Cannot set the {DAY_NAMES[self._day]} bedtime of {self._child_name}: the other bound is unknown")
			return
		start_text, end_text = start.strftime("%H:%M"), end.strftime("%H:%M")
		_LOGGER.info(f"Setting the {DAY_NAMES[self._day]} bedtime of {self._child_name} to {start_text}-{end_text}")
		success = await client.async_set_bedtime(
			start_text, end_text, day=self._day, account_id=self._child_id, scope="weekly"
		)
		if success:
			# The hours chosen in Home Assistant are the reference for strict mode
			self.coordinator.record_bedtime_hours(
				self._child_id, self._day, [start.hour, start.minute], [end.hour, end.minute]
			)
		else:
			_LOGGER.error(f"Failed to set the {DAY_NAMES[self._day]} bedtime of {self._child_name}")
		await self.coordinator.async_request_refresh()
