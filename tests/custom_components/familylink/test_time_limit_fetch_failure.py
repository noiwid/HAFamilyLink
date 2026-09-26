"""A failed time limit read raises, so the coordinator falls back to its cache (2026-09-26).

Returning a default "everything off, no schedule" result looked like a real
answer: the coordinator never used its cache, and strict mode read a single 503
as bedtime switched off and seven bedtime slots missing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.exceptions import NetworkError

ACCOUNT_ID = "115977971790729308369"


class _Response:
    def __init__(self, status: int, payload=None) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def text(self) -> str:
        return "{}"

    async def json(self):
        return self._payload


def _client(response: _Response) -> FamilyLinkClient:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    client._get_session = AsyncMock(return_value=session)
    return client


@pytest.mark.parametrize("status", [500, 503])
async def test_server_error_raises_instead_of_an_empty_result(status: int) -> None:
    client = _client(_Response(status))

    with pytest.raises(NetworkError):
        await client.async_get_time_limit(account_id=ACCOUNT_ID)


async def test_unexpected_response_shape_raises_too() -> None:
    client = _client(_Response(200, payload={"not": "a list"}))

    with pytest.raises(NetworkError):
        await client.async_get_time_limit(account_id=ACCOUNT_ID)
