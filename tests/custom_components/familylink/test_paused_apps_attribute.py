"""The apps with time limits sensor lists the apps pause_app paused (paused_apps)."""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.familylink.sensor import FamilyLinkAppsWithLimitsSensor

CHILD = "child-1"
CHROME = "com.android.chrome"
GAME = "com.example.game"
VIDEO = "com.example.video"


def _coordinator(apps: list, paused: dict | None = None):
    child = {"child_id": CHILD, "apps": apps}
    return SimpleNamespace(data={"children_data": [child]}, last_update_success=True, paused_apps=paused or {})


def _limit(package: str, minutes: int) -> dict:
    return {"packageName": package, "title": package, "supervisionSetting": {"usageLimit": {"dailyUsageLimitMins": minutes, "enabled": True}}}


def test_apps_with_limits_lists_the_apps_pause_app_paused() -> None:
    apps = [
        _limit(CHROME, 1),  # still at the pause limit
        _limit(GAME, 30),  # a parent changed it since the pause
        {"packageName": VIDEO, "supervisionSetting": {"alwaysAllowedAppInfo": {"alwaysAllowedState": "alwaysAllowedStateEnabled"}}},
    ]
    coordinator = _coordinator(apps, paused={CHILD: {CHROME: 45, GAME: -1, VIDEO: 20}, "child-2": {CHROME: 5}})
    sensor = FamilyLinkAppsWithLimitsSensor(coordinator, child_id=CHILD, child_name="Alex")

    assert sensor.extra_state_attributes["paused_apps"] == [
        {"package": CHROME, "pause_intact": True, "prior": 45},
        {"package": GAME, "pause_intact": False, "prior": -1},
        # Made unlimited by a parent: no longer in the app list, still reported
        {"package": VIDEO, "pause_intact": False, "prior": 20},
    ]


def test_apps_with_limits_has_an_empty_paused_list_without_pauses() -> None:
    sensor = FamilyLinkAppsWithLimitsSensor(_coordinator([_limit(CHROME, 45)]), child_id=CHILD, child_name="Alex")

    assert sensor.extra_state_attributes["paused_apps"] == []
