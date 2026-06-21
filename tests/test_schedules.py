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
