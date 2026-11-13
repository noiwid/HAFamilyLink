"""A failed family members read fails the refresh instead of returning no children.

A DNS timeout on that one request used to be logged as a warning, and the
refresh carried on with zero supervised children: at startup no entities were
created until a manual reload, and later refreshes blanked every child's data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from homeassistant.util import dt as dt_util

from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.exceptions import FamilyLinkException, SessionExpiredError


def _coordinator(members_error: Exception) -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator.client = MagicMock()
    coordinator.client.async_get_family_members = AsyncMock(side_effect=members_error)
    coordinator._last_known_data = None
    coordinator._last_known_at = dt_util.now()
    coordinator._auth_notification_sent = False
    coordinator._is_retrying_auth = False
    coordinator._async_enforce_strict_mode = AsyncMock()
    return coordinator


async def test_members_fetch_error_fails_the_fetch() -> None:
    coordinator = _coordinator(TimeoutError("Timeout while contacting DNS servers"))

    with pytest.raises(FamilyLinkException, match="Failed to fetch family members"):
        await coordinator._async_fetch_data()


async def test_refresh_keeps_last_known_data() -> None:
    coordinator = _coordinator(TimeoutError("Timeout while contacting DNS servers"))
    last_known = {"children_data": [{"child_id": "123", "child_name": "Child"}]}
    coordinator._last_known_data = last_known
    coordinator._last_known_at = dt_util.now()

    assert await coordinator._async_update_data() is last_known
    coordinator._async_enforce_strict_mode.assert_not_awaited()


async def test_first_refresh_raises_update_failed() -> None:
    coordinator = _coordinator(TimeoutError("Timeout while contacting DNS servers"))

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_session_expiry_still_propagates() -> None:
    coordinator = _coordinator(SessionExpiredError("expired"))

    with pytest.raises(SessionExpiredError):
        await coordinator._async_fetch_data()


def test_last_known_data_stands_in_only_while_recent() -> None:
    """A transient error is bridged; a long outage is not shown as live (yesterday's time, a bedtime long over)."""
    from datetime import timedelta

    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator._last_known_data = {"children_data": []}
    now = dt_util.now()
    coordinator._last_known_at = now - timedelta(minutes=5)
    assert coordinator._recent_data() is coordinator._last_known_data
    coordinator._last_known_at = now - timedelta(minutes=16)
    assert coordinator._recent_data() is None
    coordinator._last_known_at = dt_util.start_of_local_day() - timedelta(minutes=1)
    assert coordinator._recent_data() is None
