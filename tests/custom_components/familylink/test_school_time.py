"""School time start and finish: weekly slot lookup, write payloads and targeting."""

from __future__ import annotations

import json
from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.familylink import async_setup_services
from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN
from custom_components.familylink.time import FamilyLinkSchoolTimeTime

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


# A school day with a break: Google stores two slots on the same day (#190)
SCHOOL_TUESDAY_MORNING = "CAMQAiIkYmI1YTI4N2YtMTM3NC00N2FhLTgzZjQtZTA5NDg4NjhhYmMw"
SCHOOL_TUESDAY_AFTERNOON = "CAMQAiIkMWUyYWVmZWYtZWJkZi00ODExLTk2ODctMWZhNmUwNjUwZTYy"


def _time_limit_data_with_break() -> list:
    data = _time_limit_data()
    # The afternoon slot comes first, as Google may list it
    data[0][1].insert(1, [SCHOOL_TUESDAY_AFTERNOON, 2, 2, [14, 0], [15, 0], "1", "2", SCHOOL_RULE])
    data[0][1].append([SCHOOL_TUESDAY_MORNING, 2, 2, [8, 0], [13, 0], "1", "2", SCHOOL_RULE])
    return data


def test_a_slot_id_picks_the_row_of_a_day_with_a_break() -> None:
    data = _time_limit_data_with_break()

    first = FamilyLinkClient._find_weekly_school_time_row(data, 2)
    morning = FamilyLinkClient._find_weekly_school_time_row(data, 2, SCHOOL_TUESDAY_MORNING)

    assert first[0] == SCHOOL_TUESDAY_AFTERNOON
    assert morning[0] == SCHOOL_TUESDAY_MORNING and morning[3:5] == [[8, 0], [13, 0]]
    assert FamilyLinkClient._find_weekly_school_time_row(data, 2, "CAMQAiIkbm90LXRoZXJl") is None


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


async def test_weekly_write_names_the_slot_of_a_day_with_a_break() -> None:
    client, session = _client(_time_limit_data_with_break())

    assert await client.async_set_school_time(
        "08:15", "13:00", day=2, account_id=ACCOUNT_ID, slot_id=SCHOOL_TUESDAY_MORNING
    )

    payload = json.loads(session.post.call_args.kwargs["data"])
    assert payload[2][0][3] == [[SCHOOL_TUESDAY_MORNING, [8, 15], [13, 0]]]


def _school_time_entity(schedule: list[dict], day: int, bound: str, client=None) -> FamilyLinkSchoolTimeTime:
    coordinator = SimpleNamespace(
        client=client,
        data={"children_data": [{"child_id": ACCOUNT_ID, "school_time_schedule": schedule}]},
        async_request_refresh=AsyncMock(),
        last_update_success=True,
    )
    return FamilyLinkSchoolTimeTime(coordinator, ACCOUNT_ID, "Kid", day, bound)


def _slot(day: int, start: list, end: list, slot_id: str, enabled: bool = True) -> dict:
    return {"day": day, "day_name": "x", "enabled": enabled, "start": start, "end": end,
            "state_flag": 2 if enabled else 1, "slot_id": slot_id}


BREAK_SCHEDULE = [
    _slot(2, [14, 0], [15, 0], SCHOOL_TUESDAY_AFTERNOON),
    _slot(2, [8, 0], [13, 0], SCHOOL_TUESDAY_MORNING),
    _slot(6, [8, 0], [15, 0], "CAMQBg", enabled=False),
]


def test_entities_cover_the_whole_school_day_around_a_break() -> None:
    """Issue #190: the first row met gave Tuesday 14:00-15:00 and Monday 08:00-13:00."""
    start = _school_time_entity(BREAK_SCHEDULE, 2, "start")
    end = _school_time_entity(BREAK_SCHEDULE, 2, "end")

    assert start.native_value == time(8, 0)
    assert end.native_value == time(15, 0)
    assert start.extra_state_attributes["windows"] == ["08:00-13:00", "14:00-15:00"]
    assert start.available


def test_a_day_whose_slots_are_disabled_reads_unknown() -> None:
    entity = _school_time_entity(BREAK_SCHEDULE, 6, "start")

    assert entity.available
    assert entity.native_value is None
    assert entity.extra_state_attributes["enabled"] is False
    assert entity.extra_state_attributes["windows"] == []


def test_a_day_without_any_slot_is_unavailable() -> None:
    assert not _school_time_entity(BREAK_SCHEDULE, 3, "start").available


async def test_setting_the_bounds_keeps_the_break() -> None:
    client = SimpleNamespace(async_set_school_time=AsyncMock(return_value=True))

    await _school_time_entity(BREAK_SCHEDULE, 2, "start", client).async_set_value(time(8, 30))
    await _school_time_entity(BREAK_SCHEDULE, 2, "end", client).async_set_value(time(15, 30))

    first, second = client.async_set_school_time.await_args_list
    assert first.args[:2] == ("08:30", "13:00") and first.kwargs["slot_id"] == SCHOOL_TUESDAY_MORNING
    assert second.args[:2] == ("14:00", "15:30") and second.kwargs["slot_id"] == SCHOOL_TUESDAY_AFTERNOON


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
    coordinator.client.async_set_school_time_windows.return_value = True
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


# --- every window of a day with a break (Watapana's request) ---------------


def test_finds_every_school_time_row_of_a_day_earliest_first() -> None:
    rows = FamilyLinkClient._find_weekly_school_time_rows(_time_limit_data_with_break(), 2)

    assert [row[0] for row in rows] == [SCHOOL_TUESDAY_MORNING, SCHOOL_TUESDAY_AFTERNOON]
    assert [row[0] for row in FamilyLinkClient._find_weekly_school_time_rows(_time_limit_data(), 5)] == [SCHOOL_FRIDAY]
    assert FamilyLinkClient._find_weekly_school_time_rows(_time_limit_data(), 3) == []


async def test_windows_write_rewrites_each_slot_of_the_day_in_order() -> None:
    client, session = _client(_time_limit_data_with_break())

    assert await client.async_set_school_time_windows(
        [("08:30", "12:00"), ("13:30", "15:30")], day=2, account_id=ACCOUNT_ID
    )

    payloads = [json.loads(call.kwargs["data"]) for call in session.post.call_args_list]
    assert [p[2][0][3] for p in payloads] == [
        [[SCHOOL_TUESDAY_MORNING, [8, 30], [12, 0]]],
        [[SCHOOL_TUESDAY_AFTERNOON, [13, 30], [15, 30]]],
    ]
    assert all(call.kwargs["params"] == {"$httpMethod": "PUT"} for call in session.post.call_args_list)


async def test_windows_write_sets_a_single_window_day_too() -> None:
    client, session = _client(_time_limit_data())

    assert await client.async_set_school_time_windows([("08:00", "12:10")], day=5, account_id=ACCOUNT_ID)

    assert json.loads(session.post.call_args.kwargs["data"])[2][0][3] == [[SCHOOL_FRIDAY, [8, 0], [12, 10]]]


def _blocks(session) -> list:
    return [json.loads(call.kwargs["data"])[2][0] for call in session.post.call_args_list]


async def test_windows_write_adds_a_break_in_one_call_with_the_kept_slot() -> None:
    """Friday has one slot; two windows cut it in two (shape captured 2026-10-27)."""
    client, session = _client(_time_limit_data())

    assert await client.async_set_school_time_windows(
        [("08:00", "12:00"), ("13:00", "15:00")], day=5, account_id=ACCOUNT_ID
    )

    assert _blocks(session) == [
        [
            None,
            [[None, 5, 2, [13, 0], [15, 0], None, None, SCHOOL_RULE]],
            None,
            [[SCHOOL_FRIDAY, [8, 0], [12, 0]]],
            None,
            None,
        ],
    ]


async def test_windows_write_removes_a_break_in_one_call_with_the_kept_slot() -> None:
    """Tuesday has two slots; one window keeps the first, re-extended, and deletes the second.

    The rewrite must travel with the deletion: sent first, 08:00-15:00 overlaps
    the afternoon slot and Google answers 400 (live 2026-10-27).
    """
    client, session = _client(_time_limit_data_with_break())

    assert await client.async_set_school_time_windows([("08:00", "15:00")], day=2, account_id=ACCOUNT_ID)

    assert _blocks(session) == [
        [None, None, None, [[SCHOOL_TUESDAY_MORNING, [8, 0], [15, 0]]], None, [SCHOOL_TUESDAY_AFTERNOON]],
    ]


async def test_windows_write_fails_without_a_slot_for_the_day() -> None:
    """Google keeps a day to its slots: a lone creation is refused (live 2026-10-27)."""
    client, session = _client(_time_limit_data())

    assert not await client.async_set_school_time_windows([("08:00", "12:00")], day=3, account_id=ACCOUNT_ID)

    session.post.assert_not_called()


@pytest.mark.parametrize("windows", [[], [("08:00", "10:00"), ("10:30", "12:00"), ("13:00", "15:00")]])
async def test_windows_write_refuses_none_or_more_than_two(windows) -> None:
    """Family Link allows one break per day (a third slot answers 400, live 2026-10-27)."""
    client, session = _client(_time_limit_data_with_break())

    assert not await client.async_set_school_time_windows(windows, day=2, account_id=ACCOUNT_ID)

    session.post.assert_not_called()


async def test_windows_write_fails_without_a_rule_id_to_create_a_slot() -> None:
    data = _time_limit_data()
    data[5] = [[BEDTIME_RULE, 1, 2, ["1", 0]]]
    client, session = _client(data)
    client.async_get_time_limit = AsyncMock(return_value={})

    assert not await client.async_set_school_time_windows(
        [("08:00", "12:00"), ("13:00", "15:00")], day=5, account_id=ACCOUNT_ID
    )

    session.post.assert_not_called()


async def test_windows_write_fails_when_google_refuses_the_break_change() -> None:
    client, session = _client(_time_limit_data())
    session.post = MagicMock(return_value=_Response(400))

    assert not await client.async_set_school_time_windows(
        [("08:00", "12:00"), ("13:00", "15:00")], day=5, account_id=ACCOUNT_ID
    )

    assert session.post.call_count == 1


@pytest.mark.parametrize(
    "windows",
    [
        [("12:00", "08:00")],
        [("08:00", "12:00"), ("11:30", "15:00")],
        [("08:00", "12:00"), ("12:00", "15:00")],
        [("13:00", "15:00"), ("08:00", "12:00")],
        [("08:00", "25:00")],
    ],
)
async def test_windows_in_the_wrong_order_or_overlapping_are_rejected_before_any_request(windows) -> None:
    client, session = _client(_time_limit_data_with_break())

    assert not await client.async_set_school_time_windows(windows, day=2, account_id=ACCOUNT_ID)

    session.post.assert_not_called()


async def test_windows_write_stops_at_the_first_refused_slot() -> None:
    client, session = _client(_time_limit_data_with_break())
    session.post = MagicMock(side_effect=[_Response(200), _Response(400)])

    assert not await client.async_set_school_time_windows(
        [("08:00", "12:00"), ("13:00", "15:00")], day=2, account_id=ACCOUNT_ID
    )

    assert session.post.call_count == 2


async def test_service_passes_the_windows_of_the_day_to_the_client(hass, services) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_school_time",
        {"child_id": ACCOUNT_ID, "day": "2", "windows": ["08:00:00-12:00:00", " 13:30 - 15:00 "]},
        blocking=True,
    )

    services.client.async_set_school_time_windows.assert_awaited_once_with(
        windows=[("08:00", "12:00"), ("13:30", "15:00")], day=2, account_id=ACCOUNT_ID
    )
    services.client.async_set_school_time.assert_not_awaited()
    assert services.async_request_refresh.await_count == 1


async def test_service_raises_when_google_rejects_the_windows(hass, services) -> None:
    services.client.async_set_school_time_windows.return_value = False

    with pytest.raises(HomeAssistantError, match="08:00-12:00"):
        await hass.services.async_call(
            DOMAIN, "set_school_time", {"child_id": ACCOUNT_ID, "windows": ["08:00-12:00"]}, blocking=True
        )
    assert services.async_request_refresh.await_count == 0


@pytest.mark.parametrize(
    "data",
    [
        {"windows": ["08:00-12:00"], "start_time": "08:00", "end_time": "12:00"},
        {"windows": ["08:00-12:00"], "scope": "today"},
        {"start_time": "08:00"},
        {},
    ],
)
async def test_service_refuses_windows_mixed_with_the_bounds_or_an_incomplete_call(hass, services, data) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "set_school_time", {"child_id": ACCOUNT_ID, **data}, blocking=True)

    services.client.async_set_school_time.assert_not_awaited()
    services.client.async_set_school_time_windows.assert_not_awaited()


@pytest.mark.parametrize("windows", [[], ["08:00-10:00", "10:30-12:00", "13:00-15:00"]])
async def test_service_rejects_none_or_more_than_two_windows(hass, services, windows) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "set_school_time", {"child_id": ACCOUNT_ID, "windows": windows}, blocking=True
        )

    services.client.async_set_school_time_windows.assert_not_awaited()


@pytest.mark.parametrize("window", ["08:00", "8h-12h", "08:00-12:00-15:00", "25:00-26:00x"])
async def test_service_rejects_a_malformed_window(hass, services, window) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "set_school_time", {"child_id": ACCOUNT_ID, "windows": [window]}, blocking=True)
