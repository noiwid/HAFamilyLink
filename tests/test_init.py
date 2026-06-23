"""Tests for integration setup and unload."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.familylink import async_setup_entry, async_setup_services, async_unload_entry
from custom_components.familylink.const import (
	DOMAIN,
	SERVICE_BLOCK_APP,
	SERVICE_RING_DEVICE,
	SERVICE_SET_BEDTIME_SCHEDULE,
)
from custom_components.familylink.exceptions import FamilyLinkException


async def test_async_setup_entry_registers_services_and_forwards_platforms(
	hass, mock_config_entry, harness_coordinator, monkeypatch
):
	"""Set up a config entry, store the coordinator, and forward platforms."""
	mock_config_entry.add_to_hass(hass)
	forward_setups = AsyncMock(return_value=True)
	monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward_setups)
	monkeypatch.setattr(
		"custom_components.familylink.FamilyLinkDataUpdateCoordinator",
		lambda hass, entry: harness_coordinator,
	)

	assert await async_setup_entry(hass, mock_config_entry) is True

	harness_coordinator.async_config_entry_first_refresh.assert_awaited_once()
	assert hass.data[DOMAIN][mock_config_entry.entry_id] is harness_coordinator
	forward_setups.assert_awaited_once()
	assert hass.services.has_service(DOMAIN, SERVICE_BLOCK_APP)
	assert hass.services.has_service(DOMAIN, SERVICE_RING_DEVICE)


async def test_setup_entry_raises_not_ready_on_coordinator_failure(
	hass, mock_config_entry, harness_coordinator, monkeypatch
):
	"""Coordinator connection failures are surfaced as ConfigEntryNotReady."""
	harness_coordinator.async_config_entry_first_refresh.side_effect = FamilyLinkException("nope")
	monkeypatch.setattr(
		"custom_components.familylink.FamilyLinkDataUpdateCoordinator",
		lambda hass, entry: harness_coordinator,
	)

	with pytest.raises(ConfigEntryNotReady):
		await async_setup_entry(hass, mock_config_entry)


async def test_unload_removes_services_only_after_last_entry(
	hass, harness_coordinator, monkeypatch
):
	"""Global services stay registered until the last config entry unloads."""
	entry_one = MockConfigEntry(domain=DOMAIN, entry_id="entry-one")
	entry_two = MockConfigEntry(domain=DOMAIN, entry_id="entry-two")
	coordinator_two = harness_coordinator
	coordinator_one = AsyncMock()
	coordinator_one.async_cleanup = AsyncMock()
	hass.data[DOMAIN] = {
		entry_one.entry_id: coordinator_one,
		entry_two.entry_id: coordinator_two,
	}
	await async_setup_services(hass, harness_coordinator)
	monkeypatch.setattr(
		hass.config_entries,
		"async_unload_platforms",
		AsyncMock(return_value=True),
	)

	assert await async_unload_entry(hass, entry_one) is True
	assert hass.services.has_service(DOMAIN, SERVICE_SET_BEDTIME_SCHEDULE)
	assert hass.services.has_service(DOMAIN, SERVICE_RING_DEVICE)

	assert await async_unload_entry(hass, entry_two) is True
	assert not hass.services.has_service(DOMAIN, SERVICE_SET_BEDTIME_SCHEDULE)
	assert not hass.services.has_service(DOMAIN, SERVICE_RING_DEVICE)
	coordinator_one.async_cleanup.assert_awaited_once()
	coordinator_two.async_cleanup.assert_awaited_once()
