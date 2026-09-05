"""Diagnostics must never reveal authentication credentials."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.familylink.const import CONF_API_KEY, CONF_AUTH_URL, DOMAIN
from custom_components.familylink.diagnostics import async_get_config_entry_diagnostics

FAKE_API_KEY = "test-api-key-not-a-real-secret"
FAKE_AUTH_URL = "http://auth.invalid:8099"


async def test_api_key_is_redacted_from_diagnostics(hass) -> None:
    """Config-entry diagnostics expose only redacted credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        options={"timeout": 30, CONF_API_KEY: "stale-fake-option-key"},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"][CONF_AUTH_URL] == FAKE_AUTH_URL
    assert diagnostics["entry_data"][CONF_API_KEY] == "**REDACTED**"
    assert diagnostics["entry_options"] == {
        "timeout": 30,
        CONF_API_KEY: "**REDACTED**",
    }
    assert FAKE_API_KEY not in str(diagnostics)


async def test_failed_legacy_migration_cannot_leak_query_key(hass) -> None:
    """Diagnostics sanitize a version-1 URL even when migration was rejected."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}&route=old"},
        unique_id=f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}&route=old",
        version=1,
    )
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert FAKE_API_KEY not in str(diagnostics)
    assert diagnostics["entry_data"][CONF_AUTH_URL] == "**REDACTED**"
