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
