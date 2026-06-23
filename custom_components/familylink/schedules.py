"""Schedule parsing helpers for Google Family Link responses."""
from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAY_NAMES = {
	1: "Monday",
	2: "Tuesday",
	3: "Wednesday",
	4: "Thursday",
	5: "Friday",
	6: "Saturday",
	7: "Sunday",
}

DAY_CODES = {
	1: "CAEQAQ",
	2: "CAEQAg",
	3: "CAEQAw",
	4: "CAEQBA",
	5: "CAEQBQ",
	6: "CAEQBg",
	7: "CAEQBw",
}

def _is_int(value: Any) -> bool:
	"""Return true for plain integers, excluding booleans."""
	return type(value) is int


def get_time_zone(value: str | None) -> ZoneInfo | None:
	"""Return a ZoneInfo for an IANA timezone name."""
	if not isinstance(value, str):
		return None

	name = value.strip()
	if not name:
		return None

	try:
		return ZoneInfo(name)
	except ZoneInfoNotFoundError:
		return None


def find_device_time_zone_name(source: Any) -> str | None:
	"""Find the device timezone from the known Family Link /devices response."""
	if not isinstance(source, list) or len(source) < 2 or not isinstance(source[1], list):
		return None

	for device in source[1]:
		if not isinstance(device, list) or len(device) <= 11:
			continue

		device_settings = device[11]
		if not isinstance(device_settings, list) or not device_settings:
			continue

		timezone = device_settings[0]
		if isinstance(timezone, str) and get_time_zone(timezone):
			return timezone.strip()

	return None


def _is_time_pair(value: Any) -> bool:
	"""Return true for [hour, minute] pairs."""
	return (
		isinstance(value, list)
		and len(value) == 2
		and _is_int(value[0])
		and _is_int(value[1])
		and 0 <= value[0] <= 23
		and 0 <= value[1] <= 59
	)


def format_time_pair(value: list[int]) -> str:
	"""Format a [hour, minute] pair as HH:MM."""
	return f"{value[0]:02d}:{value[1]:02d}"


def day_code_for(day: int) -> str:
	"""Return the Family Link day code for an ISO weekday."""
	if not _is_int(day) or day not in DAY_CODES:
		raise ValueError(f"Invalid day: {day}. Must be 1-7 (Monday-Sunday)")
	return DAY_CODES[day]


def parse_time_string(value: str) -> list[int]:
	"""Parse HH:MM into a Family Link [hour, minute] pair."""
	if not isinstance(value, str):
		raise ValueError("Time must be a string in HH:MM format")

	parts = value.split(":")
	if len(parts) != 2:
		raise ValueError(f"Invalid time: {value}. Expected HH:MM")

	try:
		pair = [int(parts[0]), int(parts[1])]
	except ValueError as err:
		raise ValueError(f"Invalid time: {value}. Expected HH:MM") from err

	if not _is_time_pair(pair):
		raise ValueError(f"Invalid time: {value}. Expected HH:MM in 24-hour time")

	return pair


def build_bedtime_schedule_update_payload(
	account_id: str,
	day: int,
	start_time: str,
	end_time: str,
) -> list[Any]:
	"""Build a recurring bedtime window update payload."""
	return [
		None,
		account_id,
		[[None, None, None, [[day_code_for(day), parse_time_string(start_time), parse_time_string(end_time)]]], None, None, None, []],
		None,
		[1],
	]


def build_bedtime_day_enabled_update_payload(
	account_id: str,
	day: int,
	enabled: bool,
) -> list[Any]:
	"""Build a recurring bedtime weekday on/off payload."""
	if type(enabled) is not bool:
		raise ValueError("enabled must be a boolean")

	return [
		None,
		account_id,
		[[None, None, [[day_code_for(day), 2 if enabled else 1]], None], None, None, None, []],
		None,
		[1],
	]


def build_daily_limit_schedule_update_payload(
	account_id: str,
	day: int,
	minutes: int,
) -> list[Any]:
	"""Build a recurring daily limit minutes update payload."""
	if not _is_int(minutes) or not 0 <= minutes <= 1440:
		raise ValueError("minutes must be an integer from 0 to 1440")

	return [
		None,
		account_id,
		[None, [[2, None, None, [[day_code_for(day), minutes]]]]],
		None,
		[1],
	]


def build_daily_limit_day_enabled_update_payload(
	account_id: str,
	day: int,
	enabled: bool,
) -> list[Any]:
	"""Build a recurring daily limit weekday on/off payload."""
	if type(enabled) is not bool:
		raise ValueError("enabled must be a boolean")

	return [
		None,
		account_id,
		[None, [[2, None, [[day_code_for(day), 2 if enabled else 1]], None]]],
		None,
		[1],
	]


def parse_window_schedule_items(items: Any, code_prefix: str) -> list[dict[str, Any]]:
	"""Parse bedtime or school time rows from a timeLimit schedule list."""
	schedules: list[dict[str, Any]] = []

	if not isinstance(items, list):
		return schedules

	for item in items:
		if not (isinstance(item, list) and len(item) >= 5):
			continue

		code = item[0]
		day = item[1] if len(item) > 1 else None
		state_flag = item[2] if len(item) > 2 else None
		start = item[3] if len(item) > 3 else None
		end = item[4] if len(item) > 4 else None

		if not (
			isinstance(code, str)
			and code.startswith(code_prefix)
			and _is_int(day)
			and day in DAY_NAMES
			and _is_int(state_flag)
			and _is_time_pair(start)
			and _is_time_pair(end)
		):
			continue

		schedules.append({
			"day": day,
			"day_name": DAY_NAMES[day],
			"enabled": state_flag == 2,
			"start": start,
			"end": end,
			"state_flag": state_flag,
		})

	return sorted(schedules, key=lambda slot: slot["day"])


def _walk_lists(value: Any):
	"""Yield nested lists from a response fragment."""
	if not isinstance(value, list):
		return

	yield value
	for item in value:
		if isinstance(item, list):
			yield from _walk_lists(item)


def parse_daily_limit_schedule(config: Any) -> list[dict[str, Any]]:
	"""Parse daily limit rows from the timeLimit daily limit config block."""
	schedules_by_day: dict[int, dict[str, Any]] = {}

	for item in _walk_lists(config):
		if len(item) < 4:
			continue

		code = item[0]
		day = item[1] if len(item) > 1 else None
		state_flag = item[2] if len(item) > 2 else None
		minutes = item[3] if len(item) > 3 else None

		if not (
			isinstance(code, str)
			and code.startswith("CAEQ")
			and _is_int(day)
			and day in DAY_NAMES
			and _is_int(state_flag)
			and _is_int(minutes)
			and minutes >= 0
		):
			continue

		schedules_by_day[day] = {
			"day": day,
			"day_name": DAY_NAMES[day],
			"enabled": state_flag == 2 and minutes > 0,
			"minutes": minutes,
			"state_flag": state_flag,
		}

	return [schedules_by_day[day] for day in sorted(schedules_by_day)]


def describe_effective_window(
	effective_start: str | None,
	effective_end: str | None,
	weekly_schedule: list[dict[str, Any]] | None,
	day: int,
) -> dict[str, Any]:
	"""Describe whether today's effective window matches the recurring schedule."""
	result = {
		"start": effective_start,
		"end": effective_end,
		"label": None,
		"source": "none",
		"weekly_start": None,
		"weekly_end": None,
		"weekly_label": None,
		"differs_from_weekly": False,
	}

	if effective_start and effective_end:
		result["label"] = f"{effective_start}-{effective_end}"

	if not _is_int(day) or day not in DAY_NAMES:
		return result

	for slot in weekly_schedule or []:
		if not isinstance(slot, dict) or slot.get("day") != day or not slot.get("enabled"):
			continue

		start = slot.get("start")
		end = slot.get("end")
		if not (_is_time_pair(start) and _is_time_pair(end)):
			continue

		result["weekly_start"] = format_time_pair(start)
		result["weekly_end"] = format_time_pair(end)
		result["weekly_label"] = f"{result['weekly_start']}-{result['weekly_end']}"
		break

	if not result["label"]:
		return result

	if result["weekly_label"] == result["label"]:
		result["source"] = "weekly"
		return result

	result["source"] = "today_override"
	result["differs_from_weekly"] = result["weekly_label"] is not None
	return result


def effective_bedtime_window_source(
	bedtime_window: dict[str, Any],
	bedtime_today_source: str | None,
) -> str:
	"""Return the source label for the active effective bedtime window."""
	if bedtime_window.get("label") and bedtime_today_source:
		return bedtime_today_source
	return bedtime_window.get("source") or "none"
