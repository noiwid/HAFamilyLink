"""A device Google stops listing in the applied limits (2026-11-17).

Both devices of a child left appliedTimeLimits at 22:05, in the middle of
bedtime and under a lock placed from Home Assistant at 21:33. Lock and bedtime
were no longer applied, the phone was used until 01:33, and strict mode did
nothing: its lock rule was skipped for a device without a row. The same had
happened on 2026-11-08. Strict mode now puts the Home Assistant lock back, and
a row that cannot be read is no longer dropped without a word.
"""

from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from custom_components.familylink.client import api as api_module
from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.strict_mode import (
    ACTION_LOCK_DEVICE,
    DEVICE_INTENT_AUTO_LOCK,
    STRICT_RULES,
    plan_strict_actions,
)

CHILD = "child-1"
DEVICE = "device-1"


def _child(*, capabilities: list[str] | None = None, locked: bool = False) -> dict:
    """Google answered, without the device: no entry in devices_time_data."""
    device = {"id": DEVICE, "name": "Phone", "locked": locked}
    if capabilities is not None:
        device["capabilities"] = capabilities
    return {
        "child_id": CHILD,
        "child_name": "Kid",
        "devices": [device],
        "devices_time_data": {},
        "time_limit_fresh": True,
        "applied_limits_fresh": True,
        "bedtime_enabled": True,
        "bedtime_enabled_today": True,
    }


def _plan(child: dict, intent: str | None, ha_bonus=frozenset()) -> list[dict]:
    intents = {"policies": {"bedtime": True}, "devices": {DEVICE: intent} if intent else {}, "values": {}}
    return [a for a in plan_strict_actions(child, set(STRICT_RULES), ha_bonus, intents, today=2) if a.get("device_id")]


def test_a_device_locked_from_ha_and_no_longer_listed_is_locked_again() -> None:
    actions = _plan(_child(), "lock")

    assert [a["action"] for a in actions] == [ACTION_LOCK_DEVICE]
    assert "no longer listed" in actions[0]["reason"]


def test_nothing_is_placed_or_lifted_without_a_row_and_without_a_lock_from_ha() -> None:
    # No row says nothing about a restriction being over: strict mode's own
    # lock is not lifted, and none is placed on a device HA did not lock
    assert _plan(_child(), DEVICE_INTENT_AUTO_LOCK) == []
    assert _plan(_child(), "unlock") == []
    assert _plan(_child(), None) == []


def test_a_bonus_given_from_ha_is_left_running() -> None:
    assert _plan(_child(), "lock", ha_bonus=frozenset({DEVICE})) == []


def test_a_device_that_takes_no_time_limits_has_no_row_to_miss() -> None:
    assert _plan(_child(capabilities=["capabilityRemoteRing"]), "lock") == []
    assert [a["action"] for a in _plan(_child(capabilities=["capabilityBedtime"]), "lock")] == [ACTION_LOCK_DEVICE]


def test_a_failed_read_is_still_no_ground_to_lock() -> None:
    child = _child()
    child["applied_limits_fresh"] = False
    assert _plan(child, "lock") == []


# --- reading appliedTimeLimits ------------------------------------------------


def _row(device_id: str | None, override: list | None) -> list:
    row: list = [None] * 34
    row[0] = override
    row[5] = ["CAEQAg", 2, 2, 180, "1788268036514", "1794179037473"]
    row[25] = device_id
    return row


def _client(response: list) -> FamilyLinkClient:
    class _Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def json(self):
            return response

    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=_Response())
    client._get_session = AsyncMock(return_value=session)
    return client


async def _read(monkeypatch, response: list) -> dict:
    monkeypatch.setattr(api_module.dt_util, "now", lambda: datetime(2026, 11, 17, 22, 5))  # a Tuesday
    monkeypatch.setattr(api_module, "_unreadable_logged", {})
    return await _client(response).async_get_applied_time_limits(account_id=CHILD)


async def test_an_override_that_names_no_device_does_not_drop_the_device(monkeypatch) -> None:
    # An override for the child as a whole: no device id where a lock or a bonus has one
    override = ["override-1", "1794949507218", 9, None, [1, [22, 0], [7, 0], "CAEQAg"]]

    result = await _read(monkeypatch, [None, [_row(DEVICE, override)]])

    assert DEVICE in result["devices"]
    assert result["device_lock_states"][DEVICE] is False


async def test_a_row_that_cannot_be_read_is_reported_with_what_google_sent(monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING)

    result = await _read(monkeypatch, [None, [_row(None, None), ["short", "row"]]])

    assert result["devices"] == {}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("no device id" in w for w in warnings)
    assert any("too short" in w and "short" in w for w in warnings)


async def test_an_answer_without_any_device_is_reported(monkeypatch, caplog) -> None:
    caplog.set_level(logging.WARNING)

    result = await _read(monkeypatch, [[None, "1794949507218"], []])

    assert result["devices"] == {}
    assert any("list no device" in r.getMessage() for r in caplog.records)
