"""Schedule parsing helpers for Google Family Link responses.

The timeLimit response is a positional JSON array with no field names, so the
shapes below are the contract. Confirmed against a live account:

  bedtime      ["CAEQAQ",   1, 2, [2, 0], [7, 0], ts, ts, rule_id]
  school time  ["CAMQASIk…", 1, 2, [8, 0], [15, 0], ts, ts, rule_id]
  daily limit  ["CAEQAQ",   1, 2, 480, ts, ts]

Bedtime and school-time rows share ONE list and are told apart by the slot id;
the daily-limit rows live in a separate block and reuse the bedtime ids, so
they are told apart by carrying minutes instead of an [h, m] window.

Slot ids are base64 protobuf: field 1 is the rule type (1 = bedtime,
3 = school time, which also embeds a UUID), field 2 is the day. The type is
encoded in bits that don't shift with the day, so the "CAEQ"/"CAMQ" prefix is a
stable proxy for it (see client/api.py for the decode used on the write path,
where picking the wrong rule's id would corrupt the schedule).
"""
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

# Weekly slot ids per ISO weekday. These are a FALLBACK only: the ids are
# account-specific, so the write path resolves them from the live schedule and
# uses these when that lookup fails (issue #135).
DAY_CODES = {
	1: "CAEQAQ",
	2: "CAEQAg",
	3: "CAEQAw",
	4: "CAEQBA",
	5: "CAEQBQ",
	6: "CAEQBg",
	7: "CAEQBw",
}

BEDTIME_CODE_PREFIX = "CAEQ"
SCHOOL_TIME_CODE_PREFIX = "CAMQ"

# stateFlag on a schedule row: 2 = enabled, 1 = disabled.
STATE_FLAG_ENABLED = 2


def _is_int(value: Any) -> bool:
	"""Return true for plain integers, excluding booleans.

	`isinstance(True, int)` is True in Python, which would let a stray bool
	pass as day 1.
	"""
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


def day_code_for(day: int) -> str:
	"""Return the fallback Family Link day code for an ISO weekday."""
	if not _is_int(day) or day not in DAY_CODES:
		raise ValueError(f"Invalid day: {day}. Must be 1-7 (Monday-Sunday)")
	return DAY_CODES[day]


def get_time_zone(value: str | None) -> ZoneInfo | None:
	"""Return a ZoneInfo for an IANA timezone name, or None if unusable."""
	if not isinstance(value, str):
		return None

	name = value.strip()
	if not name:
		return None

	try:
		return ZoneInfo(name)
	except ZoneInfoNotFoundError:
		return None


WINDOW_BEDTIME = "bedtime"
WINDOW_SCHOOL_TIME = "schooltime"


def classify_window_row(
	row: Any,
	bedtime_rule_id: str | None = None,
	schooltime_rule_id: str | None = None,
) -> str | None:
	"""Tell which rule a timeLimit / appliedTimeLimits window row belongs to.

	Returns WINDOW_BEDTIME, WINDOW_SCHOOL_TIME or None.

	The policy id at index 7 is the authoritative evidence: it is the id of the
	rule the slot is attached to, and it matches the revision ids. The key
	prefix comes second because it only encodes the slot *format*: accounts on
	Google's newer downtime model store bedtime slots with a `CAMQ...` key (the
	school time shape, with an embedded slot UUID) while still attaching them to
	the bedtime policy (issue #151). On those accounts a prefix-only reader
	counts every bedtime slot as school time.
	"""
	if not (isinstance(row, list) and len(row) >= 5 and isinstance(row[0], str)):
		return None

	policy_id = row[7] if len(row) > 7 and isinstance(row[7], str) else None
	if policy_id:
		if bedtime_rule_id and policy_id == bedtime_rule_id:
			return WINDOW_BEDTIME
		if schooltime_rule_id and policy_id == schooltime_rule_id:
			return WINDOW_SCHOOL_TIME

	if row[0].startswith(BEDTIME_CODE_PREFIX):
		return WINDOW_BEDTIME
	if row[0].startswith(SCHOOL_TIME_CODE_PREFIX):
		return WINDOW_SCHOOL_TIME
	return None


def parse_window_schedule_items(
	items: Any,
	window_type: str,
	bedtime_rule_id: str | None = None,
	schooltime_rule_id: str | None = None,
) -> list[dict[str, Any]]:
	"""Parse bedtime or school time rows from a timeLimit schedule list.

	Both kinds share one list; `window_type` (WINDOW_BEDTIME or
	WINDOW_SCHOOL_TIME) selects which, using classify_window_row: policy id
	first, key prefix second. Rows that don't match the expected shape are
	skipped rather than raising, because a Google-side change should degrade
	one slot rather than the whole fetch.
	"""
	schedules: list[dict[str, Any]] = []

	if not isinstance(items, list):
		return schedules

	for item in items:
		if not (isinstance(item, list) and len(item) >= 5):
			continue

		code = item[0]
		day = item[1]
		state_flag = item[2]
		start = item[3]
		end = item[4]

		if not (
			isinstance(code, str)
			and classify_window_row(item, bedtime_rule_id, schooltime_rule_id) == window_type
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
			"enabled": state_flag == STATE_FLAG_ENABLED,
			"start": start,
			"end": end,
			"state_flag": state_flag,
		})

	return sorted(schedules, key=lambda slot: slot["day"])


def _walk_lists(value: Any):
	"""Yield every nested list in a response fragment."""
	if not isinstance(value, list):
		return

	yield value
	for item in value:
		if isinstance(item, list):
			yield from _walk_lists(item)


def parse_daily_limit_schedule(config: Any) -> list[dict[str, Any]]:
	"""Parse daily limit rows from the timeLimit daily limit config block.

	These rows reuse the bedtime slot ids but carry minutes where a window row
	has an [h, m] pair, so requiring an int here is what keeps the two apart.
	Later rows win for a given day.
	"""
	schedules_by_day: dict[int, dict[str, Any]] = {}

	for item in _walk_lists(config):
		if len(item) < 4:
			continue

		code = item[0]
		day = item[1]
		state_flag = item[2]
		minutes = item[3]

		if not (
			isinstance(code, str)
			and code.startswith(BEDTIME_CODE_PREFIX)
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
			# A 0-minute limit is reported as disabled: Google keeps the row
			# with stateFlag=2 but no allowance.
			"enabled": state_flag == STATE_FLAG_ENABLED and minutes > 0,
			"minutes": minutes,
			"state_flag": state_flag,
		}

	return [schedules_by_day[day] for day in sorted(schedules_by_day)]

CODE_DAYS = {code: day for day, code in DAY_CODES.items()}


def parse_daily_limit_overrides(data: Any) -> dict[int, dict[str, tuple[int, int]]]:
	"""Per-weekday daily-limit overrides of the timeLimit response.

	Google stores the quota set for a weekday from the app as a type-8
	override row, ``[uuid, createdMs, 8, device_token, ..., [2, minutes,
	"CAEQxx"]]``, kept next to the recurring weekly rows (issue #157 capture).
	Returns ``{day: {device_id: (minutes, created_ms)}}`` with the most recent
	row per day and device.
	"""
	result: dict[int, dict[str, tuple[int, int]]] = {}
	for item in _walk_lists(data):
		if len(item) < 5 or item[2] != 8 or not isinstance(item[3], str) or not item[3]:
			continue
		device_id = item[3]
		# The [2, minutes, "CAEQxx"] payload sits at [11] in the request and
		# after the extra columns of a stored row: take the last such list.
		payload = next(
			(p for p in reversed(item[4:]) if isinstance(p, list) and len(p) >= 3 and _is_int(p[1]) and isinstance(p[2], str) and p[2] in CODE_DAYS),
			None,
		)
		if payload is None:
			continue
		minutes, code = payload[1], payload[2]
		try:
			created = int(item[1])
		except (TypeError, ValueError):
			created = 0
		day = CODE_DAYS[code]
		previous = result.setdefault(day, {}).get(device_id)
		if previous is None or created >= previous[1]:
			result[day][device_id] = (int(minutes), created)
	return result


def latest_daily_limit_override(
	overrides: dict[int, dict[str, tuple[int, int]]],
) -> tuple[int, int, int] | None:
	"""The most recent type-8 override across days and devices: (day, minutes, created_ms)."""
	latest: tuple[int, int, int] | None = None
	for day, per_device in overrides.items():
		for _device_id, (minutes, created) in per_device.items():
			if latest is None or created >= latest[2]:
				latest = (day, minutes, created)
	return latest


def daily_limit_week(
	weekly: list[dict[str, Any]],
	overrides: dict[int, dict[str, tuple[int, int]]],
	today: int | None = None,
) -> list[dict[str, Any]]:
	"""The seven weekday quotas as the Family Link app shows them.

	The app's "weekly limits" screen reads and writes the weekly rows of
	``data[1]``; they are the value of each weekday. A type-8 override only
	changes the quota Google applies today, and only while it is the most
	recent override posted (a later override for another day supersedes it and
	is itself ignored, live capture 2026-09-03). So the effective minutes are
	the weekly value, except for ``today`` when the latest override carries
	today's code.
	"""
	by_day = {row["day"]: row for row in weekly if isinstance(row, dict) and _is_int(row.get("day"))}
	latest = latest_daily_limit_override(overrides)
	week: list[dict[str, Any]] = []
	for day in range(1, 8):
		row = by_day.get(day) or {}
		weekly_minutes = row.get("minutes")
		override = None
		for _device_id, (minutes, created) in (overrides.get(day) or {}).items():
			if override is None or created >= override[1]:
				override = (minutes, created)
		override_minutes = override[0] if override else None
		applied_override = (
			today is not None and day == today and latest is not None and latest[0] == day
		)
		effective = override_minutes if applied_override and override_minutes is not None else weekly_minutes
		week.append({
			"day": day,
			"day_name": DAY_NAMES[day],
			"weekly_minutes": weekly_minutes,
			"override_minutes": override_minutes,
			"applied_override": bool(applied_override and override_minutes is not None),
			"effective_minutes": effective,
			"source": "override" if applied_override and override_minutes is not None else ("weekly" if weekly_minutes is not None else None),
			"enabled": row.get("enabled"),
		})
	return week
