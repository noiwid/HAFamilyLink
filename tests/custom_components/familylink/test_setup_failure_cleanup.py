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
