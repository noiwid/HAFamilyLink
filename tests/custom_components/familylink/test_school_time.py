"""School time start and finish: weekly slot lookup, write payloads and targeting."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.familylink import async_setup_services
from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN

ACCOUNT_ID = "115977971790729308369"
BEDTIME_RULE = "87ac8abb-ed2a-49aa-830f-15523956338b"
SCHOOL_RULE = "00b1cb45-7cfe-4053-9cb1-9c5849fff17e"
# Real slot ids: CAMQ... decodes to rule type 3 (school time), CAEQ... to 1 (bedtime)
SCHOOL_FRIDAY = "CAMQBSIkYjMzMzhhMWItZjA2Zi00Yzk2LTg2MTUtZGUwNTdmYTc3NDcz"
SCHOOL_MONDAY = "CAMQASIkYjMzMzhhMWItZjA2Zi00Yzk2LTg2MTUtZGUwNTdmYTc3NDcz"


def _time_limit_data(*, bedtime_friday_key: str = "CAEQBQ", with_friday_school: bool = True) -> list:
    """An unwrapped timeLimit payload: one flat window list plus the revisions."""
    windows = [
        [bedtime_friday_key, 5, 2, [20, 0], [7, 0], "1", "2", BEDTIME_RULE],
        [SCHOOL_MONDAY, 1, 2, [8, 0], [13, 0], "1", "2", SCHOOL_RULE],
    ]
    if with_friday_school:
        windows.append([SCHOOL_FRIDAY, 5, 2, [8, 0], [14, 30], "1", "2", SCHOOL_RULE])
    return [
        [2, windows, "1", "2", 1],
        [[["CAEQBQ", 5, 2, 120, "1", "2"]]],
        None,
        None,
        [1],
        [[BEDTIME_RULE, 1, 2, ["1", 0]], [SCHOOL_RULE, 2, 2, ["1", 0]]],
    ]


def test_finds_the_school_time_row_of_the_day() -> None:
    row = FamilyLinkClient._find_weekly_school_time_row(_time_limit_data(), 5)

    assert row is not None
    assert row[0] == SCHOOL_FRIDAY
    assert row[3:5] == [[8, 0], [14, 30]]


def test_bedtime_row_keyed_camq_is_never_taken_for_school_time() -> None:
    """Newer downtime model accounts key bedtime rows CAMQ* too (issue #151)."""
    data = _time_limit_data(bedtime_friday_key=SCHOOL_FRIDAY.replace("BS", "BT"), with_friday_school=False)

    assert FamilyLinkClient._find_weekly_school_time_row(data, 5) is None


def test_day_without_school_time_slot_returns_none() -> None:
    assert FamilyLinkClient._find_weekly_school_time_row(_time_limit_data(), 3) is None


class _Response:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def text(self) -> str:
        return ""


def _client(data: list | None) -> tuple[FamilyLinkClient, MagicMock]:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client._weekly_slot_cache = {}
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.post = MagicMock(return_value=_Response())
    client._get_session = AsyncMock(return_value=session)
    client._async_get_weekly_schedule_data = AsyncMock(return_value=data)
    client._async_list_schooltime_overrides_today = AsyncMock(return_value=["old-override"])
    client._async_delete_time_limit_override = AsyncMock(return_value=True)
    return client, session


async def test_weekly_write_targets_the_school_time_slot() -> None:
    client, session = _client(_time_limit_data())

    assert await client.async_set_school_time("08:00", "12:10", day=5, account_id=ACCOUNT_ID)

    url = session.post.call_args.args[0]
    kwargs = session.post.call_args.kwargs
    assert url.endswith(f"/people/{ACCOUNT_ID}/timeLimit:update")
    assert kwargs["params"] == {"$httpMethod": "PUT"}
    assert json.loads(kwargs["data"]) == [
        None,
        ACCOUNT_ID,
        [[None, None, None, [[SCHOOL_FRIDAY, [8, 0], [12, 10]]]], None, None, None, []],
        None,
        [1],
    ]


async def test_weekly_write_fails_without_a_slot_for_the_day() -> None:
    client, session = _client(_time_limit_data())

    assert not await client.async_set_school_time("08:00", "12:10", day=3, account_id=ACCOUNT_ID)
    session.post.assert_not_called()


@pytest.mark.parametrize(("start", "end"), [("12:10", "08:00"), ("08:00", "08:00"), ("25:00", "26:00")])
async def test_invalid_window_is_rejected_before_any_request(start, end) -> None:
    client, session = _client(_time_limit_data())

    assert not await client.async_set_school_time(start, end, day=5, account_id=ACCOUNT_ID)
    client._get_session.assert_not_called()


async def test_today_scope_replaces_todays_overrides_with_the_window() -> None:
    client, session = _client(_time_limit_data())
    friday = datetime(2026, 9, 25, 6, 0)

    with patch("custom_components.familylink.client.api.dt_util.now", return_value=friday):
        assert await client.async_set_school_time("08:00", "12:10", account_id=ACCOUNT_ID, scope="today")

    client._async_delete_time_limit_override.assert_awaited_once_with(ACCOUNT_ID, "old-override")
    url = session.post.call_args.args[0]
    payload = json.loads(session.post.call_args.kwargs["data"])
    assert url.endswith(f"/people/{ACCOUNT_ID}/timeLimitOverrides:batchCreate")
    assert payload[2][0][2] == 9
    assert payload[2][0][12] == [2, [8, 0], [12, 10], None, [5, SCHOOL_RULE]]


async def test_today_scope_refuses_another_day() -> None:
    client, session = _client(_time_limit_data())
    friday = datetime(2026, 9, 25, 6, 0)

    with patch("custom_components.familylink.client.api.dt_util.now", return_value=friday):
        assert not await client.async_set_school_time("08:00", "12:10", day=1, account_id=ACCOUNT_ID, scope="today")
    session.post.assert_not_called()


@pytest.fixture
async def services(hass, coordinator):
    coordinator.client.async_set_school_time.return_value = True
    await async_setup_services(hass, coordinator)
    return coordinator


def _child_switch(hass, child_id: str) -> str:
    """A child-level entity without a child_id attribute, attached to the child's device."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, child_id)}
    )
    reg = er.async_get(hass).async_get_or_create(
        "switch", DOMAIN, f"{child_id}_school_time", config_entry=entry, device_id=device.id
    )
    hass.states.async_set(reg.entity_id, "on", {"school_time_enabled_weekly": True})
    return reg.entity_id


async def test_service_resolves_the_child_from_the_entity_device(hass, services) -> None:
    entity_id = _child_switch(hass, ACCOUNT_ID)

    await hass.services.async_call(
        DOMAIN,
        "set_school_time",
        {"entity_id": entity_id, "start_time": "08:00:00", "end_time": "12:10:00", "day": "5"},
        blocking=True,
    )

    services.client.async_set_school_time.assert_awaited_once_with(
        start_time="08:00", end_time="12:10", day=5, account_id=ACCOUNT_ID, scope="weekly"
    )
    assert services.async_request_refresh.await_count == 1


async def test_existing_services_resolve_the_child_from_the_entity_device(hass, services) -> None:
    """Before, a child-level switch fell back to the FIRST child without a word."""
    entity_id = _child_switch(hass, ACCOUNT_ID)

    await hass.services.async_call(DOMAIN, "enable_school_time", {"entity_id": entity_id}, blocking=True)

    services.client.async_enable_school_time.assert_awaited_once_with(account_id=ACCOUNT_ID)


async def test_service_raises_when_google_rejects_the_window(hass, services) -> None:
    services.client.async_set_school_time.return_value = False

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "set_school_time",
            {"child_id": ACCOUNT_ID, "start_time": "08:00", "end_time": "12:10"},
            blocking=True,
        )
    assert services.async_request_refresh.await_count == 0
