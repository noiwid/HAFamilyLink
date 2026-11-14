"""Bedtime and school time window attributes: local time with its offset.

They used the container's time zone without saying so (a Docker install
without TZ showed a 15:00 Paris window as "13:00:00").
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from homeassistant.util import dt as dt_util

from custom_components.familylink.binary_sensor import BedtimeActiveBinarySensor, SchoolTimeActiveBinarySensor

CHILD, DEVICE = "child-1", "phone"


def _sensor(cls, window_key: str, start_ms: int, end_ms: int):
    coordinator = MagicMock()
    coordinator.data = {
        "children_data": [{"child_id": CHILD, "devices_time_data": {DEVICE: {window_key: {"start_ms": start_ms, "end_ms": end_ms}}}}]
    }
    return cls(coordinator, DEVICE, "Phone", {}, CHILD, "Alex")


def test_windows_are_local_times_with_their_offset() -> None:
    start = dt_util.start_of_local_day().replace(hour=21)
    end = start.replace(hour=23)
    ms = lambda moment: int(moment.timestamp() * 1000)  # noqa: E731

    bedtime = _sensor(BedtimeActiveBinarySensor, "bedtime_window", ms(start), ms(end)).extra_state_attributes
    school = _sensor(SchoolTimeActiveBinarySensor, "schooltime_window", ms(start), ms(end)).extra_state_attributes

    for value, expected in ((bedtime["bedtime_start"], start), (bedtime["bedtime_end"], end), (school["schooltime_start"], start)):
        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None and parsed == expected
