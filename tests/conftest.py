"""Shared fixtures for FamilyLink tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def make_app(title: str, package: str, *, hidden: bool = False, usage_limit: dict | None = None) -> dict:
    """Build a fake app entry matching the Family Link API shape."""
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


@pytest.fixture
def sample_apps() -> list[dict]:
    """Return a realistic mix of blocked / limited / free apps."""
    return [
        # 2 blocked apps
        make_app("BlockedGame", "com.blocked.game", hidden=True),
        make_app("BlockedChat", "com.blocked.chat", hidden=True),
        # 3 apps with time limits
        make_app("LimitedVideo", "com.limited.video",
                 usage_limit={"dailyUsageLimitMins": 60, "enabled": True}),
        make_app("LimitedSocial", "com.limited.social",
                 usage_limit={"dailyUsageLimitMins": 30, "enabled": True}),
        make_app("LimitedGame", "com.limited.game",
                 usage_limit={"dailyUsageLimitMins": 45, "enabled": False}),
        # 4 free / unrestricted apps
        make_app("FreeApp1", "com.free.app1"),
        make_app("FreeApp2", "com.free.app2"),
        make_app("FreeApp3", "com.free.app3"),
        make_app("FreeApp4", "com.free.app4"),
    ]


@pytest.fixture
def child_data(sample_apps) -> dict:
    """Return a single child_data dict as the coordinator would produce."""
    return {
        "child_id": "child_123",
        "child_name": "Alice",
        "apps": sample_apps,
        "devices": [],
        "screen_time": {},
    }


@pytest.fixture
def coordinator_data(child_data) -> dict:
    """Return coordinator.data with one child."""
    return {
        "children_data": [child_data],
        "supervised_children": [{"userId": "child_123"}],
    }


@pytest.fixture
def mock_coordinator(coordinator_data):
    """Return a lightweight mock coordinator with .data and .last_update_success."""
    coord = MagicMock()
    coord.data = coordinator_data
    coord.last_update_success = True
    return coord
