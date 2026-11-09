"""The morning of an overnight bedtime is read on yesterday's weekly row (#229).

Older-model accounts only list today's row in appliedTimeLimits. With
Saturday 21:00-11:00 and Sunday 20:00-17:00, Sunday 11:29 was read as
locked until 17:00 (Sunday's end), and Friday morning as free from 11:00.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.familylink.schedules import morning_window_from_yesterday

TZ = ZoneInfo("Europe/Paris")
SCHEDULE = [
    {"day": day, "enabled": True, "start": [20, 0], "end": [17, 0]} for day in (1, 2, 3, 4, 7)
] + [
    {"day": day, "enabled": True, "start": [21, 0], "end": [11, 0]} for day in (5, 6)
]


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _today_row_window(now: datetime) -> dict:
    """What the parser builds from today's row in the morning (start moved to yesterday)."""
    row = next(slot for slot in SCHEDULE if slot["day"] == now.isoweekday())
    start = now.replace(hour=row["start"][0], minute=0, second=0, microsecond=0)
    end = now.replace(hour=row["end"][0], minute=0, second=0, microsecond=0)
    return {"start_ms": _ms(start.replace(day=now.day - 1)), "end_ms": _ms(end)}


def test_sunday_after_11_is_free_until_tonight() -> None:
    now = datetime(2026, 11, 8, 11, 29, tzinfo=TZ)  # Sunday, Saturday night ended at 11:00
    window, active = morning_window_from_yesterday(_today_row_window(now), SCHEDULE, now)
    assert active is False
    assert window["start_ms"] == _ms(datetime(2026, 11, 8, 20, 0, tzinfo=TZ))


def test_sunday_before_11_is_last_night() -> None:
    now = datetime(2026, 11, 8, 10, 0, tzinfo=TZ)
    window, active = morning_window_from_yesterday(_today_row_window(now), SCHEDULE, now)
    assert active is True
    assert window == {
        "start_ms": _ms(datetime(2026, 11, 7, 21, 0, tzinfo=TZ)),
        "end_ms": _ms(datetime(2026, 11, 8, 11, 0, tzinfo=TZ)),
    }


def test_friday_morning_is_still_thursday_night_until_17() -> None:
    now = datetime(2026, 11, 6, 13, 0, tzinfo=TZ)  # Friday, Thursday night ends at 17:00
    window, active = morning_window_from_yesterday(_today_row_window(now), SCHEDULE, now)
    assert active is True
    assert window["end_ms"] == _ms(datetime(2026, 11, 6, 17, 0, tzinfo=TZ))


def test_unknown_schedule_keeps_the_reading() -> None:
    now = datetime(2026, 11, 8, 11, 29, tzinfo=TZ)
    assert morning_window_from_yesterday(_today_row_window(now), None, now) is None


async def test_parser_flags_only_the_morning(monkeypatch) -> None:
    """Live test 2026-11-09 12:10: the evening window was flagged too and moved to tomorrow."""
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.familylink.client import api as api_module
    from custom_components.familylink.client.api import FamilyLinkClient

    device = [None] * 34
    device[4] = ["CAEQAQ", 1, 2, [22, 0], [7, 0], "1", "2", "487088e7-38b4-4f18-a5fb-4aab64ba9d2f"]
    device[25] = "device-1"

    class _Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def json(self):
            return [None, [device]]

    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=_Response())
    client._get_session = AsyncMock(return_value=session)

    for now, flagged, start in (
        (datetime(2026, 11, 9, 6, 0, tzinfo=TZ), True, datetime(2026, 11, 8, 22, 0, tzinfo=TZ)),
        (datetime(2026, 11, 9, 12, 10, tzinfo=TZ), False, datetime(2026, 11, 9, 22, 0, tzinfo=TZ)),
    ):
        monkeypatch.setattr(api_module.dt_util, "now", lambda now=now: now)
        window = (await client.async_get_applied_time_limits(account_id="child-1"))["devices"]["device-1"]["bedtime_window"]
        assert bool(window.get("morning_from_today_row")) is flagged
        assert window["start_ms"] == _ms(start)
