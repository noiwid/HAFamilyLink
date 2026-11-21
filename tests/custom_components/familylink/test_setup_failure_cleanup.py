"""A setup that fails closes the client it opened.

Each ConfigEntryNotReady retry builds a new coordinator and client: the failed
one's aiohttp session was left open, one more at every retry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.familylink as integration
from custom_components.familylink.const import DOMAIN
from custom_components.familylink.exceptions import NetworkError


async def test_a_failed_first_refresh_closes_the_client(hass, monkeypatch) -> None:
    coordinator = MagicMock()
    coordinator.async_load_strict_intents = AsyncMock()
    coordinator.async_config_entry_first_refresh = AsyncMock(side_effect=NetworkError("503"))
    coordinator.async_cleanup = AsyncMock()
    monkeypatch.setattr(integration, "FamilyLinkDataUpdateCoordinator", MagicMock(return_value=coordinator))
    entry = MockConfigEntry(domain=DOMAIN)

    with pytest.raises(ConfigEntryNotReady):
        await integration.async_setup_entry(hass, entry)

    coordinator.async_cleanup.assert_awaited_once()


async def test_strict_mode_runs_once_the_switches_are_restored(hass, monkeypatch) -> None:
    """The first refresh skips strict mode (switches not restored yet): the pass runs after the platforms."""
    coordinator = MagicMock()
    coordinator.data = {"children_data": []}
    coordinator.async_load_strict_intents = AsyncMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator._async_enforce_strict_mode = AsyncMock()
    monkeypatch.setattr(integration, "FamilyLinkDataUpdateCoordinator", MagicMock(return_value=coordinator))
    for name in ("async_setup_services", "async_setup_app_pause_services", "async_setup_website_services", "async_register_card"):
        monkeypatch.setattr(integration, name, AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    assert await integration.async_setup_entry(hass, entry)
    await hass.async_block_till_done()

    coordinator._async_enforce_strict_mode.assert_awaited_once_with(coordinator.data)
