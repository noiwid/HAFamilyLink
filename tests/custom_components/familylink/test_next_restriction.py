"""The next-restriction state names a fixed time, not a countdown (#230).

"Bedtime in 25min" changed the state at every refresh, so the recorder
wrote one row a minute per device. The countdown is now the unrecorded
minutes_until attribute.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from custom_components.familylink import sensor as sensor_module
from custom_components.familylink.schedules import describe_time_at
from custom_components.familylink.sensor import NextRestrictionSensor

TZ = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 11, 9, 20, 35, tzinfo=TZ)  # a Monday
CHILD = "child-1"
DEVICE = "device-1"


def test_describe_time_at() -> None:
    assert describe_time_at(NOW.replace(hour=22, minute=0), NOW) == "at 22:00"
    assert describe_time_at(NOW + timedelta(days=1), NOW) == "tomorrow 20:35"
    assert describe_time_at(NOW + timedelta(days=3), NOW) == "Thu 20:35"


def _sensor(time_data: dict) -> NextRestrictionSensor:
    sensor = NextRestrictionSensor.__new__(NextRestrictionSensor)
    sensor.coordinator = MagicMock()
    sensor.coordinator.data = {"children_data": [{
        "child_id": CHILD,
        "devices_time_data": {DEVICE: time_data},
    }]}
    sensor._child_id = CHILD
    sensor._child_name = "Kid"
    sensor._device_id = DEVICE
    sensor._device_name = "Phone"
    return sensor


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def test_state_stays_the_same_while_the_countdown_moves(monkeypatch) -> None:
    bedtime = NOW.replace(hour=22, minute=0)
    sensor = _sensor({"bedtime_window": {"start_ms": _ms(bedtime), "end_ms": _ms(bedtime + timedelta(hours=9))}})

    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: NOW)
    first_state, first_attrs = sensor.native_value, sensor.extra_state_attributes
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: NOW + timedelta(minutes=1))
    second_state, second_attrs = sensor.native_value, sensor.extra_state_attributes

    assert first_state == second_state == "Bedtime at 22:00"
    assert (first_attrs["minutes_until"], second_attrs["minutes_until"]) == (85, 84)
    assert first_attrs["restriction_type"] == "bedtime"
    assert "minutes_until" in NextRestrictionSensor._unrecorded_attributes


def test_active_bedtime_names_its_end(monkeypatch) -> None:
    start, end = NOW - timedelta(hours=1), NOW.replace(hour=7, minute=0) + timedelta(days=1)
    sensor = _sensor({"bedtime_active": True, "bedtime_window": {"start_ms": _ms(start), "end_ms": _ms(end)}})
    monkeypatch.setattr(sensor_module.dt_util, "now", lambda: NOW)
    assert sensor.native_value == "Bedtime (ends tomorrow 07:00)"
