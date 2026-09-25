"""A device lock keeps the always allowed apps reachable (code 7) unless the option says otherwise (#175)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DEVICE_LOCK_ACTION, DEVICE_UNLOCK_ACTION

ACCOUNT_ID = "115977971790729308369"
DEVICE_ID = "aannnppapwuzf2tgcvoq74hnz2chi4ln2hr27mcfxxba"


class _Response:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def text(self) -> str:
        return ""

    async def json(self):
        return [[None, "1"], [["override-id", "1", 7, DEVICE_ID]]]


def _client(*, keeps_allowed_apps: bool = True) -> tuple[FamilyLinkClient, MagicMock]:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.lock_keeps_allowed_apps = keeps_allowed_apps
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.post = MagicMock(return_value=_Response())
    client._get_session = AsyncMock(return_value=session)
    return client, session


def _posted_override(session: MagicMock) -> list:
    payload = json.loads(session.post.call_args.kwargs["data"])
    assert payload[1] == ACCOUNT_ID
    return payload[2][0]


async def test_lock_keeps_the_allowed_apps_reachable_by_default() -> None:
    client, session = _client()

    assert await client.async_control_device(DEVICE_ID, DEVICE_LOCK_ACTION, child_id=ACCOUNT_ID)

    assert session.post.call_args.args[0].endswith(f"/people/{ACCOUNT_ID}/timeLimitOverrides:batchCreate")
    assert _posted_override(session) == [None, None, 7, DEVICE_ID]


async def test_plain_lock_when_the_option_is_off() -> None:
    client, session = _client(keeps_allowed_apps=False)

    assert await client.async_control_device(DEVICE_ID, DEVICE_LOCK_ACTION, child_id=ACCOUNT_ID)

    assert _posted_override(session) == [None, None, 1, DEVICE_ID]


@pytest.mark.parametrize("keeps_allowed_apps", [True, False])
async def test_unlock_is_always_code_4(keeps_allowed_apps: bool) -> None:
    client, session = _client(keeps_allowed_apps=keeps_allowed_apps)

    assert await client.async_control_device(DEVICE_ID, DEVICE_UNLOCK_ACTION, child_id=ACCOUNT_ID)

    assert _posted_override(session) == [None, None, 4, DEVICE_ID]
