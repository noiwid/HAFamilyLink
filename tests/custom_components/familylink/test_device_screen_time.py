"""Tests for per-device daily screen time parsing and sensors."""

from __future__ import annotations

from datetime import datetime
import logging
from types import SimpleNamespace

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTime

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN
from custom_components.familylink.sensor import (
    FamilyLinkDeviceDailyScreenTimeSensor,
    FamilyLinkScreenTimeSensor,
)


TARGET_DATE = datetime(2026, 9, 19, 12, 0, 0)


def _usage_data() -> dict:
    """Apps and usage payload: one app per device plus one app used on both."""
    return {
        "deviceInfo": [
            {
                "deviceId": "dev-phone",
                "displayInfo": {"friendlyName": "Pixel 9 Pro"},
            },
            {
                "deviceId": "dev-tv",
                "displayInfo": {"friendlyName": "Smart TV Pro"},
            },
        ],
        "apps": [
            {
                "packageName": "com.supercell.brawlstars",
                "title": "Brawl Stars",
                "deviceIds": ["dev-phone"],
            },
            {
                "packageName": "cz.zupis.player",
                "title": "zupisPlayer",
                "deviceIds": ["dev-tv"],
            },
            {
                "packageName": "com.google.android.youtube",
                "title": "YouTube",
                "deviceIds": ["dev-phone", "dev-tv"],
            },
        ],
        "appUsageSessions": [
            {
                "date": {"year": 2026, "month": 9, "day": 19},
                "usage": "1800s",
                "deviceMudId": "dev-phone",
                "appId": {"androidAppPackageName": "com.supercell.brawlstars"},
            },
            {
                "date": {"year": 2026, "month": 9, "day": 19},
                "usage": "1200s",
                "deviceMudId": "dev-tv",
                "appId": {"androidAppPackageName": "cz.zupis.player"},
            },
            {
                "date": {"year": 2026, "month": 9, "day": 19},
                "usage": "600s",
                "deviceMudId": "dev-phone",
                "appId": {"androidAppPackageName": "com.google.android.youtube"},
            },
            {
                "date": {"year": 2026, "month": 9, "day": 19},
                "usage": "300s",
                "deviceMudId": "dev-tv",
                "appId": {"androidAppPackageName": "com.google.android.youtube"},
            },
        ],
    }


async def test_async_get_daily_screen_time_per_device(hass):
    """Test that async_get_daily_screen_time breaks down usage by device."""
    client = FamilyLinkClient(hass, {})

    result = await client.async_get_daily_screen_time("account-123", TARGET_DATE, data=_usage_data())

    assert result["total_seconds"] == 3900.0
    assert result["hours"] == 1
    assert result["minutes"] == 5
    # The child-level breakdown stays one entry per app, whatever the device count.
    assert result["app_breakdown"] == {
        "com.supercell.brawlstars": 1800.0,
        "cz.zupis.player": 1200.0,
        "com.google.android.youtube": 900.0,
    }
    assert set(result["device_screen_time"]) == {"dev-phone", "dev-tv"}

    phone_data = result["device_screen_time"]["dev-phone"]
    assert phone_data["name"] == "Pixel 9 Pro"
    assert phone_data["total_seconds"] == 2400.0
    assert phone_data["minutes"] == 40.0
    assert phone_data["app_breakdown"]["com.google.android.youtube"] == 600.0

    tv_data = result["device_screen_time"]["dev-tv"]
    assert tv_data["name"] == "Smart TV Pro"
    assert tv_data["total_seconds"] == 1500.0
    assert tv_data["minutes"] == 25.0

    app_usage = result["app_device_usage"]
    assert len(app_usage) == 4
    pairs = {(item["package"], item["device"]): item["seconds"] for item in app_usage}
    assert pairs[("com.supercell.brawlstars", "Pixel 9 Pro")] == 1800.0
    assert pairs[("cz.zupis.player", "Smart TV Pro")] == 1200.0
    assert pairs[("com.google.android.youtube", "Pixel 9 Pro")] == 600.0
    assert pairs[("com.google.android.youtube", "Smart TV Pro")] == 300.0


async def test_async_get_daily_screen_time_counts_unattributed_sessions(hass, caplog):
    """Sessions without a device id land in the unknown bucket and are counted in the log."""
    client = FamilyLinkClient(hass, {})
    data = _usage_data()
    for session in data["appUsageSessions"]:
        session.pop("deviceMudId")
    # No single-device fallback for the app installed on both devices.
    data["apps"] = [app for app in data["apps"] if app["packageName"] == "com.google.android.youtube"]

    with caplog.at_level(logging.DEBUG, logger="custom_components.familylink.client.api"):
        result = await client.async_get_daily_screen_time("account-123", TARGET_DATE, data=data)

    unknown = result["device_screen_time"]["unknown"]
    assert unknown["name"] == "Unknown Device"
    assert unknown["total_seconds"] == 3900.0
    assert "4 app usage session(s) for 2026-09-19 could not be attributed" in caplog.text


def _coordinator(children_data: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        data={"children_data": children_data},
        child_device_ids={"child-1": "hub-device-1"},
        last_update_success=True,
    )


def test_child_screen_time_sensor_keeps_apps_shape_and_adds_by_device():
    """The child sensor's `apps` stays one row per app; devices only appear in `by_device`."""
    coordinator = _coordinator([
        {
            "child_id": "child-1",
            "child_name": "Test Child",
            "apps": [
                {"packageName": "com.game", "title": "Game"},
                {"packageName": "com.video", "title": "Video"},
            ],
            "screen_time": {
                "total_seconds": 2400.0,
                "formatted": "00:40:00",
                "hours": 0,
                "minutes": 40,
                "seconds": 0,
                "app_breakdown": {"com.game": 1800.0, "com.video": 600.0},
                "device_screen_time": {
                    "dev-phone": {
                        "name": "Pixel 9 Pro",
                        "total_seconds": 2100.0,
                        "formatted": "00:35:00",
                        "minutes": 35.0,
                        "hours": 0,
                        "app_breakdown": {"com.game": 1800.0, "com.video": 300.0},
                    },
                    "dev-tv": {
                        "name": "Smart TV Pro",
                        "total_seconds": 300.0,
                        "formatted": "00:05:00",
                        "minutes": 5.0,
                        "hours": 0,
                        "app_breakdown": {"com.video": 300.0},
                    },
                },
                "app_device_usage": [
                    {"package": "com.game", "device_id": "dev-phone", "device": "Pixel 9 Pro", "seconds": 1800.0},
                    {"package": "com.video", "device_id": "dev-phone", "device": "Pixel 9 Pro", "seconds": 300.0},
                    {"package": "com.video", "device_id": "dev-tv", "device": "Smart TV Pro", "seconds": 300.0},
                ],
            },
        }
    ])

    sensor = FamilyLinkScreenTimeSensor(coordinator, "total", child_id="child-1", child_name="Test Child")
    attrs = sensor.extra_state_attributes

    # com.video runs on both devices but is listed once, with the pre-PR keys only.
    assert [app["package"] for app in attrs["apps"]] == ["com.game", "com.video"]
    assert attrs["apps"][1] == {"name": "Video", "package": "com.video", "time": "00:10:00", "minutes": 10.0}
    assert attrs["by_device"] == {
        "dev-phone": {"name": "Pixel 9 Pro", "minutes": 35.0, "seconds": 2100.0, "formatted": "00:35:00"},
        "dev-tv": {"name": "Smart TV Pro", "minutes": 5.0, "seconds": 300.0, "formatted": "00:05:00"},
    }


def test_device_daily_screen_time_sensor_unknown_when_device_missing():
    """A device absent from the data reads as unknown, not as zero."""
    coordinator = _coordinator([
        {
            "child_id": "child-1",
            "child_name": "Test Child",
            "apps": [],
            "screen_time": {
                "device_screen_time": {
                    # Same friendly name, different id: must not be picked up by name.
                    "dev-other": {"name": "Pixel 9 Pro", "total_seconds": 600.0, "minutes": 10.0},
                }
            },
        }
    ])

    sensor = FamilyLinkDeviceDailyScreenTimeSensor(
        coordinator,
        child_id="child-1",
        child_name="Test Child",
        device_id="dev-phone",
        device_name="Pixel 9 Pro",
    )

    assert sensor.native_value is None
    assert sensor.available is True
    assert sensor.extra_state_attributes == {
        "child_id": "child-1",
        "child_name": "Test Child",
        "device_id": "dev-phone",
        "device_name": "Pixel 9 Pro",
    }


def test_device_daily_screen_time_sensor():
    """Test FamilyLinkDeviceDailyScreenTimeSensor initialization and attributes."""
    child_id = "child-1"
    device_id = "dev-phone"
    device_name = "Pixel 9 Pro"

    coordinator = SimpleNamespace(
        data={
            "children_data": [
                {
                    "child_id": child_id,
                    "child_name": "Test Child",
                    "apps": [
                        {"packageName": "com.game", "title": "Game"},
                    ],
                    "screen_time": {
                        "device_screen_time": {
                            device_id: {
                                "name": device_name,
                                "total_seconds": 1800.0,
                                "formatted": "00:30:00",
                                "minutes": 30.0,
                                "hours": 0,
                                "app_breakdown": {"com.game": 1800.0},
                            }
                        }
                    },
                }
            ]
        },
        child_device_ids={child_id: "hub-device-1"},
    )

    sensor = FamilyLinkDeviceDailyScreenTimeSensor(
        coordinator,
        child_id=child_id,
        child_name="Test Child",
        device_id=device_id,
        device_name=device_name,
    )

    assert sensor.unique_id == f"{DOMAIN}_{child_id}_{device_id}_daily_screen_time"
    assert sensor.name == f"{device_name} Daily Screen Time"
    assert sensor.native_value == 30.0
    assert sensor.native_unit_of_measurement == UnitOfTime.MINUTES
    assert sensor.device_class == SensorDeviceClass.DURATION
    assert sensor.state_class == SensorStateClass.TOTAL

    attrs = sensor.extra_state_attributes
    assert attrs["device_id"] == device_id
    assert attrs["device_name"] == device_name
    assert attrs["minutes"] == 30.0
    assert len(attrs["apps"]) == 1
    assert attrs["apps"][0]["name"] == "Game"
    assert attrs["apps"][0]["minutes"] == 30.0
