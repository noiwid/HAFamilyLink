"""A transient read error keeps the last lock state and the last position.

A 503 on appliedTimeLimits restored the time data from the cache but not the
lock states, so every device read unlocked for one poll; a failed location
read cleared the position, so the tracker went to unknown and zone
automations fired.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.exceptions import NetworkError

CHILD_ID = "child-1"
DEVICE_ID = "device-1"
HOME = {"latitude": 1.0, "longitude": 2.0, "accuracy": 10}

LAST_KNOWN = {
    "children_data": [
        {
            "child_id": CHILD_ID,
            "devices": [{"id": DEVICE_ID, "name": "Phone", "locked": True}],
            "devices_time_data": {DEVICE_ID: {"used_minutes": 30}},
            "location": HOME,
        }
    ]
}


def _coordinator() -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    client = MagicMock()
    client.async_get_family_members = AsyncMock(return_value={"members": [{
        "userId": CHILD_ID,
        "profile": {"displayName": "Kid"},
        "memberSupervisionInfo": {"isSupervisedMember": True},
    }]})
    client.async_get_apps_and_usage = AsyncMock(return_value={
        "apps": [],
        "deviceInfo": [{"deviceId": DEVICE_ID, "displayInfo": {"friendlyName": "Phone"}}],
        "appUsageSessions": [],
    })
    client.async_get_time_limit = AsyncMock(return_value={})
    client.async_get_applied_time_limits = AsyncMock(side_effect=NetworkError("503"))
    client.async_get_daily_screen_time = AsyncMock(return_value=None)
    client.async_get_location = AsyncMock(side_effect=NetworkError("503"))
    client.async_get_contact_restriction = AsyncMock(return_value=None)
    coordinator.client = client
    coordinator._last_known_data = LAST_KNOWN
    coordinator._location_tracking_enabled = True
    coordinator._pending_lock_states = {}
    coordinator._pending_time_limit_states = {}
    coordinator._async_child_websites = AsyncMock(return_value=None)
    return coordinator


async def test_failed_reads_keep_the_lock_state_and_the_position() -> None:
    data = await _coordinator()._async_fetch_data()

    child = data["children_data"][0]
    assert [d["locked"] for d in child["devices"] if d["id"] == DEVICE_ID] == [True]
    assert child["location"] == HOME


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def text(self) -> str:
        return "{}"


def _client(status: int) -> FamilyLinkClient:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=_Response(status))
    client._get_session = AsyncMock(return_value=session)
    return client


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_location_server_error_raises(status: int) -> None:
    with pytest.raises(NetworkError):
        await _client(status).async_get_location(account_id=CHILD_ID)


@pytest.mark.parametrize("status", [403, 404])
async def test_lasting_location_refusal_is_no_position(status: int) -> None:
    """Sharing turned off is not frozen on the last zone: no position."""
    assert await _client(status).async_get_location(account_id=CHILD_ID) is None
