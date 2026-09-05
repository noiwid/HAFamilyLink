"""Tests for removing API keys from config-entry URLs."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import familylink
from custom_components.familylink.const import (
    AUTH_SOURCE_MANAGED,
    AUTH_SOURCE_MANUAL,
    CONF_API_KEY,
    CONF_AUTH_SOURCE,
    CONF_AUTH_URL,
    DOMAIN,
)

FAKE_API_KEY = "test-api-key-not-a-real-secret"
FAKE_AUTH_URL = "http://auth.invalid:8099"


async def test_legacy_query_key_migrates_to_separate_field(hass) -> None:
    """A v1 URL key becomes separate data and a secret-free unique ID."""
    legacy_url = f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: legacy_url, "update_interval": 60},
        options={"timeout": 30},
        unique_id=legacy_url,
        version=1,
    )
    entry.add_to_hass(hass)

    assert await familylink.async_migrate_entry(hass, entry)

    assert entry.version == 2
    assert entry.data == {
        CONF_AUTH_URL: FAKE_AUTH_URL,
        CONF_API_KEY: FAKE_API_KEY,
        CONF_AUTH_SOURCE: AUTH_SOURCE_MANUAL,
        "update_interval": 60,
    }
    assert entry.options == {"timeout": 30}
    assert entry.unique_id == FAKE_AUTH_URL


async def test_default_entry_migrates_without_connection_fields(hass) -> None:
    """Auto-detected/file entries remain valid and get a stable identity."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"update_interval": 60},
        unique_id=None,
        version=1,
    )
    entry.add_to_hass(hass)

    assert await familylink.async_migrate_entry(hass, entry)

    assert entry.version == 2
    assert entry.data == {
        "update_interval": 60,
        CONF_AUTH_SOURCE: AUTH_SOURCE_MANAGED,
    }
    assert entry.unique_id == "familylink_default"


async def test_matching_separate_key_is_preserved(hass) -> None:
    """A partially migrated matching key is retained."""
    legacy_url = f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: legacy_url, CONF_API_KEY: FAKE_API_KEY},
        unique_id=legacy_url,
        version=1,
    )
    entry.add_to_hass(hass)

    assert await familylink.async_migrate_entry(hass, entry)
    assert entry.data[CONF_API_KEY] == FAKE_API_KEY
    assert entry.data[CONF_AUTH_SOURCE] == AUTH_SOURCE_MANUAL


async def test_keyless_manual_url_gets_explicit_manual_source(hass) -> None:
    """A keyless v1 URL remains manual without relying on detection heuristics."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, "update_interval": 60},
        unique_id=FAKE_AUTH_URL,
        version=1,
    )
    entry.add_to_hass(hass)

    assert await familylink.async_migrate_entry(hass, entry)

    assert entry.version == 2
    assert entry.data == {
        CONF_AUTH_URL: FAKE_AUTH_URL,
        CONF_AUTH_SOURCE: AUTH_SOURCE_MANUAL,
        "update_interval": 60,
    }
    assert CONF_API_KEY not in entry.data
    assert entry.unique_id == FAKE_AUTH_URL


@pytest.mark.parametrize(
    "legacy_url",
    [
        f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}&api_key=other-fake-key",
        f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}&route=legacy",
        f"ftp://auth.invalid:8099?api_key={FAKE_API_KEY}",
        f"http://user:password@auth.invalid:8099?api_key={FAKE_API_KEY}",
        f"{FAKE_AUTH_URL}?api_key=",
    ],
)
async def test_unsafe_legacy_url_fails_without_mutation_or_secret_log(
    hass,
    caplog,
    legacy_url: str,
) -> None:
    """Ambiguous or unsafe legacy URLs fail closed and do not leak keys."""
    original_data = {CONF_AUTH_URL: legacy_url, "update_interval": 60}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=original_data,
        unique_id=legacy_url,
        version=1,
    )
    entry.add_to_hass(hass)

    with caplog.at_level(logging.DEBUG):
        assert not await familylink.async_migrate_entry(hass, entry)

    assert entry.version == 1
    assert entry.data == original_data
    assert entry.unique_id == legacy_url
    assert FAKE_API_KEY not in caplog.text


async def test_conflicting_separate_key_fails_closed(hass) -> None:
    """Migration cannot guess between two different credentials."""
    legacy_url = f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: legacy_url, CONF_API_KEY: "different-fake-key"},
        unique_id=legacy_url,
        version=1,
    )
    entry.add_to_hass(hass)

    assert not await familylink.async_migrate_entry(hass, entry)
    assert entry.version == 1


async def test_duplicate_normalized_endpoint_fails_closed(hass) -> None:
    """Two legacy keys for one endpoint are not silently merged."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: "other-fake-key"},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    existing.add_to_hass(hass)
    legacy_url = f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}"
    legacy = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: legacy_url},
        unique_id=legacy_url,
        version=1,
    )
    legacy.add_to_hass(hass)

    assert not await familylink.async_migrate_entry(hass, legacy)
    assert legacy.version == 1
    assert legacy.data[CONF_AUTH_URL] == legacy_url


async def test_duplicate_default_entries_fail_closed(hass) -> None:
    """Two legacy auto-detected entries cannot acquire one default identity."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={"update_interval": 60},
        unique_id=None,
        version=1,
    )
    existing.add_to_hass(hass)
    duplicate = MockConfigEntry(
        domain=DOMAIN,
        data={"update_interval": 120},
        unique_id=None,
        version=1,
    )
    duplicate.add_to_hass(hass)

    assert not await familylink.async_migrate_entry(hass, duplicate)
    assert duplicate.version == 1
    assert duplicate.unique_id is None


async def test_duplicate_canonical_manual_endpoint_fails_closed(hass) -> None:
    """Equivalent endpoint URLs cannot become duplicate unique IDs."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: f"{FAKE_AUTH_URL}/"},
        unique_id=f"{FAKE_AUTH_URL}/",
        version=1,
    )
    existing.add_to_hass(hass)
    legacy_url = f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}"
    duplicate = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: legacy_url},
        unique_id=legacy_url,
        version=1,
    )
    duplicate.add_to_hass(hass)

    assert not await familylink.async_migrate_entry(hass, duplicate)
    assert duplicate.version == 1
    assert duplicate.unique_id == legacy_url


async def test_empty_auth_url_fails_closed(hass) -> None:
    """An explicitly present but empty URL is not reclassified as managed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: ""},
        unique_id=None,
        version=1,
    )
    entry.add_to_hass(hass)

    assert not await familylink.async_migrate_entry(hass, entry)
    assert entry.version == 1
    assert entry.data[CONF_AUTH_URL] == ""


async def test_current_entry_migration_is_idempotent(hass) -> None:
    """A current entry is accepted without mutation."""
    data = {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data,
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)

    assert await familylink.async_migrate_entry(hass, entry)
    assert entry.data == data
    assert entry.version == 2


async def test_setup_lifecycle_runs_migration(hass, monkeypatch) -> None:
    """Home Assistant setup invokes migration before integration setup."""
    legacy_url = f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: legacy_url},
        unique_id=legacy_url,
        version=1,
    )
    entry.add_to_hass(hass)
    setup_entry = AsyncMock(return_value=True)
    monkeypatch.setattr(familylink, "async_setup_entry", setup_entry)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert entry.version == 2
    assert entry.data[CONF_AUTH_URL] == FAKE_AUTH_URL
    assert entry.data[CONF_API_KEY] == FAKE_API_KEY
    assert entry.data[CONF_AUTH_SOURCE] == AUTH_SOURCE_MANUAL
    assert entry.unique_id == FAKE_AUTH_URL
    setup_entry.assert_awaited_once_with(hass, entry)
