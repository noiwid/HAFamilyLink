"""The reset bonus button cancels every bonus of the day on the device (discussion #142).

Bonuses stack on Google's side, the applied limits report only the most
recent one, and cancelling that single id left the others running: four
presses on +15 needed four presses on reset.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.familylink.client.api import FamilyLinkClient

ACCOUNT_ID = "115977971790729308369"
PHONE = "aannnppawiuhqf4xa3v2huxcxko66oux4zpxabjfgldq"
TABLET = "aannnppapwuzf2tgcvoq74hnz2chi4ln2hr27mcfxxba"
TODAY_MS = 1_790_000_000_000
YESTERDAY_MS = TODAY_MS - 86_400_000


def _override(uuid: str, created_ms: int, kind: int, device: str) -> list:
    return [uuid, str(created_ms), kind, device, "", None, None, None, "parent", None, None, None, None, [["900", 0]]]


def _time_limit_data() -> list:
    """Unwrapped timeLimit payload: the override block holds every override of the day."""
    return [
        [2, [["CAEQAQ", 1, 2, [22, 0], [7, 0], "1", "2"]], "1", "2", 1],
        [
            _override("bonus-1", TODAY_MS + 1_000, 10, PHONE),
            _override("bonus-2", TODAY_MS + 60_000, 10, PHONE),
            _override("bonus-tablet", TODAY_MS + 2_000, 6, TABLET),
            _override("bonus-old", YESTERDAY_MS, 10, PHONE),
            ["lock-1", str(TODAY_MS + 3_000), 1, PHONE],
            ["limit-1", str(TODAY_MS + 4_000), 8, PHONE, "", None, None, None, "parent", None, None, [2, 300, "CAEQBQ"]],
        ],
    ]


def test_parser_keeps_the_bonuses_of_the_device_posted_today_most_recent_first() -> None:
    matches = FamilyLinkClient._parse_bonus_overrides(_time_limit_data(), PHONE, TODAY_MS)

    assert [uuid for uuid, _ in matches] == ["bonus-2", "bonus-1"]


def test_parser_ignores_other_devices_and_other_override_kinds() -> None:
    matches = FamilyLinkClient._parse_bonus_overrides(_time_limit_data(), TABLET, TODAY_MS)

    assert [uuid for uuid, _ in matches] == ["bonus-tablet"]


async def test_cancel_all_deletes_each_bonus_of_the_day() -> None:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._async_fetch_time_limit_data = AsyncMock(return_value=_time_limit_data())
    client._async_delete_time_limit_override = AsyncMock(return_value=True)

    cancelled = await client.async_cancel_all_time_bonuses(PHONE, account_id=ACCOUNT_ID)

    assert cancelled == 2
    deleted = [c.args[1] for c in client._async_delete_time_limit_override.await_args_list]
    assert deleted == ["bonus-2", "bonus-1"]


async def test_cancel_all_reports_zero_when_the_override_block_cannot_be_read() -> None:
    """The button then falls back to the single id the applied limits report."""
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._async_fetch_time_limit_data = AsyncMock(return_value=None)
    client._async_delete_time_limit_override = AsyncMock(return_value=True)

    assert await client.async_cancel_all_time_bonuses(PHONE, account_id=ACCOUNT_ID) == 0
    client._async_delete_time_limit_override.assert_not_awaited()
