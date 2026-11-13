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
