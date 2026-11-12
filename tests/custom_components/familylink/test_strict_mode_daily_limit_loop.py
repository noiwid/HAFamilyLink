"""Strict mode looped on the daily limit all night (2026-11-08/09, D-049).

21:09 Google listed both devices without today's daily-limit data, which
was read as "limit off": strict mode switched a limit that was on back on
every 97 s until midnight. 00:03 the parent
switched the limit off from HA, then a script wrote the weekly quotas, which
Google stores with the limit on: strict mode switched it off every 97 s for
two hours, with no effect (a today override was in force). One notification
each time.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.strict_mode import (
    ACTION_ENABLE_DAILY_LIMIT,
    ACTION_LOCK_DEVICE,
    ACTION_UNLOCK_DEVICE,
    DEVICE_INTENT_AUTO_LOCK,
    STRICT_RULES,
    plan_strict_actions,
)

CHILD = "child-1"
DEVICE = "device-1"


def _coordinator() -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator.hass = MagicMock()
    coordinator.client = MagicMock()
    coordinator.client.async_enable_daily_limit = AsyncMock(return_value=True)
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
    return coordinator


def _child(daily_limit_enabled, weekly_minutes=240) -> dict:
    return {
        "child_id": CHILD,
        "child_name": "Kid",
        "devices": [{"id": DEVICE, "locked": True}],
        "devices_time_data": {DEVICE: {"daily_limit_enabled": daily_limit_enabled}},
        "daily_limit_enabled": daily_limit_enabled,
        "daily_limit_week": [{"day": 4, "weekly_minutes": weekly_minutes}],
        "bedtime_enabled": True,
        "bedtime_enabled_today": True,
        "school_time_enabled": False,
        "school_time_enabled_today": False,
    }


def _actions(child, policies, values=None) -> list[str]:
    intents = {"policies": policies, "devices": {}, "values": values or {}}
    return [a["action"] for a in plan_strict_actions(child, set(STRICT_RULES), frozenset(), intents, today=1)]


def test_a_locked_device_without_a_limit_row_is_not_read_as_limit_off() -> None:
    policies = {"bedtime": True, "daily_limit": True, "school_time": False}
    assert _actions(_child(None), policies) == []
    assert _actions(_child(False), policies) == ["enable_daily_limit"]


def test_a_restriction_switched_on_from_family_link_is_left_on() -> None:
    """Strict mode guards what is active: more protection is never undone."""
    off = {"bedtime": False, "daily_limit": False, "school_time": False}
    child = {**_child(True), "school_time_enabled": True, "school_time_enabled_today": True}
    assert _actions(child, off) == []
    # A restriction switched off on Google's side is still put back
    assert _actions(_child(False), {**off, "daily_limit": True}) == ["enable_daily_limit"]


def test_no_quota_written_while_the_parent_keeps_the_limit_off() -> None:
    """A quota write switches the limit on at Google, the other rule would switch it off again."""
    values = {"weekly_limits": {"4": 180}}
    on = {"bedtime": True, "daily_limit": True, "school_time": False}
    off = {**on, "daily_limit": False}
    assert _actions(_child(True), on, values) == ["set_weekly_limit"]
    assert "set_weekly_limit" not in _actions(_child(False), off, values)


def test_a_quota_set_from_ha_switches_the_limit_reference_on() -> None:
    coordinator = _coordinator()
    coordinator._intents_for(CHILD)["policies"]["daily_limit"] = False
    coordinator.record_daily_limit_minutes(CHILD, 180, 1)
    assert coordinator._intents_for(CHILD)["policies"]["daily_limit"] is True


async def test_a_correction_without_effect_is_given_up_after_three_tries() -> None:
    coordinator = _coordinator()
    action = {"action": ACTION_ENABLE_DAILY_LIMIT, "child_id": CHILD, "reason": "off at Google"}
    child = {"child_id": CHILD, "child_name": "Kid", "devices": []}
    for _ in range(5):
        # One poll every cooldown: the 5 s pending state of the last try is long gone
        coordinator._strict_cooldown.clear()
        coordinator._pending_time_limit_states.clear()
        await coordinator._async_run_strict_action(child, action)
    assert coordinator.client.async_enable_daily_limit.await_count == 3
    assert coordinator.hass.bus.async_fire.call_count == 3


async def test_a_correction_given_up_is_tried_again_the_next_day(monkeypatch) -> None:
    from datetime import datetime

    from custom_components.familylink import coordinator as coordinator_module

    coordinator = _coordinator()
    action = {"action": ACTION_ENABLE_DAILY_LIMIT, "child_id": CHILD, "reason": "off at Google"}
    child = {"child_id": CHILD, "child_name": "Kid", "devices": []}
    for day in (9, 10):
        monkeypatch.setattr(coordinator_module.dt_util, "now", lambda day=day: datetime(2026, 11, day, 9, 0))
        for _ in range(4):
            coordinator._strict_cooldown.clear()
            coordinator._pending_time_limit_states.clear()
            await coordinator._async_run_strict_action(child, action)
    assert coordinator.client.async_enable_daily_limit.await_count == 6


def test_the_strict_mode_lock_stays_while_bedtime_is_put_back() -> None:
    """2026-11-09 03:02: bedtime switched off in the app, the tablet unlocked, bedtime restored 3 s later."""
    child = {**_child(True), "bedtime_enabled": False, "bedtime_enabled_today": False}
    child["devices"] = [{"id": DEVICE, "locked": True}]
    child["devices_time_data"] = {DEVICE: {"daily_limit_enabled": True, "bedtime_active": False}}
    intents = {"policies": {"bedtime": True}, "devices": {DEVICE: DEVICE_INTENT_AUTO_LOCK}, "values": {}}
    actions = [a["action"] for a in plan_strict_actions(child, set(STRICT_RULES), frozenset(), intents, today=1)]
    assert actions == ["enable_bedtime"]
    # Bedtime really over (morning): the strict mode lock is lifted
    child = {**child, "bedtime_enabled": True, "bedtime_enabled_today": True}
    actions = [a["action"] for a in plan_strict_actions(child, set(STRICT_RULES), frozenset(), intents, today=1)]
    assert actions == [ACTION_UNLOCK_DEVICE]
    assert ACTION_LOCK_DEVICE not in actions


def test_a_quota_google_refused_puts_the_limit_reference_back() -> None:
    coordinator = _coordinator()
    coordinator._intents_for(CHILD)["policies"]["daily_limit"] = False
    weekly = coordinator.record_daily_limit_minutes(CHILD, 180, 3)
    today = coordinator.record_daily_limit_minutes(CHILD, 180, 1)
    # The service restores the last recorded first
    coordinator.restore_daily_limit_minutes(CHILD, 1, today)
    coordinator.restore_daily_limit_minutes(CHILD, 3, weekly)
    intents = coordinator._intents_for(CHILD)
    assert intents["policies"]["daily_limit"] is False
    assert intents["values"]["weekly_limits"] == {}
    # No reference before: none after
    coordinator._intents_for(CHILD)["policies"].pop("daily_limit")
    coordinator.restore_daily_limit_minutes(CHILD, 1, coordinator.record_daily_limit_minutes(CHILD, 90, 1))
    assert "daily_limit" not in coordinator._intents_for(CHILD)["policies"]


async def test_the_notification_names_who_created_the_bonus() -> None:
    coordinator = _coordinator()
    coordinator.client.async_cancel_time_bonus = AsyncMock(return_value=True)
    coordinator.data = {"family_members": [{"userId": "42", "profile": {"displayName": "Benoit Collin"}}]}
    child = {
        "child_id": CHILD, "child_name": "Kid", "devices": [{"id": DEVICE, "name": "Phone"}],
        "devices_time_data": {DEVICE: {"override_by": "42"}},
    }
    bonus = {"action": "cancel_bonus", "child_id": CHILD, "device_id": DEVICE, "override_id": "o-1", "reason": "bonus"}
    await coordinator._async_run_strict_action(child, bonus)
    event = coordinator.hass.bus.async_fire.call_args.args[1]
    assert event["created_by"] == "Benoit Collin"
    # An account outside the family is given by its id
    coordinator.data = {"family_members": []}
    coordinator._strict_cooldown.clear()
    await coordinator._async_run_strict_action(child, bonus)
    assert coordinator.hass.bus.async_fire.call_args.args[1]["created_by"] == "42"


def test_a_quota_set_on_one_device_is_not_copied_to_the_others(monkeypatch) -> None:
    """set_daily_limit on the tablet alone: strict mode gave the phone the same quota at the next poll."""
    from datetime import datetime

    from custom_components.familylink import coordinator as coordinator_module

    monkeypatch.setattr(coordinator_module.dt_util, "now", lambda: datetime(2026, 11, 9, 9, 0))  # a Monday
    coordinator = _coordinator()
    coordinator.record_daily_limit_minutes(CHILD, 180, 1)
    previous = coordinator.record_daily_limit_minutes(CHILD, 0, 1, device_id="tablet")
    values = coordinator._intents_for(CHILD)["values"]
    assert values == {"weekly_limits": {"1": 180}, "device_limits": {"tablet": 0}}

    child = _child(True)
    child["devices_time_data"] = {
        DEVICE: {"daily_limit_enabled": True, "daily_limit_minutes": 180},
        "tablet": {"daily_limit_enabled": True, "daily_limit_minutes": 0},
    }
    policies = {"bedtime": True, "daily_limit": True, "school_time": False}
    plan = lambda: [  # noqa: E731
        (a["device_id"], a["minutes"])
        for a in plan_strict_actions(child, set(STRICT_RULES), frozenset(), {"policies": policies, "devices": {}, "values": values}, today=1)
        if a["action"] == "set_daily_limit"
    ]
    assert plan() == []
    # Changed on Google's side: each device goes back to its own quota
    child["devices_time_data"][DEVICE]["daily_limit_minutes"] = 600
    child["devices_time_data"]["tablet"]["daily_limit_minutes"] = 600
    assert plan() == [(DEVICE, 180), ("tablet", 0)]

    # Refused by Google: the device has no quota of its own any more
    coordinator.restore_daily_limit_minutes(CHILD, 1, previous, device_id="tablet")
    assert values["device_limits"] == {}
    # A quota for the whole child today, or the next day, drops the per-device ones
    coordinator.record_daily_limit_minutes(CHILD, 0, 1, device_id="tablet")
    coordinator.record_daily_limit_minutes(CHILD, 200, 1)
    assert "device_limits" not in values
    coordinator.record_daily_limit_minutes(CHILD, 0, 1, device_id="tablet")
    monkeypatch.setattr(coordinator_module.dt_util, "now", lambda: datetime(2026, 11, 10, 9, 0))
    assert "device_limits" not in coordinator._intents_for(CHILD)["values"]
