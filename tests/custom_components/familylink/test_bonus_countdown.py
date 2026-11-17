"""A bonus counts down from the moment it was granted (#255).

Google ends a bonus at its creation time plus its duration. The applied limits
carry the duration and the creation time, not the time left: the integration
used to report the full duration until the override disappeared.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink.client import api as api_module
from custom_components.familylink.client.api import FamilyLinkClient

CHILD_ID = "child-1"
DEVICE = "device-a"
NOW_S = 1_794_000_000  # a Monday, 2026-11-09
MONDAY = datetime(2026, 11, 9, 3, 0)


def _override(created_s: float, minutes: int) -> list:
    """An Android bonus override: created time at [1], duration in seconds at [13][0][0]."""
    override: list = [None] * 14
    override[0] = "bonus-1"
    override[1] = str(int(created_s * 1000))
    override[2] = 10
    override[3] = DEVICE
    override[13] = [[str(minutes * 60), 0]]
    return override


def _client(created_s: float, minutes: int, daily_limit: int = 45) -> FamilyLinkClient:
    device: list = [None] * 34
    device[0] = _override(created_s, minutes)
    device[5] = ["CAEQAQ", 1, 2, daily_limit, "1788268036514", "1794179037473"]
    device[25] = DEVICE
    response = [None, [device]]

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


async def _read(monkeypatch, created_s: float, minutes: int, elapsed_s: float) -> dict:
    monkeypatch.setattr(api_module.dt_util, "now", lambda: MONDAY)
    monkeypatch.setattr(api_module.time, "time", lambda: created_s + elapsed_s)
    result = await _client(created_s, minutes).async_get_applied_time_limits(account_id=CHILD_ID)
    return result["devices"][DEVICE]


@pytest.mark.parametrize(
    ("elapsed_s", "expected"),
    [
        (0, 60),  # just granted
        (57 * 60, 3),  # the Family Link app showed 3 min left
        (57 * 60 + 40, 3),  # 2 min 20 s left rounds up: the bonus is still running
        (60 * 60 - 1, 1),  # one second left
        (60 * 60, 0),  # over
        (61 * 60, 0),  # Google keeps the override a minute more: no negative time
    ],
)
async def test_the_bonus_counts_down_from_its_creation(monkeypatch, elapsed_s, expected) -> None:
    device = await _read(monkeypatch, NOW_S, 60, elapsed_s)

    assert device["bonus_minutes"] == expected
    assert device["remaining_minutes"] == (expected if expected else max(0, 45 - device["used_minutes"]))
    assert device["bonus_granted_minutes"] == 60
    assert device["bonus_override_id"] == "bonus-1"  # still there to cancel


async def test_the_allowed_time_stays_the_granted_bonus_while_the_rest_falls(monkeypatch) -> None:
    device = await _read(monkeypatch, NOW_S, 90, 30 * 60)

    assert device["total_allowed_minutes"] == 90
    assert device["remaining_minutes"] == 60


async def test_the_sensors_read_the_countdown_with_the_daily_limit_on(monkeypatch) -> None:
    """From Google's answer to what Home Assistant shows: Active Bonus and Screen Time Remaining."""
    from custom_components.familylink.sensor import ActiveBonusSensor, ScreenTimeRemainingSensor

    device = await _read(monkeypatch, NOW_S, 60, 57 * 60)
    coordinator = MagicMock()
    coordinator.data = {"children_data": [{"child_id": CHILD_ID, "devices_time_data": {DEVICE: device}}]}
    args = (coordinator, CHILD_ID, "Alex", DEVICE, "Tablet")

    assert device["daily_limit_enabled"] is True
    assert ActiveBonusSensor(*args).native_value == 3
    assert ScreenTimeRemainingSensor(*args).native_value == 3
    assert ActiveBonusSensor(*args).extra_state_attributes["bonus_granted_minutes"] == 60
