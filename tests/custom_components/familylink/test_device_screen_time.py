"""Tests for per-device daily screen time parsing and sensors."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTime

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN
from custom_components.familylink.sensor import (
    FamilyLinkDeviceDailyScreenTimeSensor,
)


async def test_async_get_daily_screen_time_per_device(hass):
    """Test that async_get_daily_screen_time breaks down usage by device."""
    client = FamilyLinkClient(hass, {})
    target_date = datetime(2026, 9, 19, 12, 0, 0)

    mock_data = {
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
        ],
    }

    result = await client.async_get_daily_screen_time("account-123", target_date, data=mock_data)

    assert result["total_seconds"] == 3000.0
    assert result["hours"] == 0
    assert result["minutes"] == 50
    assert "device_screen_time" in result
    assert "dev-phone" in result["device_screen_time"]
    assert "dev-tv" in result["device_screen_time"]

    phone_data = result["device_screen_time"]["dev-phone"]
    assert phone_data["name"] == "Pixel 9 Pro"
    assert phone_data["total_seconds"] == 1800.0
    assert phone_data["minutes"] == 30.0

    tv_data = result["device_screen_time"]["dev-tv"]
    assert tv_data["name"] == "Smart TV Pro"
    assert tv_data["total_seconds"] == 1200.0
    assert tv_data["minutes"] == 20.0

    app_usage = result["app_device_usage"]
    assert len(app_usage) == 2
    packages = {item["package"]: item["device"] for item in app_usage}
    assert packages["com.supercell.brawlstars"] == "Pixel 9 Pro"
    assert packages["cz.zupis.player"] == "Smart TV Pro"


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
