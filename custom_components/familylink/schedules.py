"""Schedule parsing helpers for Google Family Link responses."""
from __future__ import annotations

from typing import Any

DAY_NAMES = {
	1: "Monday",
	2: "Tuesday",
	3: "Wednesday",
	4: "Thursday",
	5: "Friday",
	6: "Saturday",
	7: "Sunday",
}


def _is_int(value: Any) -> bool:
	"""Return true for plain integers, excluding booleans."""
	return type(value) is int


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
