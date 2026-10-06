"""Reconfigure keeps an add-on (managed) entry managed when no key is typed (issue #186).

"Clear API key" on a Supervisor install used to force the manual source and
validate with no key at all: a 403, "invalid_api_key", and no way out but
pasting the key by hand. The managed path reads the key the add-on shares.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.familylink.auth.addon_client import AddonCookieClient
from custom_components.familylink.const import (
    AUTH_SOURCE_MANAGED,
    AUTH_SOURCE_MANUAL,
    CONF_API_KEY,
    CONF_AUTH_SOURCE,
    CONF_AUTH_URL,
    CONF_CLEAR_API_KEY,
    DOMAIN,
)

ADDON_URL = "http://addon.invalid:8099"
COOKIES = [{"name": "TEST_SESSION", "value": "fake-value"}]


@pytest.fixture
def managed_only(monkeypatch):
    """The manual endpoint refuses every call (403); the managed path has the shared key."""

    async def _manual_fetch(self, url, api_key=None):
        self.last_fetch_status = 403
        return None

    async def _managed(self):
        return COOKIES

    monkeypatch.setattr(AddonCookieClient, "_fetch_cookies_from_url", _manual_fetch)
    monkeypatch.setattr(AddonCookieClient, "_load_managed_cookies", _managed)


async def _reconfigure(hass, entry, user_input):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)


def _managed_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_AUTH_URL: ADDON_URL,
            CONF_AUTH_SOURCE: AUTH_SOURCE_MANAGED,
            CONF_API_KEY: "stale-key-from-before-the-add-on-upgrade",
        },
        unique_id=ADDON_URL,
        version=2,
    )
    entry.add_to_hass(hass)
    return entry


async def test_clearing_the_key_on_a_managed_entry_validates_through_the_add_on(
    hass, managed_only, monkeypatch
) -> None:
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    entry = _managed_entry(hass)

    result = await _reconfigure(hass, entry, {CONF_AUTH_URL: ADDON_URL, CONF_CLEAR_API_KEY: True})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_AUTH_SOURCE] == AUTH_SOURCE_MANAGED
    assert CONF_API_KEY not in entry.data


async def test_a_typed_key_still_makes_the_endpoint_manual(hass, managed_only, monkeypatch) -> None:
    """An explicit key is the user taking the endpoint over; the manual path then applies."""
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))

    async def _manual_ok(self, url, api_key=None):
        return COOKIES if api_key == "typed-key" else None

    monkeypatch.setattr(AddonCookieClient, "_fetch_cookies_from_url", _manual_ok)
    entry = _managed_entry(hass)

    result = await _reconfigure(hass, entry, {CONF_AUTH_URL: ADDON_URL, CONF_API_KEY: "typed-key"})

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_AUTH_SOURCE] == AUTH_SOURCE_MANUAL
    assert entry.data[CONF_API_KEY] == "typed-key"
