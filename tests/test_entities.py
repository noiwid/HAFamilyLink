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


async def test_schedule_sensors_expose_weekday_today_and_timezone_attributes(
	hass, mock_config_entry, harness_coordinator
):
	"""Schedule sensors expose readable weekday values and timezone metadata."""
	entities = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, sensor
	)

	bedtime = _entity_by_unique_id(
		entities, f"{DOMAIN}_{TEST_CHILD_ID}_bedtime_schedule"
	)
	daily_limit = _entity_by_unique_id(
		entities, f"{DOMAIN}_{TEST_CHILD_ID}_daily_limit_schedule"
	)

	assert bedtime.native_value == "enabled"
	assert bedtime.extra_state_attributes["enabled"] is True
	assert bedtime.extra_state_attributes["monday"] == "21:00-06:00"
	assert bedtime.extra_state_attributes["today"] == "21:00-06:00"
	assert bedtime.extra_state_attributes["schedule_today_key"] == "monday"
	assert bedtime.extra_state_attributes["schedule_timezone"] == "UTC"
	assert bedtime.extra_state_attributes["schedule_timezone_source"] == "config"
	assert daily_limit.extra_state_attributes["monday"] == "120 min"


async def test_device_switch_reflects_lock_limit_bedtime_and_bonus_priority(
	hass, mock_config_entry, harness_coordinator
):
	"""Device switch state and icon explain the active restriction."""
	switches = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, switch
	)
	device_switch = _entity_by_unique_id(
		switches, f"{DOMAIN}_{TEST_CHILD_ID}_{TEST_DEVICE_ID}"
	)
	child_data = harness_coordinator.data["children_data"][0]
	device = child_data["devices"][0]
	time_data = child_data["devices_time_data"][TEST_DEVICE_ID]

	device["locked"] = True
	assert device_switch.is_on is False
	assert device_switch.icon == "mdi:cellphone-lock"
	assert device_switch.extra_state_attributes["restriction_reason"] == "manually_locked"

	device["locked"] = False
	time_data["bonus_minutes"] = 0
	time_data["bedtime_active"] = True
	time_data["daily_limit_remaining"] = 30
	assert device_switch.is_on is False
	assert device_switch.icon == "mdi:cellphone-off"
	assert device_switch.extra_state_attributes["restriction_reason"] == "bedtime_active"

	time_data["bedtime_active"] = False
	time_data["daily_limit_remaining"] = 0
	assert device_switch.is_on is False
	assert device_switch.icon == "mdi:cellphone-remove"
	assert device_switch.extra_state_attributes["restriction_reason"] == "daily_limit_reached"

	time_data["bonus_minutes"] = 15
	assert device_switch.is_on is True
	assert device_switch.icon == "mdi:cellphone-clock"
	assert device_switch.extra_state_attributes["restriction_reason"] == "bonus_active"


async def test_time_limit_switches_prefer_pending_state_then_today_state(
	hass, mock_config_entry, harness_coordinator
):
	"""Child switches use pending UI state before today-effective API state."""
	pending_states = {}

	def get_pending_time_limit_state(child_id, limit_type):
		return pending_states.get((child_id, limit_type))

	def set_pending_time_limit_state(child_id, limit_type, enabled):
		if enabled is None:
			pending_states.pop((child_id, limit_type), None)
		else:
			pending_states[(child_id, limit_type)] = enabled

	harness_coordinator.get_pending_time_limit_state = get_pending_time_limit_state
	harness_coordinator.set_pending_time_limit_state = set_pending_time_limit_state
	child_data = harness_coordinator.data["children_data"][0]
	child_data["bedtime_enabled"] = True
	child_data["bedtime_enabled_today"] = False

	switches = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, switch
	)
	bedtime = _entity_by_unique_id(switches, f"{DOMAIN}_{TEST_CHILD_ID}_bedtime")

	assert bedtime.is_on is False
	set_pending_time_limit_state(TEST_CHILD_ID, "bedtime", True)
	assert bedtime.is_on is True


async def test_button_presses_dispatch_to_client_and_refresh(
	hass, mock_config_entry, harness_coordinator
):
	"""Time bonus and ring buttons call the expected client methods."""
	buttons = await _entities_for_platform(
		hass, mock_config_entry, harness_coordinator, button
	)
	bonus = _entity_by_unique_id(
		buttons, f"{DOMAIN}_{TEST_CHILD_ID}_{TEST_DEVICE_ID}_bonus_15min"
	)
	ring = _entity_by_unique_id(
		buttons, f"{DOMAIN}_{TEST_CHILD_ID}_{TEST_DEVICE_ID}_ring"
	)

	await bonus.async_press()
	await ring.async_press()

	harness_coordinator.client.async_add_time_bonus.assert_awaited_once_with(
		bonus_minutes=15,
		device_id=TEST_DEVICE_ID,
		account_id=TEST_CHILD_ID,
	)
	harness_coordinator.client.async_ring_device.assert_awaited_once_with(
		device_id=TEST_DEVICE_ID,
		child_id=TEST_CHILD_ID,
	)
	harness_coordinator.async_request_refresh.assert_awaited_once()
