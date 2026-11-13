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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER_NAME
from .permissions import async_check_entity_action
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
			entities.append(FamilyLinkSchoolTimeTime(coordinator, child_id, child_name, day, BOUND_START))
			entities.append(FamilyLinkSchoolTimeTime(coordinator, child_id, child_name, day, BOUND_END))
	async_add_entities(entities)


class FamilyLinkBedtimeTime(CoordinatorEntity, TimeEntity):
	"""Start or end of the bedtime of one weekday."""

	_attr_has_entity_name = True
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
		label = "start" if bound == BOUND_START else "end"
		self._attr_name = f"{DAY_NAMES[day]} bedtime {label}"
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
		await async_check_entity_action(self)
		client = self.coordinator.client
		if client is None:
			raise HomeAssistantError("Cannot set the bedtime: client not connected")
		slot = self._slot() or {}
		start = self._as_time(slot.get("start"))
		end = self._as_time(slot.get("end"))
		if self._bound == BOUND_START:
			start = value
		else:
			end = value
		if start is None or end is None:
			raise HomeAssistantError(f"Cannot set the {DAY_NAMES[self._day]} bedtime of {self._child_name}: the other bound is unknown")
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
		await self.coordinator.async_request_refresh()
		if not success:
			raise HomeAssistantError(f"Failed to set the {DAY_NAMES[self._day]} bedtime of {self._child_name}")


class FamilyLinkSchoolTimeTime(FamilyLinkBedtimeTime):
	"""Start or end of the weekly school time of one weekday.

	Unavailable for weekdays without a school time window in Family Link
	(Google does not create a slot from the weekly update call). A school day
	with a break is stored by Google as several slots on the same day (issue
	#190): the start is the earliest slot's, the end the latest slot's, and the
	slots are listed in the ``windows`` attribute. A day whose slots are all
	disabled reads unknown.
	"""

	def __init__(
		self,
		coordinator: FamilyLinkDataUpdateCoordinator,
		child_id: str,
		child_name: str,
		day: int,
		bound: str,
	) -> None:
		"""Initialize the time entity."""
		super().__init__(coordinator, child_id, child_name, day, bound)
		label = "start" if bound == BOUND_START else "end"
		self._attr_name = f"{DAY_NAMES[day]} school time {label}"
		self._attr_unique_id = f"{DOMAIN}_{child_id}_schooltime_{day}_{bound}"
		self._attr_icon = "mdi:school" if bound == BOUND_START else "mdi:school-outline"

	def _day_slots(self) -> list[dict[str, Any]]:
		"""The enabled school time slots of this weekday, earliest first."""
		rows: list[dict[str, Any]] = []
		for child_data in (self.coordinator.data or {}).get("children_data", []):
			if child_data.get("child_id") == self._child_id:
				rows = [
					slot for slot in child_data.get("school_time_schedule") or []
					if slot.get("day") == self._day and slot.get("enabled")
				]
		return sorted(rows, key=lambda slot: tuple(slot.get("start") or [0, 0]))

	def _has_rows(self) -> bool:
		for child_data in (self.coordinator.data or {}).get("children_data", []):
			if child_data.get("child_id") == self._child_id:
				return any(
					slot.get("day") == self._day for slot in child_data.get("school_time_schedule") or []
				)
		return False

	def _slot(self) -> dict[str, Any] | None:
		"""The school day as one window: earliest start, latest end, slots listed.

		None when Family Link has no slot at all for the day (entity unavailable);
		a window without bounds when the day's slots are all disabled (unknown).
		"""
		slots = self._day_slots()
		if not slots:
			return {"enabled": False, "start": None, "end": None, "windows": []} if self._has_rows() else None
		last = max(slots, key=lambda slot: tuple(slot.get("end") or [0, 0]))
		return {
			"enabled": True,
			"start": slots[0].get("start"),
			"end": last.get("end"),
			"windows": [
				f"{self._as_time(slot.get('start')):%H:%M}-{self._as_time(slot.get('end')):%H:%M}"
				for slot in slots
				if self._as_time(slot.get("start")) and self._as_time(slot.get("end"))
			],
			"first_slot": slots[0],
			"last_slot": last,
		}

	@property
	def extra_state_attributes(self) -> dict[str, Any]:
		"""The whole school day, slots included, for cards."""
		slot = self._slot() or {}
		return {
			"child_id": self._child_id,
			"child_name": self._child_name,
			"day": self._day,
			"day_name": DAY_NAMES[self._day],
			"enabled": slot.get("enabled"),
			"start": slot.get("start"),
			"end": slot.get("end"),
			"windows": slot.get("windows", []),
		}

	async def async_set_value(self, value: time) -> None:
		"""Rewrite the weekly school time slot of this weekday with the new bound.

		With a break, the start belongs to the first slot and the end to the
		last one; the slot in between is left alone, so the break survives.
		"""
		await async_check_entity_action(self)
		client = self.coordinator.client
		if client is None:
			raise HomeAssistantError("Cannot set the school time: client not connected")
		day = self._slot() or {}
		target = day.get("first_slot" if self._bound == BOUND_START else "last_slot") or {}
		start = self._as_time(target.get("start"))
		end = self._as_time(target.get("end"))
		if self._bound == BOUND_START:
			start = value
		else:
			end = value
		if start is None or end is None:
			raise HomeAssistantError(f"Cannot set the {DAY_NAMES[self._day]} school time of {self._child_name}: the other bound is unknown")
		start_text, end_text = start.strftime("%H:%M"), end.strftime("%H:%M")
		_LOGGER.info(f"Setting the {DAY_NAMES[self._day]} school time of {self._child_name} to {start_text}-{end_text}")
		success = await client.async_set_school_time(
			start_text, end_text, day=self._day, account_id=self._child_id, scope="weekly",
			slot_id=target.get("slot_id"),
		)
		await self.coordinator.async_request_refresh()
		if not success:
			raise HomeAssistantError(f"Failed to set the {DAY_NAMES[self._day]} school time of {self._child_name}")
