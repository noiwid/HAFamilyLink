"""Decisions of the strict mode planner (pure module, no Home Assistant)."""

from __future__ import annotations

from custom_components.familylink.strict_mode import (
    ACTION_LOCK_DEVICE,
    DEVICE_INTENT_AUTO_LOCK,
    LOCK_OVERRIDE_UNLOCKED,
    STRICT_RULES,
    device_is_usable,
    plan_strict_actions,
)

CHILD = "child-1"
DEVICE = "device-1"


def _child(*, locked: bool, bonus_minutes: int = 0, bonus_override_id: str | None = None,
           bedtime_active: bool = False, schooltime_active: bool = False,
           lock_override: int | None = None) -> dict:
    return {
        "child_id": CHILD,
        "child_name": "Kid",
        "devices": [{"id": DEVICE, "name": "Phone", "locked": locked}],
        "devices_time_data": {
            DEVICE: {
                "bonus_minutes": bonus_minutes,
                "bonus_override_id": bonus_override_id,
                "bedtime_active": bedtime_active,
                "schooltime_active": schooltime_active,
                "daily_limit_enabled": True,
                "daily_limit_remaining": 120,
                "lock_override": lock_override,
            }
        },
        "daily_limit_enabled": True,
        "bedtime_enabled": True,
        "bedtime_enabled_today": True,
        "school_time_enabled": False,
        "school_time_enabled_today": False,
    }


def _intents(device_intent: str | None) -> dict:
    return {
        "policies": {"bedtime": True, "daily_limit": True, "school_time": False},
        "devices": {DEVICE: device_intent} if device_intent else {},
        "values": {},
    }


def _actions(child, intents, ha_bonus_devices=frozenset()):
    return [a["action"] for a in plan_strict_actions(child, set(STRICT_RULES), ha_bonus_devices, intents, today=1)]


def test_locked_from_ha_and_unlocked_on_google_side_is_relocked():
    child = _child(locked=False)
    assert _actions(child, _intents("lock")) == [ACTION_LOCK_DEVICE]


def test_bonus_granted_from_ha_suspends_the_relock():
    """The +30 min button on a device locked from HA today: no relock, no bonus cancel."""
    child = _child(locked=False, bonus_minutes=30, bonus_override_id="ovr-1")
    assert _actions(child, _intents("lock"), frozenset({DEVICE})) == []


def test_bonus_from_google_side_on_a_locked_device_is_cancelled_then_relocked():
    child = _child(locked=False, bonus_minutes=30, bonus_override_id="ovr-1")
    assert _actions(child, _intents("lock")) == ["cancel_bonus", ACTION_LOCK_DEVICE]


def test_relock_resumes_once_the_ha_bonus_is_over():
    """The HA bonus allowance expired (device no longer in ha_bonus_devices)."""
    child = _child(locked=False)
    assert _actions(child, _intents("lock"), frozenset()) == [ACTION_LOCK_DEVICE]


def test_ha_bonus_also_suspends_a_strict_mode_auto_lock():
    child = _child(locked=False, bonus_minutes=15, bonus_override_id="ovr-2", bedtime_active=True,
                   lock_override=LOCK_OVERRIDE_UNLOCKED)
    assert _actions(child, _intents(DEVICE_INTENT_AUTO_LOCK), frozenset({DEVICE})) == []


def test_locked_device_with_lock_intent_needs_nothing():
    child = _child(locked=True)
    assert _actions(child, _intents("lock")) == []

def test_school_time_makes_the_device_unusable_like_bedtime():
    """Issue #176: the usability reading counted bedtime and the daily limit, never school time."""
    child = _child(locked=False, schooltime_active=True)
    device = child["devices"][0]
    time_data = child["devices_time_data"][DEVICE]
    assert device_is_usable(device, time_data) is False
    assert device_is_usable(device, {**time_data, "schooltime_active": False}) is True
    # A running bonus still wins, as it does for bedtime
    assert device_is_usable(device, {**time_data, "bonus_minutes": 15}) is True


def test_unlock_override_during_school_time_is_countered():
    """A Google-side unlock bypassing school time is locked again, like a bedtime bypass."""
    child = _child(locked=False, schooltime_active=True, lock_override=LOCK_OVERRIDE_UNLOCKED)
    assert _actions(child, _intents(None)) == [ACTION_LOCK_DEVICE]
