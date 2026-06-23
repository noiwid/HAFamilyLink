"""Home Assistant test harness fixtures for the Family Link integration."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HassJob
from homeassistant.const import CONF_NAME
from pytest_homeassistant_custom_component import plugins as ha_test_plugins
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.familylink.const import (
	CONF_AUTH_URL,
	CONF_ENABLE_LOCATION_TRACKING,
	CONF_SCHEDULE_TIMEZONE,
	CONF_TIMEOUT,
	CONF_UPDATE_INTERVAL,
	DEFAULT_TIMEOUT,
	DEFAULT_UPDATE_INTERVAL,
	DOMAIN,
	INTEGRATION_NAME,
)


pytest_plugins = ("pytest_homeassistant_custom_component",)

TEST_ENTRY_ID = "familylink-test-entry"
TEST_CHILD_ID = "100200300"
TEST_DEVICE_ID = "device-1"
TEST_AUTH_URL = "http://familylink-auth.local:8099?api_key=test-api-key"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations, mock_network):
	"""Load custom integrations and keep network helpers mocked for every test."""
	yield


@pytest.fixture(autouse=True)
def verify_cleanup(event_loop, expected_lingering_tasks, expected_lingering_timers):
	"""Keep HA cleanup checks, allowing HA's safe-shutdown helper thread in CI."""
	threads_before = frozenset(threading.enumerate())
	tasks_before = asyncio.all_tasks(event_loop)
	yield

	event_loop.run_until_complete(event_loop.shutdown_default_executor())

	if len(ha_test_plugins.INSTANCES) >= 2:
		count = len(ha_test_plugins.INSTANCES)
		for inst in ha_test_plugins.INSTANCES:
			inst.stop()
		pytest.exit(f"Detected non stopped instances ({count}), aborting test run")

	tasks = asyncio.all_tasks(event_loop) - tasks_before
	for task in tasks:
		if expected_lingering_tasks:
			ha_test_plugins._LOGGER.warning("Lingering task after test %r", task)
		else:
			pytest.fail(f"Lingering task after test {task!r}")
		task.cancel()
	if tasks:
		event_loop.run_until_complete(asyncio.wait(tasks))

	for handle in event_loop._scheduled:
		if handle.cancelled():
			continue
		with ha_test_plugins.long_repr_strings():
			if expected_lingering_timers:
				ha_test_plugins._LOGGER.warning("Lingering timer after test %r", handle)
			elif handle._args and isinstance(job := handle._args[-1], HassJob):
				if job.cancel_on_shutdown:
					continue
				pytest.fail(f"Lingering timer after job {job!r}")
			else:
				pytest.fail(f"Lingering timer after test {handle!r}")
			handle.cancel()

	threads = frozenset(threading.enumerate()) - threads_before
	for thread in threads:
		assert (
			isinstance(thread, threading._DummyThread)
			or thread.name.startswith("waitpid-")
			or "_run_safe_shutdown_loop" in thread.name
		)


@pytest.fixture
def sample_config_data() -> dict[str, object]:
	"""Return config entry data that never points at real credentials."""
	return {
		CONF_NAME: INTEGRATION_NAME,
		CONF_AUTH_URL: TEST_AUTH_URL,
		CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
		CONF_TIMEOUT: DEFAULT_TIMEOUT,
		CONF_ENABLE_LOCATION_TRACKING: True,
		CONF_SCHEDULE_TIMEZONE: "UTC",
	}


@pytest.fixture
def mock_config_entry(sample_config_data) -> MockConfigEntry:
	"""Return a config entry for the custom integration."""
	return MockConfigEntry(
		domain=DOMAIN,
		title=INTEGRATION_NAME,
		data=sample_config_data,
		entry_id=TEST_ENTRY_ID,
		unique_id=TEST_AUTH_URL,
	)


@pytest.fixture
def sample_coordinator_data() -> dict[str, object]:
	"""Return one complete child/device payload shared by platform tests."""
	child = {
		"userId": TEST_CHILD_ID,
		"role": "MEMBER",
		"ageBandLabel": "Child",
		"profile": {
			"displayName": "Alex",
			"givenName": "Alex",
			"familyName": "Tester",
			"email": "alex@example.test",
			"birthday": {"year": 2016, "month": 6, "day": 23},
		},
	}
	return {
		"children_data": [
			{
				"child": child,
				"child_id": TEST_CHILD_ID,
				"child_name": "Alex",
				"apps": [
					{
						"title": "YouTube",
						"packageName": "com.google.android.youtube",
						"supervisionSetting": {"hidden": True},
					},
					{
						"title": "Spotify",
						"packageName": "com.spotify.music",
						"supervisionSetting": {
							"usageLimit": {"dailyUsageLimitMins": 45, "enabled": True}
						},
					},
					{
						"title": "Calculator",
						"packageName": "com.android.calculator2",
						"supervisionSetting": {"alwaysAllowedAppInfo": {"enabled": True}},
					},
				],
				"screen_time": {
					"total_seconds": 5400,
					"formatted": "01:30:00",
					"hours": 1,
					"minutes": 30,
					"seconds": 0,
					"app_breakdown": {
						"com.google.android.youtube": 3600,
						"com.spotify.music": 1800,
					},
				},
				"devices": [
					{
						"id": TEST_DEVICE_ID,
						"name": "Pixel Tablet",
						"model": "Pixel Tablet",
						"version": "14",
						"locked": False,
						"last_activity": 1710000000000,
					}
				],
				"devices_time_data": {
					TEST_DEVICE_ID: {
						"remaining_minutes": 60,
						"total_allowed_minutes": 120,
						"used_minutes": 60,
						"daily_limit_enabled": True,
						"daily_limit_minutes": 120,
						"daily_limit_remaining": 60,
						"bedtime_active": False,
						"schooltime_active": False,
						"bonus_minutes": 15,
						"bonus_override_id": "bonus-1",
						"bedtime_window": {
							"start_ms": 1710021600000,
							"end_ms": 1710050400000,
						},
						"schooltime_window": {
							"start_ms": 1710061200000,
							"end_ms": 1710075600000,
						},
						"bedtime_window_start": "21:00",
						"bedtime_window_end": "06:00",
						"bedtime_window_label": "21:00-06:00",
						"bedtime_window_source": "weekly",
					}
				},
				"bedtime_enabled": True,
				"school_time_enabled": False,
				"daily_limit_enabled": True,
				"bedtime_schedule": [
					{
						"day": 1,
						"day_name": "Monday",
						"enabled": True,
						"start": [21, 0],
						"end": [6, 0],
					}
				],
				"school_time_schedule": [
					{
						"day": 1,
						"day_name": "Monday",
						"enabled": False,
						"start": [8, 0],
						"end": [13, 30],
					}
				],
				"daily_limit_schedule": [
					{
						"day": 1,
						"day_name": "Monday",
						"enabled": True,
						"minutes": 120,
					}
				],
				"schedule_today": 1,
				"schedule_timezone": "UTC",
				"schedule_timezone_source": "config",
				"location": {
					"latitude": 32.0853,
					"longitude": 34.7818,
					"accuracy": 25,
					"battery_level": 84,
					"source_device_name": "Pixel Tablet",
					"timestamp_iso": "2026-06-23T12:00:00+00:00",
				},
			}
		]
	}


@pytest.fixture
def familylink_client() -> SimpleNamespace:
	"""Return a mocked Family Link API client with every service endpoint covered."""
	client = SimpleNamespace()
	for method_name in (
		"async_block_device_for_school",
		"async_unblock_all_apps",
		"async_block_app",
		"async_unblock_app",
		"async_set_app_daily_limit",
		"async_add_time_bonus",
		"async_enable_bedtime",
		"async_disable_bedtime",
		"async_enable_school_time",
		"async_disable_school_time",
		"async_enable_daily_limit",
		"async_disable_daily_limit",
		"async_set_daily_limit",
		"async_set_bedtime",
		"async_set_bedtime_schedule",
		"async_set_daily_limit_schedule",
		"async_ring_device",
		"async_cancel_time_bonus",
	):
		setattr(client, method_name, AsyncMock(return_value=True))
	client.async_get_all_supervised_children = AsyncMock(
		return_value=[{"id": TEST_CHILD_ID, "name": "Alex"}]
	)
	client.async_get_location = AsyncMock(
		return_value={"latitude": 32.0853, "longitude": 34.7818}
	)
	return client


@pytest.fixture
def harness_coordinator(sample_coordinator_data, familylink_client) -> SimpleNamespace:
	"""Return the minimum coordinator surface used by setup, services, and entities."""
	coordinator = SimpleNamespace(
		data=deepcopy(sample_coordinator_data),
		client=familylink_client,
		last_update_success=True,
		async_config_entry_first_refresh=AsyncMock(),
		async_request_refresh=AsyncMock(),
		async_cleanup=AsyncMock(),
	)
	coordinator.async_add_listener = lambda update_callback, context=None: lambda: None
	coordinator.async_update_listeners = lambda: None
	return coordinator
