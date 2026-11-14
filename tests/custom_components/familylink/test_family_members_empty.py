"""An empty family members answer does not blank children the last refresh had.

The read can succeed and still list no supervised child (no "members" field,
an empty list, or members without their supervision info). The refresh used
to carry on with zero children: every child's entities lost their data and
the cache was overwritten with nothing, so a later failed read had nothing
to fall back on either. Like a failed read (test_family_members_fetch_failure),
it now fails the refresh when the last good one had children.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.util import dt as dt_util

from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.exceptions import FamilyLinkException

LAST_KNOWN = {"children_data": [{"child_id": "123", "child_name": "Child"}]}

EMPTY_ANSWERS = [
    pytest.param({}, id="no-members-field"),
    pytest.param({"members": []}, id="empty-list"),
    pytest.param({"members": [{"userId": "456"}]}, id="no-supervision-info"),
    pytest.param(
        {"members": [{"userId": "456", "memberSupervisionInfo": {"isSupervisedMember": False}}]},
        id="parents-only",
    ),
]


def _coordinator(members: dict, last_known: dict | None) -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator.client = MagicMock()
    coordinator.client.async_get_family_members = AsyncMock(return_value=members)
    coordinator._last_known_data = last_known
    coordinator._last_known_at = dt_util.now()
    coordinator._auth_notification_sent = False
    coordinator._is_retrying_auth = False
    coordinator._async_enforce_strict_mode = AsyncMock()
    return coordinator


@pytest.mark.parametrize("members", EMPTY_ANSWERS)
async def test_empty_answer_after_children_fails_the_fetch(members) -> None:
    coordinator = _coordinator(members, LAST_KNOWN)

    with pytest.raises(FamilyLinkException, match="no supervised children"):
        await coordinator._async_fetch_data()


@pytest.mark.parametrize("members", EMPTY_ANSWERS)
async def test_refresh_keeps_last_known_data(members) -> None:
    coordinator = _coordinator(members, LAST_KNOWN)

    assert await coordinator._async_update_data() is LAST_KNOWN
    assert coordinator._last_known_data is LAST_KNOWN
    coordinator._async_enforce_strict_mode.assert_not_awaited()


async def test_first_refresh_without_children_still_succeeds() -> None:
    """Nothing to keep yet: an account without supervised children sets up as before."""
    coordinator = _coordinator({"members": []}, None)

    result = await coordinator._async_update_data()

    assert result["children_data"] == []
    assert coordinator._last_known_data is result


async def test_account_without_children_keeps_refreshing() -> None:
    """A cache that never had children does not turn every refresh into a failure."""
    coordinator = _coordinator({"members": []}, {"children_data": []})

    result = await coordinator._async_update_data()

    assert result["children_data"] == []
