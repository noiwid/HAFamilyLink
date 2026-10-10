"""A daily limit set for a child skips the devices that take no time limits.

A Google TV / Chromecast advertises no time-limit capability (#173). Google
never applies a daily-limit override there, so the readback reported it as not
applied: the service raised although the phone and tablet had taken the new
quota, and the weekday number put strict mode's previous reference back.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink import async_setup_services
from custom_components.familylink.const import CAP_BEDTIME, CAP_LOCK_WITH_DEADLINE, DOMAIN
from custom_components.familylink.devices import time_limit_device_ids
from custom_components.familylink.number import FamilyLinkDailyLimitNumber

CHILD_ID = "child-1"
PHONE = "device-phone"
TV = "device-tv"
OLD = "device-old"

PHONE_CAPS = ["capabilityAppActivity", CAP_BEDTIME, CAP_LOCK_WITH_DEADLINE]
TV_CAPS = ["capabilityAppActivity", "capabilityDisableApp"]


def _data() -> dict:
    return {
        "children_data": [
            {
                "child_id": CHILD_ID,
                "devices": [
                    {"id": PHONE, "capabilities": PHONE_CAPS},
                    {"id": TV, "capabilities": TV_CAPS},
                    # No capability list (older cache): kept, as for the entities
                    {"id": OLD},
                ],
            },
            {"child_id": "child-2", "devices": [{"id": "other", "capabilities": PHONE_CAPS}]},
        ]
    }


def test_time_limit_device_ids_skips_a_tv() -> None:
    assert time_limit_device_ids(_data(), CHILD_ID) == [PHONE, OLD]
    assert time_limit_device_ids(None, CHILD_ID) == []


def _tracking(coordinator, calls: list) -> None:
    coordinator.record_daily_limit_minutes = MagicMock(return_value=300)
    coordinator.restore_daily_limit_minutes = MagicMock(
        side_effect=lambda *a, **k: calls.append(("restore", a[1], a[2]))
    )

    async def weekly(day, minutes, child_id):
        return True

    async def today(daily_minutes, device_id, account_id):
        calls.append(("today", device_id, daily_minutes))
        # Google never confirms an override on a TV
        return device_id != TV

    coordinator.client.async_set_weekly_daily_limit = AsyncMock(side_effect=weekly)
    coordinator.client.async_set_daily_limit = AsyncMock(side_effect=today)


def _today() -> int:
    from homeassistant.util import dt as dt_util

    return dt_util.now().isoweekday()


async def test_number_for_today_skips_the_tv_and_keeps_the_reference() -> None:
    calls: list = []
    coordinator = SimpleNamespace(
        client=SimpleNamespace(),
        data=_data(),
        async_request_refresh=AsyncMock(),
        last_update_success=True,
    )
    _tracking(coordinator, calls)
    number = FamilyLinkDailyLimitNumber(coordinator, CHILD_ID, "Kid", _today())

    await number.async_set_native_value(400)

    assert [c for c in calls if c[0] == "today"] == [("today", PHONE, 400), ("today", OLD, 400)]
    assert not [c for c in calls if c[0] == "restore"]


@pytest.fixture
async def services(hass, coordinator):
    coordinator.data = _data()
    await async_setup_services(hass, coordinator)
    return coordinator


async def test_service_for_a_child_skips_the_tv(hass, services) -> None:
    calls: list = []
    _tracking(services, calls)

    await hass.services.async_call(
        DOMAIN, "set_daily_limit", {"child_id": CHILD_ID, "daily_minutes": 400}, blocking=True
    )

    assert calls == [("today", PHONE, 400), ("today", OLD, 400)]


async def test_service_for_an_explicit_device_still_targets_it(hass, services) -> None:
    calls: list = []
    _tracking(services, calls)

    await hass.services.async_call(
        DOMAIN, "set_daily_limit", {"device_id": PHONE, "child_id": CHILD_ID, "daily_minutes": 90}, blocking=True
    )

    assert calls == [("today", PHONE, 90)]


async def test_service_for_a_child_with_only_a_tv_says_so(hass, coordinator) -> None:
    coordinator.data = {"children_data": [{"child_id": CHILD_ID, "devices": [{"id": TV, "capabilities": TV_CAPS}]}]}
    await async_setup_services(hass, coordinator)
    _tracking(coordinator, [])

    with pytest.raises(Exception, match="takes a daily limit"):
        await hass.services.async_call(
            DOMAIN, "set_daily_limit", {"child_id": CHILD_ID, "daily_minutes": 400}, blocking=True
        )
    coordinator.client.async_set_daily_limit.assert_not_called()
