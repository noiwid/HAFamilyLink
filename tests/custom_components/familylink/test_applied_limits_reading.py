"""Reading appliedTimeLimits: what strict mode relies on (2026-11-09).

The app's "Unlock" during bedtime writes lock code 3, which was read as no
override: the phone stayed free from 02:48 to 02:52 and strict mode never
saw it. A device listed without today's daily-limit row was read as "limit
off", and strict mode switched a limit that was on back on every 97 s.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from custom_components.familylink.client import api as api_module
from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator

CHILD_ID = "child-1"
UNLOCKED = "device-a"
NO_ROW = "device-b"


def _device(device_id: str, override: list | None, rows: dict[int, list]) -> list:
    data: list = [None] * 34
    data[0] = override
    data[25] = device_id
    for index, row in rows.items():
        data[index] = row
    return data


RESPONSE = [None, [
    _device(
        UNLOCKED,
        ["cff6afec-10e9-44f6-8d64-7e5ee2a1c7a2", "1794189749879", 3, UNLOCKED, "", None, ["1", "CAEQBw"], None, "1"],
        {5: ["CAEQAQ", 1, 2, 180, "1788268036514", "1794179037473"]},
    ),
    _device(NO_ROW, None, {}),
]]


class _Response:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def json(self):
        return RESPONSE


def _client() -> FamilyLinkClient:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=_Response())
    client._get_session = AsyncMock(return_value=session)
    return client


async def test_app_unlock_and_missing_limit_row(monkeypatch) -> None:
    monkeypatch.setattr(api_module.dt_util, "now", lambda: datetime(2026, 11, 9, 3, 0))  # a Monday

    result = await _client().async_get_applied_time_limits(account_id=CHILD_ID)

    unlocked, no_row = result["devices"][UNLOCKED], result["devices"][NO_ROW]
    assert unlocked["lock_override"] == 3
    assert result["device_lock_states"][UNLOCKED] is False
    assert unlocked["daily_limit_enabled"] is True
    assert no_row["daily_limit_enabled"] is None
    # Who created the override: told in the strict mode notification
    assert unlocked["override_by"] == "1"
    assert no_row["override_by"] is None


async def test_child_limit_is_unknown_when_no_device_reports_it() -> None:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    client = MagicMock()
    client.async_get_family_members = AsyncMock(return_value={"members": [{
        "userId": CHILD_ID,
        "profile": {"displayName": "Kid"},
        "memberSupervisionInfo": {"isSupervisedMember": True},
    }]})
    client.async_get_apps_and_usage = AsyncMock(return_value={
        "apps": [],
        "deviceInfo": [{"deviceId": NO_ROW, "displayInfo": {"friendlyName": "Tablet"}}],
        "appUsageSessions": [],
    })
    client.async_get_time_limit = AsyncMock(return_value={})
    client.async_get_applied_time_limits = AsyncMock(return_value={
        "device_lock_states": {NO_ROW: False},
        "devices": {NO_ROW: {"daily_limit_enabled": None, "lock_override": None}},
        "bedtime_enabled_today": False,
        "schooltime_enabled_today": False,
    })
    client.async_get_daily_screen_time = AsyncMock(return_value=None)
    client.async_get_location = AsyncMock(return_value=None)
    client.async_get_contact_restriction = AsyncMock(return_value=None)
    coordinator.client = client
    coordinator._last_known_data = None
    coordinator._location_tracking_enabled = False
    coordinator._pending_lock_states = {}
    coordinator._pending_time_limit_states = {}
    coordinator._async_child_websites = AsyncMock(return_value=None)
    coordinator._async_child_play_settings = AsyncMock(return_value=None)

    data = await coordinator._async_fetch_data()

    assert data["children_data"][0]["daily_limit_enabled"] is None

    # The app's switch wins over today's rows (an override keeps a row on)
    client.async_get_time_limit = AsyncMock(return_value={"daily_limit_enabled": False})
    client.async_get_applied_time_limits.return_value["devices"][NO_ROW]["daily_limit_enabled"] = True
    data = await coordinator._async_fetch_data()
    assert data["children_data"][0]["daily_limit_enabled"] is False


def _time_limit_client(switch_flag: int) -> FamilyLinkClient:
    """timeLimit as read on 2026-11-09: switch off in the app, Monday row still 180 min on."""
    rows = [["CAEQAQ", 1, 2, 180, "1", "2"], ["CAEQAg", 2, 2, 180, "1", "2"]]
    body = [[None, "1"], [[2, [], "1", "1", 1], [[switch_flag, [6, 0], rows, "1", "1"]]]]

    class _TimeLimitResponse(_Response):
        async def json(self):
            return body

    client = _client()
    client._get_session.return_value.get = MagicMock(return_value=_TimeLimitResponse())
    return client


async def test_the_app_daily_limit_switch_is_read(monkeypatch) -> None:
    monkeypatch.setattr(api_module.dt_util, "now", lambda: datetime(2026, 11, 9, 11, 0))
    assert (await _time_limit_client(1).async_get_time_limit(account_id=CHILD_ID))["daily_limit_enabled"] is False
    assert (await _time_limit_client(2).async_get_time_limit(account_id=CHILD_ID))["daily_limit_enabled"] is True
