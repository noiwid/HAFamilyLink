"""The bedtime, school time and daily limit sensors name their child and device even before Google sends time data."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.familylink.binary_sensor import (
    BedtimeActiveBinarySensor,
    DailyLimitReachedBinarySensor,
    SchoolTimeActiveBinarySensor,
)

CHILD, DEVICE = "child-1", "phone"


@pytest.mark.parametrize(
    "sensor_class", [BedtimeActiveBinarySensor, SchoolTimeActiveBinarySensor, DailyLimitReachedBinarySensor]
)
def test_attributes_name_the_child_and_device_without_time_data(sensor_class) -> None:
    coordinator = MagicMock()
    coordinator.data = {"children_data": [{"child_id": CHILD, "devices_time_data": {}}]}
    sensor = sensor_class(coordinator, DEVICE, "Phone", {}, CHILD, "Alex")

    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {
        "device_id": DEVICE,
        "device_name": "Phone",
        "child_id": CHILD,
        "child_name": "Alex",
    }
