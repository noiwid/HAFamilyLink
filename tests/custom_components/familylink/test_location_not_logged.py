"""The child's position stays out of the log, debug included.

Logs get pasted in public issues. Flagged in the review for the HACS default
catalog.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink.client.api import FamilyLinkClient

CHILD_ID = "child-1"
LATITUDE = 48.123456
LONGITUDE = 2.654321
PLACE = "Secret School"
ADDRESS = "12 Hidden Street"
LOCATION = [
    [None, "1"],
    [
        CHILD_ID,
        1,
        [
            [LATITUDE, LONGITUDE],
            "1762300000000",
            "15",
            None,
            ["place-1", PLACE, ADDRESS],
            None,
            "device-1",
            None,
            [80, 1],
        ],
    ],
]


class _Response:
    status = 200

    def __init__(self, data: list) -> None:
        self._data = data

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def json(self) -> list:
        return self._data


def _client(data: list) -> FamilyLinkClient:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=_Response(data))
    client._get_session = AsyncMock(return_value=session)
    return client


def _assert_no_position(text: str) -> None:
    for secret in ("48.123", "2.654", PLACE, ADDRESS):
        assert secret not in text


async def test_location_is_returned_but_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    location = await _client(LOCATION).async_get_location(account_id=CHILD_ID)

    assert location["latitude"] == LATITUDE
    assert location["place_name"] == PLACE
    assert "Location for child" in caplog.text
    _assert_no_position(caplog.text)


async def test_unexpected_location_shape_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    assert await _client([[LATITUDE, LONGITUDE, PLACE, ADDRESS]]).async_get_location(account_id=CHILD_ID) is None

    assert "Unexpected location response structure" in caplog.text
    _assert_no_position(caplog.text)
