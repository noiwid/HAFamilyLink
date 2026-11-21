"""Strict mode does not "correct" the parent's own clicks from Home Assistant (D-038).

On 2026-11-04 at 17:38, bedtime and the daily limit were switched several
times in a few seconds from HA. Each write takes 2 to 6 s and they end out
of order: strict mode read a Google state that did not show the last click
yet, and ran a plan made before a click, after earlier actions had taken
their seconds. It switched the daily limit back off and sent two "changed
from Family Link" notifications.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.familylink.const import STRICT_MODE_BONUS_GRACE
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.strict_mode import ACTION_ENABLE_DAILY_LIMIT, ACTION_LOCK_DEVICE

CHILD = "child-1"
DEVICE = "device-1"


def _coordinator() -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator.hass = MagicMock()
    coordinator.client = MagicMock()
    coordinator.client.async_enable_daily_limit = AsyncMock(return_value=True)
    coordinator.client.async_control_device = AsyncMock(return_value=True)
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


CHILD_DATA = {"child_id": CHILD, "child_name": "Child", "devices": []}
ENABLE_LIMIT = {"action": ACTION_ENABLE_DAILY_LIMIT, "child_id": CHILD, "reason": "daily limit switched off"}


async def test_a_plan_made_before_a_click_is_dropped() -> None:
    coordinator = _coordinator()
    coordinator._intents_for(CHILD)["policies"]["daily_limit"] = True
    planned = {"policies": {"daily_limit": True}, "devices": {}}
    # The parent switches the limit off after the plan, the write ends 6 s before the action runs
    coordinator._intents_for(CHILD)["policies"]["daily_limit"] = False
    coordinator._ha_write_ended[f"{CHILD}:daily_limit"] = time.time() - 6

    await coordinator._async_run_strict_action(CHILD_DATA, ENABLE_LIMIT, planned)

    coordinator.client.async_enable_daily_limit.assert_not_awaited()
    coordinator.hass.bus.async_fire.assert_not_called()


async def test_no_correction_while_a_click_is_being_written() -> None:
    coordinator = _coordinator()
    release = asyncio.Event()

    async def slow_disable(account_id):
        await release.wait()
        return True

    coordinator.client.async_disable_daily_limit = slow_disable
    click = asyncio.create_task(coordinator.async_set_policy(CHILD, "daily_limit", False))
    await asyncio.sleep(0)

    # Running: the refresh may show Google before the click
    await coordinator._async_run_strict_action(CHILD_DATA, ENABLE_LIMIT)
    release.set()
    assert await click
    # Just done: the refresh may still predate it
    await coordinator._async_run_strict_action(CHILD_DATA, ENABLE_LIMIT)

    coordinator.client.async_enable_daily_limit.assert_not_awaited()
    assert coordinator._intents_for(CHILD)["policies"]["daily_limit"] is False


async def test_no_bedtime_correction_while_hours_set_from_ha_are_written() -> None:
    """The reference was recorded after the write, unguarded: a refresh in between put the old hours back."""
    from datetime import time as dtime

    from custom_components.familylink.strict_mode import ACTION_SET_BEDTIME
    from custom_components.familylink.time import BOUND_START, FamilyLinkBedtimeTime

    coordinator = _coordinator()
    coordinator.async_request_refresh = AsyncMock()
    release = asyncio.Event()
    writes = []

    async def set_bedtime(start, end, **kwargs):
        writes.append((start, end))
        if len(writes) == 1:
            await release.wait()
        return True

    coordinator.client.async_set_bedtime = set_bedtime
    entity = FamilyLinkBedtimeTime(coordinator, CHILD, "Child", 1, BOUND_START)
    entity._slot = lambda: {"start": [21, 0], "end": [7, 0]}
    revert = {"action": ACTION_SET_BEDTIME, "child_id": CHILD, "day": 1, "start": [21, 0], "end": [7, 0], "reason": "hours changed"}

    setting = asyncio.create_task(entity.async_set_value(dtime(20, 30)))
    await asyncio.sleep(0)
    # Running: the refresh may show Google before the new hours
    await coordinator._async_run_strict_action(CHILD_DATA, revert)
    release.set()
    await setting
    # Just done: the refresh may still predate it
    await coordinator._async_run_strict_action(CHILD_DATA, revert)

    assert writes == [("20:30", "07:00")]
    assert coordinator._intents_for(CHILD)["values"]["bedtime"]["1"] == [[20, 30], [7, 0]]


def test_a_reference_without_a_child_is_refused_not_given_to_the_first_child() -> None:
    import pytest

    coordinator = _coordinator()
    coordinator.data = {"children_data": [{"child_id": CHILD}, {"child_id": "child-2"}]}

    with pytest.raises(ValueError, match="No child"):
        coordinator.record_policy_intent(None, "bedtime", True)
    assert "bedtime" not in coordinator._intents_for(CHILD)["policies"]


async def test_a_change_from_family_link_is_still_reverted() -> None:
    coordinator = _coordinator()
    coordinator._intents_for(CHILD)["policies"]["daily_limit"] = True
    coordinator._ha_write_ended[f"{CHILD}:daily_limit"] = time.time() - 6
    planned = {"policies": {"daily_limit": True}, "devices": {}}

    await coordinator._async_run_strict_action(CHILD_DATA, ENABLE_LIMIT, planned)

    coordinator.client.async_enable_daily_limit.assert_awaited_once()
    coordinator.hass.bus.async_fire.assert_called_once()


async def test_a_failed_click_records_nothing() -> None:
    coordinator = _coordinator()
    coordinator.client.async_enable_bedtime = AsyncMock(return_value=False)

    assert not await coordinator.async_set_policy(CHILD, "bedtime", True)
    assert "bedtime" not in coordinator._intents_for(CHILD)["policies"]


async def test_a_device_lock_planned_before_an_unlock_click_is_dropped() -> None:
    coordinator = _coordinator()
    planned = {"policies": {}, "devices": {DEVICE: "lock"}}
    coordinator._intents_for(CHILD)["devices"][DEVICE] = "unlock"
    lock = {"action": ACTION_LOCK_DEVICE, "child_id": CHILD, "device_id": DEVICE, "reason": "unlocked"}

    await coordinator._async_run_strict_action(CHILD_DATA, lock, planned)

    coordinator.client.async_control_device.assert_not_awaited()


def test_a_second_ha_bonus_extends_the_protection(monkeypatch) -> None:
    """+30 then +15 min: the protection covers both, the first bonus is not cancelled early."""
    clock = [1000.0]
    monkeypatch.setattr("custom_components.familylink.coordinator.time", SimpleNamespace(time=lambda: clock[0], monotonic=lambda: clock[0]))
    coordinator = _coordinator()
    coordinator.register_ha_bonus("phone", 30)
    first_end = coordinator._ha_bonus_until["phone"]
    clock[0] += 300
    coordinator.register_ha_bonus("phone", 15)
    assert coordinator._ha_bonus_until["phone"] == first_end + 15 * 60 + STRICT_MODE_BONUS_GRACE
    # Taken back from HA (reset button, lock): nothing protected any more
    coordinator.restore_ha_bonus("phone", None)
    assert "phone" not in coordinator._ha_bonus_until


def test_a_reset_keeps_a_bonus_granted_while_it_ran(monkeypatch) -> None:
    """Reset then +15 pressed before the reset ends: the +15 stays protected (2026-11-20 21:16)."""
    clock = [1000.0]
    monkeypatch.setattr("custom_components.familylink.coordinator.time", SimpleNamespace(time=lambda: clock[0], monotonic=lambda: clock[0]))
    coordinator = _coordinator()
    coordinator.register_ha_bonus("phone", 30)
    seen = coordinator.ha_bonus_allowance("phone")
    coordinator.register_ha_bonus("phone", 15)  # pressed while the reset runs
    coordinator.drop_ha_bonus("phone", seen)
    assert "phone" in coordinator._ha_bonus_until
    # a reset with nothing granted meanwhile ends the protection
    coordinator.drop_ha_bonus("phone", coordinator.ha_bonus_allowance("phone"))
    assert "phone" not in coordinator._ha_bonus_until


def test_a_new_bonus_gets_tries_of_its_own() -> None:
    """A bonus posted again after each cancel must not use up the tries and win for the day."""
    from custom_components.familylink.coordinator import _strict_key
    from custom_components.familylink.strict_mode import ACTION_CANCEL_BONUS

    first = {"child_id": CHILD, "action": ACTION_CANCEL_BONUS, "device_id": "phone", "override_id": "o1"}
    assert _strict_key(first) == _strict_key(dict(first))
    assert _strict_key(first) != _strict_key({**first, "override_id": "o2"})
