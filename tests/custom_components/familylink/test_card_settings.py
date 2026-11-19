"""The card's integration settings: administrators only, and applied without a reload where possible."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.exceptions import Unauthorized

from custom_components.familylink import async_options_updated, card

RULES = ["bonus", "lock", "bedtime", "daily_limit", "school_time", "values"]


def _entry(options: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(entry_id="e1", domain="familylink", data={}, options=dict(options or {}))


def _hass(entry: SimpleNamespace) -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_get_entry = lambda entry_id: entry if entry_id == entry.entry_id else None

    def update(e, options):
        e.options = options

    hass.config_entries.async_update_entry = MagicMock(side_effect=update)
    return hass


def _call(hass, msg: dict, admin: bool = True) -> MagicMock:
    connection = MagicMock()
    connection.user = SimpleNamespace(is_admin=admin, id="u1")
    registry = MagicMock()
    registry.async_get = lambda entity_id: SimpleNamespace(config_entry_id="e1") if entity_id == "switch.phone" else None
    with patch.object(card.er, "async_get", return_value=registry):
        card.ws_settings(hass, connection, {"id": 1, "type": "familylink/settings", **msg})
    return connection


def test_the_defaults_are_read_when_no_option_was_saved() -> None:
    entry = _entry()

    connection = _call(_hass(entry), {"entity_id": "switch.phone"})

    connection.send_result.assert_called_once_with(1, {
        "strict_mode_rules": RULES,
        "lock_keeps_allowed_apps": True,
        "enable_location_tracking": False,
    })


def test_an_administrator_changes_the_options_and_keeps_the_others() -> None:
    entry = _entry({"allowed_users": ["u2"], "update_interval": 60})
    hass = _hass(entry)

    connection = _call(hass, {"entity_id": "switch.phone", "set": {"strict_mode_rules": ["bonus"], "lock_keeps_allowed_apps": False}})

    assert entry.options == {"allowed_users": ["u2"], "update_interval": 60, "strict_mode_rules": ["bonus"], "lock_keeps_allowed_apps": False}
    assert connection.send_result.call_args.args[1]["strict_mode_rules"] == ["bonus"]


def test_a_user_who_is_not_an_administrator_is_refused() -> None:
    entry = _entry()
    hass = _hass(entry)

    with pytest.raises(Unauthorized):
        _call(hass, {"entity_id": "switch.phone", "set": {"enable_location_tracking": True}}, admin=False)

    hass.config_entries.async_update_entry.assert_not_called()


def test_an_entity_of_another_integration_is_not_found() -> None:
    connection = _call(_hass(_entry()), {"entity_id": "switch.other"})

    connection.send_error.assert_called_once()


async def test_rules_and_lock_apply_without_a_reload_but_location_reloads() -> None:
    entry = _entry({"strict_mode": True})
    coordinator = SimpleNamespace(
        applied_options={"strict_mode": True}, strict_mode_default=True, strict_rules=frozenset(RULES),
        client=SimpleNamespace(lock_keeps_allowed_apps=True),
    )
    hass = MagicMock()
    hass.data = {"familylink": {"e1": coordinator}}
    hass.config_entries.async_reload = AsyncMock()

    entry.options = {"strict_mode": True, "strict_mode_rules": ["lock"], "lock_keeps_allowed_apps": False}
    await async_options_updated(hass, entry)

    hass.config_entries.async_reload.assert_not_called()
    assert coordinator.strict_rules == frozenset({"lock"})
    assert coordinator.client.lock_keeps_allowed_apps is False

    entry.options = {**entry.options, "enable_location_tracking": True}
    await async_options_updated(hass, entry)

    hass.config_entries.async_reload.assert_awaited_once_with("e1")
