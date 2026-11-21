"""The device switch reads every restriction Google enforces, school time included (#176)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.exceptions import SessionExpiredError
from custom_components.familylink.switch import FamilyLinkDeviceSwitch

CHILD_ID = "child-1"
DEVICE_ID = "device-1"


def _switch(*, locked: bool = False, bonus_minutes: int = 0, bedtime_active: bool = False,
            schooltime_active: bool = False, daily_limit_remaining: int = 120) -> FamilyLinkDeviceSwitch:
    device = {"id": DEVICE_ID, "name": "Phone", "locked": locked}
    coordinator = SimpleNamespace(
        data={
            "children_data": [
                {
                    "child_id": CHILD_ID,
                    "child_name": "Kid",
                    "devices": [device],
                    "devices_time_data": {
                        DEVICE_ID: {
                            "bonus_minutes": bonus_minutes,
                            "bedtime_active": bedtime_active,
                            "schooltime_active": schooltime_active,
                            "daily_limit_remaining": daily_limit_remaining,
                            "remaining_minutes": daily_limit_remaining,
                        }
                    },
                }
            ]
        },
        last_update_success=True,
        child_device_ids={},
    )
    return FamilyLinkDeviceSwitch(coordinator, device, CHILD_ID, "Kid")


@pytest.mark.parametrize(
    ("kwargs", "is_on", "reason", "icon"),
    [
        ({}, True, "none", "mdi:cellphone"),
        ({"locked": True}, False, "manually_locked", "mdi:cellphone-lock"),
        ({"bedtime_active": True}, False, "bedtime_active", "mdi:cellphone-off"),
        ({"schooltime_active": True}, False, "school_time_active", "mdi:school"),
        ({"daily_limit_remaining": 0}, False, "daily_limit_reached", "mdi:cellphone-remove"),
        # A running bonus wins over bedtime and school time alike
        ({"schooltime_active": True, "bonus_minutes": 15}, True, "bonus_active", "mdi:cellphone-clock"),
        ({"bedtime_active": True, "bonus_minutes": 15}, True, "bonus_active", "mdi:cellphone-clock"),
        # A manual lock wins over a bonus
        ({"locked": True, "bonus_minutes": 15}, False, "manually_locked", "mdi:cellphone-lock"),
    ],
)
def test_state_reason_and_icon_follow_every_restriction(kwargs, is_on, reason, icon) -> None:
    switch = _switch(**kwargs)

    assert switch.is_on is is_on
    assert switch.extra_state_attributes["restriction_reason"] == reason
    assert switch.icon == icon


def test_school_time_is_exposed_as_an_attribute_too() -> None:
    attributes = _switch(schooltime_active=True).extra_state_attributes

    assert attributes["school_time_active"] is True
    assert attributes["bedtime_active"] is False
    assert attributes["daily_limit_reached"] is False


async def test_an_expired_session_reaches_the_parent_as_such() -> None:
    """async_control_device returned False on it: the parent read "Failed to lock"."""
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator.client = MagicMock()
    coordinator.client.async_control_device = AsyncMock(side_effect=SessionExpiredError("Session expired, please re-authenticate"))
    coordinator._ha_writes_running, coordinator._ha_write_ended = {}, {}
    with pytest.raises(SessionExpiredError):
        await coordinator.async_control_device(DEVICE_ID, "lock", CHILD_ID)

    switch = _switch()
    switch.coordinator.async_control_device = coordinator.async_control_device
    with pytest.raises(HomeAssistantError, match="Session expired"):
        await switch.async_turn_on()
