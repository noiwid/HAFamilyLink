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

from datetime import datetime, timedelta
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

def find_daily_limit_slot_id(data: Any, day: int) -> str | None:
	"""Return the live daily-limit slot id for an ISO weekday (issue #157).

	The daily-limit rows of the timeLimit response reuse a weekly slot id,
	and that id is not the static ``CAEQxx`` value on every account: posting
	an unknown id to ``timeLimitOverrides:batchCreate`` returns HTTP 200 but
	the override stays inert. A daily-limit row is recognised by its shape,
	``[slot_id, day, state_flag, minutes, ...]``: window rows carry an
	``[hour, minute]`` pair at index 3 and revision rows a timestamp list, so
	requiring plain integer minutes keeps this lookup specific.

	The daily-limit block is ``data[1]`` when the response has the documented
	layout; it is searched first, the whole response only as a fallback.
	As in ``parse_daily_limit_schedule``, a later row wins for the same day.
	"""
	if not _is_int(day) or day not in DAY_NAMES:
		return None

	def _search(fragment: Any) -> str | None:
		found: str | None = None
		for item in _walk_lists(fragment):
			if len(item) < 4:
				continue
			code, row_day, state_flag, minutes = item[0], item[1], item[2], item[3]
			if (
				isinstance(code, str)
				and code
				and _is_int(row_day)
				and row_day == day
				and _is_int(state_flag)
				and state_flag in (1, 2)
				and _is_int(minutes)
				and minutes >= 0
			):
				found = code
		return found

	if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
		found = _search(data[1])
		if found:
			return found
	return _search(data)

def describe_time_until(target: datetime, now: datetime) -> str:
	"""Human-readable delay until `target`: "Active now", "in 25min", "in 3h05", "in 1d 14h"."""
	diff_seconds = int((target - now).total_seconds())
	if diff_seconds <= 0:
		return "Active now"
	days, rem = divmod(diff_seconds, 86400)
	hours, rem = divmod(rem, 3600)
	minutes = rem // 60
	if days > 0:
		return f"in {days}d {hours}h"
	if hours > 0:
		return f"in {hours}h{minutes:02d}"
	return f"in {minutes}min"


def next_scheduled_window(
	now: datetime,
	bedtime_schedule: list[dict[str, Any]] | None,
	school_time_schedule: list[dict[str, Any]] | None,
	bedtime_enabled: bool | None = None,
	school_time_enabled: bool | None = None,
	days_ahead: int = 7,
) -> tuple[str, datetime, datetime] | None:
	"""Earliest window of the weekly schedules starting after today.

	Today's windows are covered by the per-device data of appliedTimeLimits
	(which already merges the daily overrides); this helper only looks from
	tomorrow on, so the next-restriction sensor can announce tomorrow's
	bedtime once today's windows are over instead of "No restrictions".

	A schedule is skipped when its weekly policy is off (`False`); `None`
	means unknown and is treated as on. Rows are the dicts produced by
	parse_window_schedule_items (day, enabled, start [h, m], end [h, m]).
	Returns (WINDOW_BEDTIME | WINDOW_SCHOOL_TIME, start, end) or None.
	"""
	candidates: list[tuple[datetime, datetime, str]] = []
	sources = (
		(WINDOW_BEDTIME, bedtime_schedule, bedtime_enabled),
		(WINDOW_SCHOOL_TIME, school_time_schedule, school_time_enabled),
	)
	for offset in range(1, days_ahead + 1):
		day_dt = now + timedelta(days=offset)
		weekday = day_dt.isoweekday()
		for window_type, schedule, policy_enabled in sources:
			if policy_enabled is False or not isinstance(schedule, list):
				continue
			for slot in schedule:
				if not isinstance(slot, dict) or slot.get("day") != weekday or not slot.get("enabled"):
					continue
				start, end = slot.get("start"), slot.get("end")
				if not (_is_time_pair(start) and _is_time_pair(end)):
					continue
				start_dt = day_dt.replace(hour=start[0], minute=start[1], second=0, microsecond=0)
				end_dt = day_dt.replace(hour=end[0], minute=end[1], second=0, microsecond=0)
				if end_dt <= start_dt:
					end_dt += timedelta(days=1)
				candidates.append((start_dt, end_dt, window_type))
		if candidates:
			break

	if not candidates:
		return None
	start_dt, end_dt, window_type = min(candidates, key=lambda c: c[0])
	return window_type, start_dt, end_dt
