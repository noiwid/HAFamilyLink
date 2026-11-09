"""Strict mode put school time back as an override "now -> 23:59" (2.6.0).

A Saturday morning, school time was switched off on Google's side: the
revert posted school time from 07:15 to 23:59 on a day without school time,
and the device was locked from 07:58. On a school day, a parent's unlock
during school time read as "school time switched off" and was undone 10 s
later. The revert now puts the weekly schedule back instead, and only an
override posted today or a scheduled window is a today state to enforce.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.strict_mode import (
    ACTION_ENABLE_SCHOOL_TIME,
    STRICT_RULES,
    plan_strict_actions,
)

CHILD = "child-1"
DEVICE = "device-1"
RULE = "2c578e54-e390-429a-b53e-53221a9719bd"


def _child(*, weekly: bool, scheduled_today: bool | None, today: bool | None,
           override: bool | None) -> dict:
    return {
        "child_id": CHILD,
        "child_name": "Kid",
        "devices": [{"id": DEVICE, "locked": False}],
        "devices_time_data": {DEVICE: {"daily_limit_enabled": True, "daily_limit_remaining": 60}},
        "daily_limit_enabled": True,
        "bedtime_enabled": True,
        "bedtime_enabled_today": True,
        "school_time_enabled": weekly,
        "school_time_scheduled_today": scheduled_today,
        "school_time_enabled_today": today,
        "school_time_today_override": override,
    }


def _actions(child, device_intent: str | None = None) -> list[str]:
    intents = {
        "policies": {"bedtime": True, "daily_limit": True, "school_time": True},
        "devices": {DEVICE: device_intent} if device_intent else {},
        "values": {},
    }
    return [a["action"] for a in plan_strict_actions(child, set(STRICT_RULES), frozenset(), intents, today=6)]


def test_weekend_without_school_time_is_not_school_time_switched_off():
    child = _child(weekly=True, scheduled_today=False, today=False, override=None)
    assert ACTION_ENABLE_SCHOOL_TIME not in _actions(child)


def test_weekly_school_time_switched_off_on_a_weekend_is_put_back():
    child = _child(weekly=False, scheduled_today=False, today=False, override=None)
    assert ACTION_ENABLE_SCHOOL_TIME in _actions(child)


def test_school_window_suspended_by_an_unlock_from_ha_is_left_alone():
    child = _child(weekly=True, scheduled_today=False, today=False, override=None)
    assert _actions(child, device_intent="unlock") == []


def test_school_time_switched_off_for_today_is_put_back():
    child = _child(weekly=True, scheduled_today=True, today=False, override=False)
    assert ACTION_ENABLE_SCHOOL_TIME in _actions(child)


def _override(uuid: str, created: datetime, action: int, weekday: int) -> list:
    return [uuid, str(int(created.timestamp() * 1000)), 9, "", "", None, None, None, "acc",
            None, None, None, [action, [0, 0], [23, 59], None, [weekday, RULE]]]


def test_overrides_of_previous_weeks_are_not_today():
    data = [None, None, [
        _override("last-monday", datetime(2026, 11, 2, 7, 0), 1, 1),
        _override("today", datetime(2026, 11, 9, 11, 30), 2, 1),
    ]]
    since = int(datetime(2026, 11, 9).timestamp() * 1000)
    found = FamilyLinkClient._parse_schooltime_overrides(data, RULE, 1, since_ms=since)
    assert [uuid for uuid, _ts, _action in found] == ["today"]
    assert len(FamilyLinkClient._parse_schooltime_overrides(data, RULE, 1)) == 2


async def test_strict_mode_restores_school_time_without_a_today_override() -> None:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator.hass = MagicMock()
    coordinator.client = MagicMock()
    coordinator.client.async_restore_school_time = AsyncMock(return_value=True)
    coordinator.client.async_enable_school_time = AsyncMock(return_value=True)
    coordinator._pending_time_limit_states = {}
    coordinator._pending_lock_states = {}
    coordinator._strict_cooldown = {}
    coordinator._strict_attempts = {}
    coordinator._ha_writes_running = {}
    coordinator._ha_write_ended = {}
    coordinator._ha_bonus_until = {}
    coordinator.strict_mode_status = {}
    coordinator._save_strict_intents = MagicMock()
    coordinator._strict_intents = {}
    coordinator._intents_for(CHILD)

    child = _child(weekly=False, scheduled_today=False, today=False, override=None)
    action = {"action": ACTION_ENABLE_SCHOOL_TIME, "child_id": CHILD, "reason": "school time switched off"}
    await coordinator._async_run_strict_action(child, action)

    coordinator.client.async_restore_school_time.assert_awaited_once_with(account_id=CHILD)
    coordinator.client.async_enable_school_time.assert_not_awaited()
