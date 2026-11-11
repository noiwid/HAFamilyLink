"""Each device has its own battery sensor, read from the child's device list (#223)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.exceptions import NetworkError, SessionExpiredError
from custom_components.familylink.sensor import FamilyLinkDeviceBatterySensor

CHILD_ID = "child-1"


def _device(device_id: str, battery: object) -> list:
    device = [None] * 28
    device[0] = device_id
    device[22] = battery
    return device


def test_parser_reads_each_device_and_skips_unusable_readings() -> None:
    data = [
        [None, "1"],
        [
            _device("tablet", [60, 1]),
            _device("phone", [0, 2]),
            _device("no-reading", None),
            _device("empty", []),
            _device("not-a-level", ["60", 1]),
            _device("boolean", [True, 1]),
            _device("too-high", [101, 1]),
            ["short"],
            "not-a-device",
        ],
        None,
        None,
        2,
    ]

    assert FamilyLinkClient._parse_device_batteries(data) == {"tablet": 60, "phone": 0}


@pytest.mark.parametrize("data", [None, [], {}, [None], [None, None], [None, "x"]])
def test_parser_survives_an_unexpected_shape(data: object) -> None:
    assert FamilyLinkClient._parse_device_batteries(data) == {}


def _coordinator(batteries: AsyncMock) -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    client = MagicMock()
    client.async_get_family_members = AsyncMock(return_value={"members": [{
        "userId": CHILD_ID,
        "profile": {"displayName": "Kid"},
        "memberSupervisionInfo": {"isSupervisedMember": True},
    }]})
    client.async_get_apps_and_usage = AsyncMock(return_value={"apps": [], "deviceInfo": [], "appUsageSessions": []})
    client.async_get_time_limit = AsyncMock(return_value={})
    client.async_get_applied_time_limits = AsyncMock(return_value={})
    client.async_get_daily_screen_time = AsyncMock(return_value=None)
    client.async_get_contact_restriction = AsyncMock(return_value=None)
    client.async_get_device_batteries = batteries
    coordinator.client = client
    coordinator._last_known_data = {"children_data": [{"child_id": CHILD_ID, "device_batteries": {"phone": 42}}]}
    coordinator._location_tracking_enabled = False
    coordinator._pending_lock_states = {}
    coordinator._pending_time_limit_states = {}
    coordinator._async_child_websites = AsyncMock(return_value=None)
    coordinator._async_child_play_settings = AsyncMock(return_value=None)
    return coordinator


async def test_fresh_readings_replace_the_cache() -> None:
    coordinator = _coordinator(AsyncMock(return_value={"phone": 50}))

    data = await coordinator._async_fetch_data()

    assert data["children_data"][0]["device_batteries"] == {"phone": 50}


async def test_transient_error_keeps_the_last_readings() -> None:
    coordinator = _coordinator(AsyncMock(side_effect=NetworkError("503")))

    data = await coordinator._async_fetch_data()

    assert data["children_data"][0]["device_batteries"] == {"phone": 42}


async def test_expired_session_is_not_swallowed() -> None:
    coordinator = _coordinator(AsyncMock(side_effect=SessionExpiredError("401")))

    with pytest.raises(SessionExpiredError):
        await coordinator._async_fetch_data()


def _sensor(device_id: str, *, success: bool = True) -> FamilyLinkDeviceBatterySensor:
    sensor = FamilyLinkDeviceBatterySensor.__new__(FamilyLinkDeviceBatterySensor)
    sensor.coordinator = SimpleNamespace(
        data={"children_data": [{"child_id": CHILD_ID, "device_batteries": {"phone": 0}}]},
        last_update_success=success,
    )
    sensor._child_id = CHILD_ID
    sensor._device_id = device_id
    return sensor


def test_sensor_reads_its_own_device() -> None:
    sensor = _sensor("phone")

    assert sensor.native_value == 0
    assert sensor.available is True


def test_sensor_without_a_reading_is_unavailable() -> None:
    sensor = _sensor("tablet")

    assert sensor.native_value is None
    assert sensor.available is False


def test_sensor_is_unavailable_when_the_update_failed() -> None:
    assert _sensor("phone", success=False).available is False


def test_unique_id_differs_from_the_child_battery_sensor() -> None:
    sensor = FamilyLinkDeviceBatterySensor(MagicMock(), CHILD_ID, "Kid", "phone", "Phone")

    assert sensor.unique_id == f"{DOMAIN}_{CHILD_ID}_phone_battery_level"
    assert sensor.name == "Phone Battery Level"
