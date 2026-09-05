"""Tests for secret-safe manual configuration."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.selector import TextSelector, TextSelectorType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.familylink.auth.addon_client import (
    AddonCookieClient,
    AuthServerApiKeyError,
)
from custom_components.familylink.const import (
    AUTH_SOURCE_MANAGED,
    AUTH_SOURCE_MANUAL,
    CONF_API_KEY,
    CONF_AUTH_SOURCE,
    CONF_AUTH_URL,
    CONF_CLEAR_API_KEY,
    DOMAIN,
)

FAKE_API_KEY = "test-api-key-not-a-real-secret"
FAKE_AUTH_URL = "http://auth.invalid:8099"


@pytest.fixture
def mock_auth_client(monkeypatch):
    """Prevent all config-flow network and filesystem access."""

    async def _detect(_self):
        return ("none", None)

    async def _validate_manual(_self):
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    async def _load(_self):
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    monkeypatch.setattr(AddonCookieClient, "detect_auth_source", _detect)
    monkeypatch.setattr(
        AddonCookieClient,
        "async_validate_manual_endpoint",
        _validate_manual,
    )
    monkeypatch.setattr(AddonCookieClient, "load_cookies", _load)


async def test_managed_addon_setup_does_not_store_internal_url(
    hass,
    monkeypatch,
) -> None:
    """Supervisor discovery keeps the config entry on managed auto mode."""
    async def _detect(_self):
        return ("managed_addon", FAKE_AUTH_URL)

    async def _load(_self):
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    monkeypatch.setattr(AddonCookieClient, "detect_auth_source", _detect)
    monkeypatch.setattr(AddonCookieClient, "load_cookies", _load)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "auto_detect"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Managed Family Link",
            "update_interval": 60,
            "timeout": 30,
            "enable_location_tracking": False,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_SOURCE] == AUTH_SOURCE_MANAGED
    assert CONF_AUTH_URL not in result["data"]
    assert result["result"].unique_id == "familylink_default"


async def test_auto_detected_local_api_is_stored_as_manual(
    hass,
    monkeypatch,
) -> None:
    """A discovered localhost API remains an explicit manual endpoint."""
    async def _detect(_self):
        return ("api", FAKE_AUTH_URL)

    async def _load(_self):
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    monkeypatch.setattr(AddonCookieClient, "detect_auth_source", _detect)
    monkeypatch.setattr(AddonCookieClient, "load_cookies", _load)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "auto_detect"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Local API Family Link",
            "update_interval": 60,
            "timeout": 30,
            "enable_location_tracking": False,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_SOURCE] == AUTH_SOURCE_MANUAL
    assert result["data"][CONF_AUTH_URL] == FAKE_AUTH_URL
    assert result["result"].unique_id == FAKE_AUTH_URL


async def _open_manual_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "manual_url"},
    )


async def test_manual_form_uses_separate_password_key(hass, mock_auth_client) -> None:
    """The API key is a separate masked field, not URL text."""
    result = await _open_manual_form(hass)

    schema = result["data_schema"].schema
    fields = {marker.schema: validator for marker, validator in schema.items()}
    assert set(fields) == {CONF_AUTH_URL, CONF_API_KEY}
    assert isinstance(
        next(marker for marker in schema if marker.schema == CONF_API_KEY),
        vol.Optional,
    )
    assert isinstance(fields[CONF_API_KEY], TextSelector)
    assert fields[CONF_API_KEY].config["type"] == TextSelectorType.PASSWORD
    assert "autocomplete" not in fields[CONF_AUTH_URL].config
    assert "autocomplete" not in fields[CONF_API_KEY].config


@pytest.mark.parametrize("detected_source", ["managed_addon", "file"])
async def test_manual_choice_overrides_detected_source(
    hass,
    monkeypatch,
    detected_source: str,
) -> None:
    """Choosing Manual URL clears any previously detected managed state."""
    async def _detect(_self):
        return (
            (detected_source, FAKE_AUTH_URL)
            if detected_source == "managed_addon"
            else ("file", None)
        )

    async def _validate_manual(_self):
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    async def _load(_self):
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    monkeypatch.setattr(AddonCookieClient, "detect_auth_source", _detect)
    monkeypatch.setattr(
        AddonCookieClient,
        "async_validate_manual_endpoint",
        _validate_manual,
    )
    monkeypatch.setattr(AddonCookieClient, "load_cookies", _load)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "manual_url"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Manual Family Link",
            "update_interval": 60,
            "timeout": 30,
            "enable_location_tracking": False,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_SOURCE] == AUTH_SOURCE_MANUAL
    assert result["data"][CONF_AUTH_URL] == FAKE_AUTH_URL
    assert result["data"][CONF_API_KEY] == FAKE_API_KEY
    assert result["result"].unique_id == FAKE_AUTH_URL


async def test_manual_flow_allows_unprotected_standalone(
    hass,
    mock_auth_client,
) -> None:
    """Standalone setups without API_KEY remain supported."""
    result = await _open_manual_form(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: FAKE_AUTH_URL},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "configure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Unprotected Test Family Link",
            "update_interval": 60,
            "timeout": 30,
            "enable_location_tracking": False,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_SOURCE] == AUTH_SOURCE_MANUAL
    assert result["data"][CONF_AUTH_URL] == FAKE_AUTH_URL
    assert CONF_API_KEY not in result["data"]


async def test_manual_flow_stores_clean_url_and_separate_key(
    hass,
    mock_auth_client,
    caplog,
) -> None:
    """Entry data and unique ID never contain a credential-bearing URL."""
    result = await _open_manual_form(hass)

    with caplog.at_level(logging.DEBUG):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_AUTH_URL: f" {FAKE_AUTH_URL}/ ", CONF_API_KEY: FAKE_API_KEY},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "configure"
        assert FAKE_API_KEY not in str(result.get("description_placeholders", {}))

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "name": "Test Family Link",
                "update_interval": 60,
                "timeout": 30,
                "enable_location_tracking": False,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_AUTH_URL] == FAKE_AUTH_URL
    assert result["data"][CONF_API_KEY] == FAKE_API_KEY
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.unique_id == FAKE_AUTH_URL
    assert FAKE_API_KEY not in entry.unique_id
    assert FAKE_API_KEY not in caplog.text


@pytest.mark.parametrize(
    "auth_url",
    [
        f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}",
        "http://user:password@auth.invalid:8099",
        "http://auth.invalid:8099/#fragment",
        "ftp://auth.invalid:8099",
    ],
)
async def test_manual_flow_rejects_unsafe_url(
    hass,
    mock_auth_client,
    caplog,
    auth_url: str,
) -> None:
    """New entries reject all URL-embedded credentials and metadata."""
    result = await _open_manual_form(hass)

    with caplog.at_level(logging.DEBUG):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_AUTH_URL: auth_url, CONF_API_KEY: FAKE_API_KEY},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_url"
    assert FAKE_API_KEY not in caplog.text


async def test_manual_flow_reports_rejected_key_without_leaking_it(
    hass,
    mock_auth_client,
    monkeypatch,
    caplog,
) -> None:
    """A 403 maps to the key error without reflecting the credential."""

    async def _rejected(_client):
        raise AuthServerApiKeyError

    monkeypatch.setattr(AddonCookieClient, "async_validate_manual_endpoint", _rejected)
    result = await _open_manual_form(hass)

    with caplog.at_level(logging.DEBUG):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_api_key"
    assert FAKE_API_KEY not in caplog.text


async def test_reconfigure_masks_existing_key(hass, mock_auth_client) -> None:
    """Credential updates never suggest or display the stored key."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    assert FAKE_API_KEY not in str(result["data_schema"])
    fields = {
        marker.schema: validator
        for marker, validator in result["data_schema"].schema.items()
    }
    assert fields[CONF_API_KEY].config["type"] == TextSelectorType.PASSWORD
    assert "autocomplete" not in fields[CONF_AUTH_URL].config
    assert "autocomplete" not in fields[CONF_API_KEY].config
    assert CONF_CLEAR_API_KEY in fields


async def test_reconfigure_blank_key_preserves_existing_key(
    hass,
    mock_auth_client,
) -> None:
    """An empty masked field keeps the existing credential."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: ""},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_API_KEY] == FAKE_API_KEY


async def test_reconfigure_can_clear_existing_key(
    hass,
    mock_auth_client,
) -> None:
    """An explicit clear control removes a formerly configured key."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_CLEAR_API_KEY: True},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert CONF_API_KEY not in entry.data


async def test_reconfigure_rejects_new_and_clear_key_together(
    hass,
    mock_auth_client,
) -> None:
    """A contradictory credential update is rejected before validation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_AUTH_URL: FAKE_AUTH_URL,
            CONF_API_KEY: "replacement-fake-key",
            CONF_CLEAR_API_KEY: True,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "api_key_conflict"
    assert entry.data[CONF_API_KEY] == FAKE_API_KEY


async def test_reconfigure_new_url_requires_explicit_key_decision(
    hass,
    mock_auth_client,
) -> None:
    """An old endpoint's key cannot be reused implicitly for a new URL."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)
    new_url = "http://new-auth.invalid:8099"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: new_url, CONF_API_KEY: ""},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "api_key_required_for_new_url"
    assert entry.data[CONF_AUTH_URL] == FAKE_AUTH_URL
    assert entry.data[CONF_API_KEY] == FAKE_API_KEY


async def test_reconfigure_unprotected_entry_can_change_url_without_key(
    hass,
    mock_auth_client,
) -> None:
    """An unprotected standalone entry can move without a fake clear step."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_AUTH_SOURCE: AUTH_SOURCE_MANUAL},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)
    new_url = "http://new-auth.invalid:8099"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: new_url},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_AUTH_URL] == new_url
    assert CONF_API_KEY not in entry.data


async def test_reconfigure_rejects_duplicate_without_network(
    hass,
    mock_auth_client,
    monkeypatch,
) -> None:
    """Changing to an existing endpoint aborts before validation traffic."""
    first = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    first.add_to_hass(hass)
    second_url = "http://other-auth.invalid:8099"
    second = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: second_url, CONF_API_KEY: "other-fake-key"},
        unique_id=second_url,
        version=2,
    )
    second.add_to_hass(hass)
    load_cookies = AsyncMock()
    monkeypatch.setattr(AddonCookieClient, "load_cookies", load_cookies)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": second.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: "replacement-fake-key"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    load_cookies.assert_not_awaited()
    assert second.unique_id == second_url


async def test_reconfigure_maps_403_to_api_key_error(
    hass,
    mock_auth_client,
    monkeypatch,
) -> None:
    """A rejected replacement key does not look like expired Google cookies."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
        unique_id=FAKE_AUTH_URL,
        version=2,
    )
    entry.add_to_hass(hass)

    async def _rejected(client):
        client.last_fetch_status = 403
        return None

    monkeypatch.setattr(AddonCookieClient, "load_cookies", _rejected)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: "replacement-fake-key"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_api_key"
