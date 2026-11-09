"""Switching the daily limit off also removes the per-device quota overrides.

Seen live on 2026-11-09: the limit was switched off (app and HA agreed), yet
Google kept enforcing the 180 min quota override posted that morning and the
phone was blocked once it was used. The override list also held Saturday's
rows, which would have been the most recent ones again with today's gone.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from custom_components.familylink.client.api import FamilyLinkClient

ACCOUNT_ID = "123456789012345678901"
PHONE = "device-phone"
TABLET = "device-tablet"


def _quota(uuid: str, device: str, minutes: int, code: str) -> list:
    return [uuid, "1794179042000", 8, device, "", None, None, None, "parent", None, None, [2, minutes, code]]


def _time_limit_data() -> list:
    """Unwrapped timeLimit payload: limit switched off, weekly rows kept, overrides left behind."""
    return [
        [2, [["CAEQAQ", 1, 2, [22, 0], [7, 0], "1", "2"]], "1", "2", 1],
        [[1, [6, 0], [["CAEQAQ", 1, 2, 180, "1", "2"], ["CAEQBg", 6, 2, 360, "1", "2"]]]],
        [
            _quota("2e7f8c29-monday-phone", PHONE, 180, "CAEQAQ"),
            _quota("3b73cef3-monday-tablet", TABLET, 180, "CAEQAQ"),
            _quota("1d18c54f-saturday-phone", PHONE, 480, "CAEQBg"),
            ["lock-1", "1794179043000", 7, PHONE, "", None, None, None, "parent"],
            ["bonus-1", "1794179044000", 10, PHONE, "", None, None, None, "parent", None, None, None, None, [["3600"]]],
        ],
    ]


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_Response":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def text(self) -> str:
        return ""


def _client(put_status: int = 200, time_limit_data: list | None = None) -> FamilyLinkClient:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    session = MagicMock()
    session.put = MagicMock(return_value=_Response(put_status))
    client._get_session = AsyncMock(return_value=session)
    client._get_cookie_header = MagicMock(return_value="")
    client._async_fetch_time_limit_data = AsyncMock(return_value=time_limit_data)
    client._async_delete_time_limit_override = AsyncMock(return_value=True)
    return client


async def test_switching_off_deletes_every_quota_override_and_nothing_else() -> None:
    client = _client(time_limit_data=_time_limit_data())

    assert await client.async_disable_daily_limit(ACCOUNT_ID) is True

    deleted = [c.args[1] for c in client._async_delete_time_limit_override.await_args_list]
    assert deleted == ["2e7f8c29-monday-phone", "3b73cef3-monday-tablet", "1d18c54f-saturday-phone"]


async def test_a_weekly_quota_written_with_the_limit_off_leaves_it_off() -> None:
    """Checked live 2026-11-09: head flag 1 with a row stores the row, the limit stays off."""
    client = _client(time_limit_data=_time_limit_data())
    client._async_get_daily_limit_slot_id = AsyncMock(return_value="CAEQAQ")
    client._weekly_slot_cache = {}
    put = client._get_session.return_value.put

    assert await client.async_is_daily_limit_off(ACCOUNT_ID) is True
    assert await client.async_set_weekly_daily_limit(1, 120, ACCOUNT_ID, limit_on=False) is True
    assert json.loads(put.call_args.kwargs["data"])[2] == [None, [[1, None, None, [["CAEQAQ", 120]]]]]

    assert await client.async_set_weekly_daily_limit(1, 120, ACCOUNT_ID) is True
    assert json.loads(put.call_args.kwargs["data"])[2][1][0][0] == 2


async def test_an_unreadable_switch_counts_as_on() -> None:
    assert await _client(time_limit_data=None).async_is_daily_limit_off(ACCOUNT_ID) is False


async def test_a_refused_switch_off_leaves_the_overrides() -> None:
    client = _client(put_status=500, time_limit_data=_time_limit_data())

    assert await client.async_disable_daily_limit(ACCOUNT_ID) is False

    client._async_delete_time_limit_override.assert_not_awaited()


async def test_switch_off_still_succeeds_when_the_overrides_cannot_be_read() -> None:
    client = _client(time_limit_data=None)

    assert await client.async_disable_daily_limit(ACCOUNT_ID) is True

    client._async_delete_time_limit_override.assert_not_awaited()
