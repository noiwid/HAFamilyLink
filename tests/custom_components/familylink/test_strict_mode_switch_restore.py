"""The per-child strict mode switch keeps its state across a reload or a restart.

The option mirrors the switches only while every child is in the same state.
With two children, one strict and one not, every restart put both back to the
option: the switch inherited RestoreEntity without using it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.core import State
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.switch import FamilyLinkStrictModeSwitch


def _coordinator(option: bool) -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator.strict_mode_default = option
    coordinator._strict_mode_children = {}
    coordinator.async_add_listener = MagicMock()
    return coordinator


async def _add(hass, coordinator, child_id: str) -> FamilyLinkStrictModeSwitch:
    switch = FamilyLinkStrictModeSwitch(coordinator, child_id, child_id)
    switch.hass = hass
    switch.entity_id = f"switch.{child_id}_strict_mode"
    await switch.async_added_to_hass()
    return switch


async def test_two_children_one_strict_survive_a_reload(hass) -> None:
    mock_restore_cache_with_extra_data(hass, [
        (State("switch.kid_a_strict_mode", "on"), {"option": False}),
        (State("switch.kid_b_strict_mode", "off"), {"option": False}),
    ])
    coordinator = _coordinator(option=False)

    await _add(hass, coordinator, "kid_a")
    await _add(hass, coordinator, "kid_b")

    assert coordinator.is_strict_mode_enabled("kid_a") is True
    assert coordinator.is_strict_mode_enabled("kid_b") is False


async def test_an_option_changed_in_the_options_screen_wins(hass) -> None:
    """Saved with the option off, reloaded with it on: every child follows the new option."""
    mock_restore_cache_with_extra_data(hass, [(State("switch.kid_a_strict_mode", "off"), {"option": False})])
    coordinator = _coordinator(option=True)

    await _add(hass, coordinator, "kid_a")

    assert coordinator.is_strict_mode_enabled("kid_a") is True


async def test_without_a_saved_state_the_option_applies(hass) -> None:
    mock_restore_cache_with_extra_data(hass, [(State("switch.kid_a_strict_mode", "unavailable"), {"option": False})])
    coordinator = _coordinator(option=False)

    await _add(hass, coordinator, "kid_a")
    await _add(hass, coordinator, "kid_b")

    assert coordinator.is_strict_mode_enabled("kid_a") is False
    assert coordinator.is_strict_mode_enabled("kid_b") is False


def test_the_option_in_force_is_saved_with_the_state() -> None:
    switch = FamilyLinkStrictModeSwitch(_coordinator(option=True), "kid_a", "kid_a")

    assert switch.extra_restore_state_data.as_dict() == {"option": True}
