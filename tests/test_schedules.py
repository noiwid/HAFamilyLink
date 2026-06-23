"""Tests for Family Link schedule parsing helpers."""
from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
	Path(__file__).parents[1]
	/ "custom_components"
	/ "familylink"
	/ "schedules.py"
)
spec = importlib.util.spec_from_file_location("familylink_schedules", MODULE_PATH)
schedules = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(schedules)


def test_parse_window_schedule_items_splits_enabled_and_disabled_rows():
	items = [
		["CAEQAQ", 1, 2, [21, 0], [6, 30], "1", "2", "bedtime-rule"],
		["CAMQAg", 2, 1, [8, 15], [13, 45], "1", "2", "school-rule"],
		["CAEQAw", 3, 1, [22, 0], [7, 0], "1", "2", "bedtime-rule"],
		["CAEQBA", 4, 2, 21, [7, 0], "bad"],
		["other", 5, 2, [21, 0], [6, 30]],
	]

	bedtime = schedules.parse_window_schedule_items(items, "CAEQ")
	school_time = schedules.parse_window_schedule_items(items, "CAMQ")

	assert bedtime == [
		{
			"day": 1,
			"day_name": "Monday",
			"enabled": True,
			"start": [21, 0],
			"end": [6, 30],
			"state_flag": 2,
		},
		{
			"day": 3,
			"day_name": "Wednesday",
			"enabled": False,
			"start": [22, 0],
			"end": [7, 0],
			"state_flag": 1,
		},
	]
	assert school_time == [
		{
			"day": 2,
			"day_name": "Tuesday",
			"enabled": False,
			"start": [8, 15],
			"end": [13, 45],
			"state_flag": 1,
		}
	]


def test_parse_daily_limit_schedule_ignores_malformed_rows():
	config = [[
		2,
		[6, 0],
		[
			["CAEQAQ", 1, 2, 90, "1", "2"],
			["CAEQAg", 2, 1, 45, "1", "2"],
			["CAEQAw", 3, 2, 0, "1", "2"],
			["CAEQBA", 4, 2, [21, 0], "bad"],
		],
		"created",
		"updated",
	]]

	assert schedules.parse_daily_limit_schedule(config) == [
		{
			"day": 1,
			"day_name": "Monday",
			"enabled": True,
			"minutes": 90,
			"state_flag": 2,
		},
		{
			"day": 2,
			"day_name": "Tuesday",
			"enabled": False,
			"minutes": 45,
			"state_flag": 1,
		},
		{
			"day": 3,
			"day_name": "Wednesday",
			"enabled": False,
			"minutes": 0,
			"state_flag": 2,
		},
	]


def test_get_time_zone_accepts_only_valid_iana_names():
	assert schedules.get_time_zone("Asia/Jerusalem") is not None
	assert schedules.get_time_zone("  Asia/Jerusalem  ") is not None
	assert schedules.get_time_zone("") is None
	assert schedules.get_time_zone("UTC+03:00") is None


def test_find_device_time_zone_name_uses_devices_payload_position():
	device_without_timezone = [None] * 12
	device_with_timezone = [None] * 11 + [["Asia/Jerusalem"]]
	source = [None, [device_without_timezone, device_with_timezone]]

	assert schedules.find_device_time_zone_name(source) == "Asia/Jerusalem"


def test_find_device_time_zone_name_ignores_unrelated_nested_keys():
	source = {"deviceInfo": [{"timeZone": "Asia/Jerusalem"}]}

	assert schedules.find_device_time_zone_name(source) is None


def test_describe_effective_window_marks_weekly_match():
	weekly_schedule = [{
		"day": 7,
		"day_name": "Sunday",
		"enabled": True,
		"start": [21, 0],
		"end": [6, 30],
		"state_flag": 2,
	}]

	assert schedules.describe_effective_window("21:00", "06:30", weekly_schedule, 7) == {
		"start": "21:00",
		"end": "06:30",
		"label": "21:00-06:30",
		"source": "weekly",
		"weekly_start": "21:00",
		"weekly_end": "06:30",
		"weekly_label": "21:00-06:30",
		"differs_from_weekly": False,
	}


def test_describe_effective_window_marks_today_override():
	weekly_schedule = [{
		"day": 7,
		"day_name": "Sunday",
		"enabled": True,
		"start": [18, 30],
		"end": [6, 30],
		"state_flag": 2,
	}]

	assert schedules.describe_effective_window("21:00", "06:30", weekly_schedule, 7) == {
		"start": "21:00",
		"end": "06:30",
		"label": "21:00-06:30",
		"source": "today_override",
		"weekly_start": "18:30",
		"weekly_end": "06:30",
		"weekly_label": "18:30-06:30",
		"differs_from_weekly": True,
	}


def test_describe_effective_window_handles_missing_weekly_slot():
	weekly_schedule = [{
		"day": 6,
		"day_name": "Saturday",
		"enabled": True,
		"start": [21, 0],
		"end": [6, 30],
		"state_flag": 2,
	}]

	assert schedules.describe_effective_window("21:00", "06:30", weekly_schedule, 7) == {
		"start": "21:00",
		"end": "06:30",
		"label": "21:00-06:30",
		"source": "today_override",
		"weekly_start": None,
		"weekly_end": None,
		"weekly_label": None,
		"differs_from_weekly": False,
	}


def test_build_bedtime_schedule_update_payload():
	assert schedules.build_bedtime_schedule_update_payload(
		"child123", 7, "21:15", "06:30"
	) == [
		None,
		"child123",
		[[None, None, None, [["CAEQBw", [21, 15], [6, 30]]]], None, None, None, []],
		None,
		[1],
	]


def test_build_bedtime_day_enabled_update_payload():
	assert schedules.build_bedtime_day_enabled_update_payload(
		"child123", 2, False
	) == [
		None,
		"child123",
		[[None, None, [["CAEQAg", 1]], None], None, None, None, []],
		None,
		[1],
	]


def test_build_daily_limit_schedule_update_payload():
	assert schedules.build_daily_limit_schedule_update_payload(
		"child123", 5, 135
	) == [
		None,
		"child123",
		[None, [[2, None, None, [["CAEQBQ", 135]]]]],
		None,
		[1],
	]


def test_build_daily_limit_day_enabled_update_payload():
	assert schedules.build_daily_limit_day_enabled_update_payload(
		"child123", 3, False
	) == [
		None,
		"child123",
		[None, [[2, None, [["CAEQAw", 1]], None]]],
		None,
		[1],
	]


def test_builders_reject_invalid_values():
	for invalid_day in (0, 8, True):
		try:
			schedules.day_code_for(invalid_day)
		except ValueError:
			pass
		else:
			raise AssertionError(f"day {invalid_day!r} should be rejected")

	for invalid_time in ("24:00", "10:60", "bad"):
		try:
			schedules.parse_time_string(invalid_time)
		except ValueError:
			pass
		else:
			raise AssertionError(f"time {invalid_time!r} should be rejected")

	for invalid_minutes in (-1, 1441, True):
		try:
			schedules.build_daily_limit_schedule_update_payload("child123", 1, invalid_minutes)
		except ValueError:
			pass
		else:
			raise AssertionError(f"minutes {invalid_minutes!r} should be rejected")

	for invalid_enabled in (0, 1, "true"):
		try:
			schedules.build_daily_limit_day_enabled_update_payload(
				"child123", 1, invalid_enabled
			)
		except ValueError:
			pass
		else:
			raise AssertionError(f"enabled {invalid_enabled!r} should be rejected")
