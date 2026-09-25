"""A daily limit set from Home Assistant is declared to strict mode before it is written.

The client verifies each override for several seconds; a refresh in between must
not find the old reference and put the old quota back (which also made the
verification fail, so the new value was never recorded). Seen live on
2026-09-25: three attempts to move a quota from 300 to 400 min were fought by
strict mode within the same second.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.familylink import async_setup_services
from custom_components.familylink.const import DOMAIN
from custom_components.familylink.number import FamilyLinkDailyLimitNumber

CHILD_ID = "child-1"
PHONE = "device-phone"
TABLET = "device-tablet"


def _tracking(coordinator, calls: list, *, weekly_ok: bool = True, today_ok: bool = True) -> None:
    """Make the strict mode hooks and the client writes log their order."""
    coordinator.record_daily_limit_minutes = MagicMock(
        side_effect=lambda *a, **k: calls.append(("record", a[1], a[2])) or 300
    )
    coordinator.restore_daily_limit_minutes = MagicMock(
        side_effect=lambda *a, **k: calls.append(("restore", a[1], a[2]))
    )

    async def weekly(day, minutes, child_id):
        calls.append(("weekly", day, minutes))
        return weekly_ok

    async def today(daily_minutes, device_id, account_id):
        calls.append(("today", device_id, daily_minutes))
        return today_ok

    coordinator.client.async_set_weekly_daily_limit = AsyncMock(side_effect=weekly)
    coordinator.client.async_set_daily_limit = AsyncMock(side_effect=today)


def _number(calls: list, day: int, **kwargs) -> FamilyLinkDailyLimitNumber:
    coordinator = SimpleNamespace(
        client=SimpleNamespace(),
        data={"children_data": [{"child_id": CHILD_ID, "devices": [{"id": PHONE}, {"id": TABLET}]}]},
        async_request_refresh=AsyncMock(),
        last_update_success=True,
    )
    _tracking(coordinator, calls, **kwargs)
    return FamilyLinkDailyLimitNumber(coordinator, CHILD_ID, "Kid", day)


def _today() -> int:
    from homeassistant.util import dt as dt_util

    return dt_util.now().isoweekday()


async def test_number_declares_the_quota_before_writing_it() -> None:
    calls: list = []
    number = _number(calls, _today())

    await number.async_set_native_value(400)

    assert calls[0] == ("record", 400, _today())
    assert calls[1] == ("weekly", _today(), 400)
    assert {c for c in calls if c[0] == "today"} == {("today", PHONE, 400), ("today", TABLET, 400)}
    assert not [c for c in calls if c[0] == "restore"]


async def test_number_puts_the_previous_reference_back_when_google_refuses() -> None:
    calls: list = []
    number = _number(calls, _today(), today_ok=False)

    await number.async_set_native_value(400)

    assert calls[0] == ("record", 400, _today())
    assert calls[-1] == ("restore", _today(), 300)


async def test_number_of_another_weekday_writes_the_weekly_quota_only() -> None:
    calls: list = []
    day = 1 if _today() != 1 else 2
    number = _number(calls, day)

    await number.async_set_native_value(240)

    assert calls == [("record", 240, day), ("weekly", day, 240)]


@pytest.fixture
async def services(hass, coordinator):
    hass.states.async_set("switch.kid_phone", "on", {"device_id": PHONE, "child_id": CHILD_ID})
    coordinator.data = {"children_data": [{"child_id": CHILD_ID, "devices": [{"id": PHONE}, {"id": TABLET}]}]}
    await async_setup_services(hass, coordinator)
    return coordinator


async def test_service_declares_the_quota_before_writing_it(hass, services) -> None:
    calls: list = []
    _tracking(services, calls)

    await hass.services.async_call(
        DOMAIN, "set_daily_limit", {"child_id": CHILD_ID, "daily_minutes": 400}, blocking=True
    )

    assert calls[0] == ("record", 400, _today())
    assert calls[1:] == [("today", PHONE, 400), ("today", TABLET, 400)]


async def test_service_restores_the_reference_only_when_nothing_was_taken(hass, services) -> None:
    calls: list = []
    _tracking(services, calls, today_ok=False)

    # Nothing taken: the service raises for the automation, after the rollback
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "set_daily_limit", {"child_id": CHILD_ID, "daily_minutes": 400}, blocking=True
        )

    assert calls[0] == ("record", 400, _today())
    assert calls[-1] == ("restore", _today(), 300)
