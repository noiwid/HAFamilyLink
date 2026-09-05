"""Fixtures for mocked Home Assistant integration tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading integrations from custom_components."""
    yield


@pytest.fixture
def coordinator():
    """Return a coordinator whose API surface is entirely mocked."""
    client = AsyncMock()
    for method_name in (
        "async_add_time_bonus",
        "async_block_app",
        "async_disable_bedtime",
        "async_disable_daily_limit",
        "async_disable_school_time",
        "async_enable_bedtime",
        "async_enable_daily_limit",
        "async_enable_school_time",
        "async_ring_device",
        "async_set_app_daily_limit",
        "async_set_bedtime",
        "async_set_daily_limit",
        "async_unblock_app",
    ):
        getattr(client, method_name).return_value = True
    client.async_block_device_for_school.return_value = {
        "blocked_count": 1,
        "unblocked_count": 0,
        "failed_count": 0,
    }
    client.async_unblock_all_apps.return_value = {
        "unblocked_count": 1,
        "failed_count": 0,
    }
    client.async_get_location.return_value = {
        "latitude": 12.345678,
        "longitude": 98.765432,
    }
    return SimpleNamespace(
        client=client,
        data={"children_data": []},
        async_request_refresh=AsyncMock(),
    )
