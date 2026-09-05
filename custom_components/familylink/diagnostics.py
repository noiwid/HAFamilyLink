"""Diagnostics support for Google Family Link."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .auth.addon_client import split_legacy_auth_url
from .const import CONF_API_KEY, CONF_AUTH_URL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return credential-redacted config-entry diagnostics."""
    entry_data = dict(entry.data)
    if auth_url := entry_data.get(CONF_AUTH_URL):
        try:
            entry_data[CONF_AUTH_URL], _ = split_legacy_auth_url(auth_url)
        except (TypeError, ValueError):
            entry_data[CONF_AUTH_URL] = "**REDACTED**"
    return {
        "entry_data": async_redact_data(entry_data, {CONF_API_KEY}),
        "entry_options": async_redact_data(dict(entry.options), {CONF_API_KEY}),
    }
