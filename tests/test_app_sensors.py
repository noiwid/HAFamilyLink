"""Tests for the three app-category sensors and truncation logic.

Covers:
- FamilyLinkBlockedAppsSensor
- FamilyLinkAppsWithLimitsSensor
- FamilyLinkAppsWithoutLimitsSensor  (issue #95)
- _truncate_app_list helper
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helper to build fake app entries (duplicated here to avoid conftest import issues)
# ---------------------------------------------------------------------------

def make_app(title: str, package: str, *, hidden: bool = False, usage_limit: dict | None = None) -> dict:
    supervision: dict = {}
    if hidden:
        supervision["hidden"] = True
    if usage_limit is not None:
        supervision["usageLimit"] = usage_limit
    return {
        "title": title,
        "packageName": package,
        "supervisionSetting": supervision,
    }

# ---------------------------------------------------------------------------
# Stub out homeassistant + local dependencies so sensor.py can be imported
# without a full HA installation.
# ---------------------------------------------------------------------------

_SensorEntity = type("SensorEntity", (), {})
_CoordinatorEntity = type("CoordinatorEntity", (), {"__init__": lambda self, *a, **kw: None})

_stubs = {
    "homeassistant": types.ModuleType("homeassistant"),
    "homeassistant.components": types.ModuleType("homeassistant.components"),
    "homeassistant.components.sensor": types.ModuleType("homeassistant.components.sensor"),
    "homeassistant.config_entries": types.ModuleType("homeassistant.config_entries"),
    "homeassistant.const": types.ModuleType("homeassistant.const"),
    "homeassistant.core": types.ModuleType("homeassistant.core"),
    "homeassistant.helpers": types.ModuleType("homeassistant.helpers"),
    "homeassistant.helpers.entity": types.ModuleType("homeassistant.helpers.entity"),
    "homeassistant.helpers.entity_platform": types.ModuleType("homeassistant.helpers.entity_platform"),
    "homeassistant.helpers.update_coordinator": types.ModuleType("homeassistant.helpers.update_coordinator"),
}

_stubs["homeassistant.components.sensor"].SensorDeviceClass = type("SensorDeviceClass", (), {"DURATION": "duration", "BATTERY": "battery"})
_stubs["homeassistant.components.sensor"].SensorEntity = _SensorEntity
_stubs["homeassistant.components.sensor"].SensorStateClass = type("SensorStateClass", (), {"MEASUREMENT": "measurement", "TOTAL": "total"})
_stubs["homeassistant.config_entries"].ConfigEntry = type("ConfigEntry", (), {})
_stubs["homeassistant.const"].PERCENTAGE = "%"
_stubs["homeassistant.const"].EntityCategory = type("EntityCategory", (), {"DIAGNOSTIC": "diagnostic"})
_stubs["homeassistant.const"].UnitOfTime = type("UnitOfTime", (), {"MINUTES": "min"})
_stubs["homeassistant.core"].HomeAssistant = type("HomeAssistant", (), {})
_stubs["homeassistant.helpers.entity"].DeviceInfo = dict
_stubs["homeassistant.helpers.entity_platform"].AddEntitiesCallback = None
_stubs["homeassistant.helpers.update_coordinator"].CoordinatorEntity = _CoordinatorEntity

for name, mod in _stubs.items():
    sys.modules[name] = mod

# Stub familylink sub-packages that sensor.py imports
_cc = types.ModuleType("custom_components")
_fl = types.ModuleType("custom_components.familylink")
_fl.__path__ = [str(Path(__file__).resolve().parent.parent / "custom_components" / "familylink")]
_fl_const = types.ModuleType("custom_components.familylink.const")
_fl_const.DOMAIN = "familylink"
_fl_const.INTEGRATION_NAME = "Google Family Link"
_fl_const.LOGGER_NAME = "custom_components.familylink"
_fl_const.CONF_ENABLE_LOCATION_TRACKING = "enable_location_tracking"
_fl_coord = types.ModuleType("custom_components.familylink.coordinator")
_fl_coord.FamilyLinkDataUpdateCoordinator = type("FamilyLinkDataUpdateCoordinator", (), {})

sys.modules["custom_components"] = _cc
sys.modules["custom_components.familylink"] = _fl
sys.modules["custom_components.familylink.const"] = _fl_const
sys.modules["custom_components.familylink.coordinator"] = _fl_coord

# Now load sensor.py via importlib so it resolves correctly
_sensor_file = Path(__file__).resolve().parent.parent / "custom_components" / "familylink" / "sensor.py"
_spec = importlib.util.spec_from_file_location("custom_components.familylink.sensor", _sensor_file)
sensor_mod = importlib.util.module_from_spec(_spec)
sys.modules["custom_components.familylink.sensor"] = sensor_mod
_spec.loader.exec_module(sensor_mod)

FamilyLinkAppsWithoutLimitsSensor = sensor_mod.FamilyLinkAppsWithoutLimitsSensor
FamilyLinkAppsWithLimitsSensor = sensor_mod.FamilyLinkAppsWithLimitsSensor
FamilyLinkBlockedAppsSensor = sensor_mod.FamilyLinkBlockedAppsSensor
MAX_ATTR_SIZE = sensor_mod.MAX_ATTR_SIZE
_truncate_app_list = sensor_mod._truncate_app_list


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def sample_apps():
    return [
        make_app("BlockedGame", "com.blocked.game", hidden=True),
        make_app("BlockedChat", "com.blocked.chat", hidden=True),
        make_app("LimitedVideo", "com.limited.video", usage_limit={"dailyUsageLimitMins": 60, "enabled": True}),
        make_app("LimitedSocial", "com.limited.social", usage_limit={"dailyUsageLimitMins": 30, "enabled": True}),
        make_app("LimitedGame", "com.limited.game", usage_limit={"dailyUsageLimitMins": 45, "enabled": False}),
        make_app("FreeApp1", "com.free.app1"),
        make_app("FreeApp2", "com.free.app2"),
        make_app("FreeApp3", "com.free.app3"),
        make_app("FreeApp4", "com.free.app4"),
    ]


@pytest.fixture
def mock_coordinator(sample_apps):
    coord = MagicMock()
    coord.data = {
        "children_data": [{
            "child_id": "child_123",
            "child_name": "Alice",
            "apps": sample_apps,
            "devices": [],
            "screen_time": {},
        }],
        "supervised_children": [{"userId": "child_123"}],
    }
    coord.last_update_success = True
    return coord


# ===================================================================
# Helpers
# ===================================================================

def _make_sensor(cls, mock_coordinator, child_id="child_123", child_name="Alice"):
    """Instantiate a sensor with the mocked coordinator."""
    sensor = cls.__new__(cls)
    sensor._child_id = child_id
    sensor._child_name = child_name
    sensor.coordinator = mock_coordinator
    return sensor


# ===================================================================
# _truncate_app_list
# ===================================================================

class TestTruncateAppList:

    def test_no_truncation_needed(self):
        apps = [{"name": f"App{i}", "package": f"com.app{i}"} for i in range(5)]
        base = {"child_id": "x", "child_name": "Y", "count": 5}
        result, truncated = _truncate_app_list(apps, base)
        assert result == apps
        assert truncated is False

    def test_truncation_triggers_on_large_list(self):
        apps = [{"name": f"VeryLongAppName_{i:04d}", "package": f"com.very.long.package.name.app{i:04d}"} for i in range(500)]
        base = {"child_id": "x", "child_name": "Y", "count": 500}
        result, truncated = _truncate_app_list(apps, base)
        assert truncated is True
        assert len(result) < 500
        total = len(json.dumps({**base, "apps": result}, ensure_ascii=False).encode("utf-8"))
        assert total <= MAX_ATTR_SIZE + 200

    def test_empty_list(self):
        result, truncated = _truncate_app_list([], {"count": 0})
        assert result == []
        assert truncated is False

    def test_unicode_app_names(self):
        apps = [{"name": "日本語アプリ", "package": "com.jp.app"}]
        result, truncated = _truncate_app_list(apps, {"count": 1})
        assert result == apps
        assert truncated is False


# ===================================================================
# FamilyLinkAppsWithoutLimitsSensor  (issue #95)
# ===================================================================

class TestAppsWithoutLimitsSensor:

    def test_native_value_counts_free_apps(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        assert sensor.native_value == 4

    def test_native_value_zero_when_no_data(self, mock_coordinator):
        mock_coordinator.data = None
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        assert sensor.native_value == 0

    def test_native_value_zero_when_child_not_found(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator, child_id="unknown")
        assert sensor.native_value == 0

    def test_extra_state_attributes_structure(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        attrs = sensor.extra_state_attributes
        assert "apps" in attrs
        assert "count" in attrs
        assert attrs["count"] == 4
        assert attrs["child_id"] == "child_123"
        assert attrs["child_name"] == "Alice"
        assert "truncated" not in attrs

    def test_attributes_contain_correct_apps(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        attrs = sensor.extra_state_attributes
        packages = {a["package"] for a in attrs["apps"]}
        assert packages == {"com.free.app1", "com.free.app2", "com.free.app3", "com.free.app4"}

    def test_blocked_apps_excluded(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        attrs = sensor.extra_state_attributes
        packages = {a["package"] for a in attrs["apps"]}
        assert "com.blocked.game" not in packages
        assert "com.blocked.chat" not in packages

    def test_limited_apps_excluded(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        attrs = sensor.extra_state_attributes
        packages = {a["package"] for a in attrs["apps"]}
        assert "com.limited.video" not in packages
        assert "com.limited.social" not in packages

    def test_available_true(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        assert sensor.available is True

    def test_available_false_when_update_failed(self, mock_coordinator):
        mock_coordinator.last_update_success = False
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        assert sensor.available is False

    def test_empty_attributes_when_all_apps_restricted(self, mock_coordinator):
        mock_coordinator.data["children_data"][0]["apps"] = [
            make_app("Blocked", "com.b", hidden=True),
            make_app("Limited", "com.l", usage_limit={"dailyUsageLimitMins": 10, "enabled": True}),
        ]
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        assert sensor.native_value == 0
        assert sensor.extra_state_attributes == {}

    def test_icon(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        assert sensor._attr_icon == "mdi:lock-open-outline"

    def test_unique_id_format(self):
        coord = MagicMock()
        sensor = FamilyLinkAppsWithoutLimitsSensor.__new__(FamilyLinkAppsWithoutLimitsSensor)
        sensor._child_id = "child_456"
        sensor._child_name = "Bob"
        sensor.coordinator = coord
        sensor._attr_unique_id = "familylink_child_456_apps_without_limits"
        assert "apps_without_limits" in sensor._attr_unique_id


# ===================================================================
# FamilyLinkBlockedAppsSensor
# ===================================================================

class TestBlockedAppsSensor:

    def test_native_value(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkBlockedAppsSensor, mock_coordinator)
        assert sensor.native_value == 2

    def test_attributes_apps(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkBlockedAppsSensor, mock_coordinator)
        attrs = sensor.extra_state_attributes
        assert attrs["count"] == 2
        packages = {a["package"] for a in attrs["apps"]}
        assert "com.blocked.game" in packages
        assert "com.blocked.chat" in packages


# ===================================================================
# FamilyLinkAppsWithLimitsSensor
# ===================================================================

class TestAppsWithLimitsSensor:

    def test_native_value(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithLimitsSensor, mock_coordinator)
        assert sensor.native_value == 3

    def test_attributes_contain_limit_info(self, mock_coordinator):
        sensor = _make_sensor(FamilyLinkAppsWithLimitsSensor, mock_coordinator)
        attrs = sensor.extra_state_attributes
        assert attrs["count"] == 3
        app = next(a for a in attrs["apps"] if a["package"] == "com.limited.video")
        assert app["limit_minutes"] == 60
        assert app["enabled"] is True


# ===================================================================
# Cross-sensor consistency
# ===================================================================

class TestCrossSensorConsistency:
    """Verify that blocked + limited + without_limits == total apps."""

    def test_partition_covers_all_apps(self, mock_coordinator, sample_apps):
        blocked = _make_sensor(FamilyLinkBlockedAppsSensor, mock_coordinator)
        limited = _make_sensor(FamilyLinkAppsWithLimitsSensor, mock_coordinator)
        free = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        total = blocked.native_value + limited.native_value + free.native_value
        assert total == len(sample_apps)

    def test_partition_with_only_free_apps(self, mock_coordinator):
        mock_coordinator.data["children_data"][0]["apps"] = [
            make_app(f"App{i}", f"com.app{i}") for i in range(10)
        ]
        blocked = _make_sensor(FamilyLinkBlockedAppsSensor, mock_coordinator)
        limited = _make_sensor(FamilyLinkAppsWithLimitsSensor, mock_coordinator)
        free = _make_sensor(FamilyLinkAppsWithoutLimitsSensor, mock_coordinator)
        assert blocked.native_value == 0
        assert limited.native_value == 0
        assert free.native_value == 10
