"""Tests for entity platform creation from coordinator data."""
from __future__ import annotations

from custom_components.familylink import binary_sensor, button, device_tracker, sensor, switch
from custom_components.familylink.const import DOMAIN

from conftest import TEST_CHILD_ID, TEST_DEVICE_ID


async def _entities_for_platform(hass, mock_config_entry, harness_coordinator, platform):
	if hass.config_entries.async_get_entry(mock_config_entry.entry_id) is None:
		mock_config_entry.add_to_hass(hass)
	hass.data.setdefault(DOMAIN, {})[mock_config_entry.entry_id] = harness_coordinator
	entities = []

	def async_add_entities(new_entities, update_before_add=False):
		entities.extend(new_entities)

	await platform.async_setup_entry(hass, mock_config_entry, async_add_entities)
	return entities


def _entity_by_unique_id(entities, unique_id):
	return next(entity for entity in entities if entity.unique_id == unique_id)


async def test_sensor_entities_include_unique_ids_device_info_and_attributes(
	hass, mock_config_entry, harness_coordinator
):
	"""Sensor setup creates child, schedule, app, and device sensors."""
	entities = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, sensor
	)

	assert len(entities) == 27
	app_count = _entity_by_unique_id(entities, f"{DOMAIN}_{TEST_CHILD_ID}_app_count")
	assert app_count.native_value == 3
	assert app_count.extra_state_attributes["blocked_apps"] == 1
	assert (DOMAIN, TEST_CHILD_ID) in app_count.device_info["identifiers"]

	screen_time = _entity_by_unique_id(
		entities, f"{DOMAIN}_{TEST_CHILD_ID}_{TEST_DEVICE_ID}_screen_time_remaining"
	)
	assert screen_time.native_value == 60
	assert screen_time.extra_state_attributes["device_id"] == TEST_DEVICE_ID

	battery = _entity_by_unique_id(entities, f"{DOMAIN}_{TEST_CHILD_ID}_battery_level")
	assert battery.native_value == 84


async def test_switch_binary_button_and_tracker_entities_are_created(
	hass, mock_config_entry, harness_coordinator
):
	"""The non-sensor platforms create entities from the same coordinator payload."""
	switches = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, switch
	)
	binary_sensors = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, binary_sensor
	)
	buttons = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, button
	)
	trackers = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, device_tracker
	)

	assert len(switches) == 4
	device_switch = _entity_by_unique_id(
		switches, f"{DOMAIN}_{TEST_CHILD_ID}_{TEST_DEVICE_ID}"
	)
	assert device_switch.is_on is True
	assert device_switch.extra_state_attributes["child_id"] == TEST_CHILD_ID
	assert (DOMAIN, f"{TEST_CHILD_ID}_{TEST_DEVICE_ID}") in device_switch.device_info[
		"identifiers"
	]

	assert len(binary_sensors) == 3
	bedtime = _entity_by_unique_id(
		binary_sensors, f"{DOMAIN}_{TEST_CHILD_ID}_{TEST_DEVICE_ID}_bedtime_active"
	)
	assert bedtime.is_on is False
	assert bedtime.extra_state_attributes["device_id"] == TEST_DEVICE_ID

	assert len(buttons) == 5
	assert _entity_by_unique_id(
		buttons, f"{DOMAIN}_{TEST_CHILD_ID}_{TEST_DEVICE_ID}_bonus_15min"
	)

	assert len(trackers) == 1
	tracker = trackers[0]
	assert tracker.unique_id == f"{DOMAIN}_{TEST_CHILD_ID}_location"
	assert tracker.latitude == 32.0853
	assert tracker.extra_state_attributes["battery_level"] == 84
