"""Tests for Family Link service schemas and dispatch."""
from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.familylink import (
	SCHEMA_SET_BEDTIME_SCHEDULE,
	async_setup_services,
)
from custom_components.familylink.const import (
	DOMAIN,
	SERVICE_REFRESH_DEVICES,
	SERVICE_RING_DEVICE,
	SERVICE_SET_BEDTIME_SCHEDULE,
	SERVICE_SET_DAILY_LIMIT_SCHEDULE,
)
from custom_components.familylink.exceptions import ScheduleUpdatePartialError

from conftest import TEST_CHILD_ID, TEST_DEVICE_ID


@pytest.fixture
async def services_hass(hass, harness_coordinator):
	"""Register Family Link services for service tests."""
	await async_setup_services(hass, harness_coordinator)
	return hass


def test_bedtime_schedule_schema_rejects_invalid_times():
	"""Service schemas reject invalid schedule times."""
	with pytest.raises(vol.Invalid):
		SCHEMA_SET_BEDTIME_SCHEDULE(
			{"day": 1, "start_time": "25:00", "end_time": "06:30"}
		)


def test_schema_keeps_numeric_looking_child_id_as_string():
	"""Child IDs look numeric but must remain strings."""
	result = SCHEMA_SET_BEDTIME_SCHEDULE(
		{"day": 1, "enabled": True, "child_id": "001002003"}
	)

	assert result["child_id"] == "001002003"


async def test_schedule_service_dispatch_keeps_child_id_string(
	services_hass, harness_coordinator
):
	"""Service dispatch passes child_id through to the API client unchanged."""
	await services_hass.services.async_call(
		DOMAIN,
		SERVICE_SET_DAILY_LIMIT_SCHEDULE,
		{"day": 1, "enabled": True, "child_id": "001002003"},
		blocking=True,
	)

	harness_coordinator.client.async_set_daily_limit_schedule.assert_awaited_once_with(
		day=1,
		daily_minutes=None,
		enabled=True,
		account_id="001002003",
	)


async def test_entity_id_fallback_extracts_child_and_device_ids(
	services_hass, harness_coordinator
):
	"""Entity attributes are used as fallback service targets."""
	services_hass.states.async_set(
		"switch.pixel_tablet",
		"on",
		{"child_id": TEST_CHILD_ID, "device_id": TEST_DEVICE_ID},
	)

	await services_hass.services.async_call(
		DOMAIN,
		SERVICE_RING_DEVICE,
		{"entity_id": "switch.pixel_tablet"},
		blocking=True,
	)

	harness_coordinator.client.async_ring_device.assert_awaited_once_with(
		device_id=TEST_DEVICE_ID,
		child_id=TEST_CHILD_ID,
	)


async def test_partial_schedule_write_still_requests_refresh(
	services_hass, harness_coordinator
):
	"""Partial schedule failures still request a coordinator refresh."""
	harness_coordinator.client.async_set_bedtime_schedule.side_effect = (
		ScheduleUpdatePartialError(["window"], "enabled")
	)

	with pytest.raises(ScheduleUpdatePartialError):
		await services_hass.services.async_call(
			DOMAIN,
			SERVICE_SET_BEDTIME_SCHEDULE,
			{"day": 1, "start_time": "21:00", "end_time": "06:30", "enabled": False},
			blocking=True,
		)

	harness_coordinator.async_request_refresh.assert_awaited_once()


def test_removed_or_unsupported_services_are_not_registered(services_hass):
	"""Deprecated or unsupported services stay out of the service registry."""
	assert not services_hass.services.has_service(DOMAIN, SERVICE_REFRESH_DEVICES)
	assert not services_hass.services.has_service(DOMAIN, "set_school_time_schedule")
