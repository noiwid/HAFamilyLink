"""Allow apps with unlimited time during downtime: read, write, switch and service.

The setting is read from the [flag, setting] pairs that end the timeLimit
response (setting 1, flag 1 = allowed) and written with timeLimit:update.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockUser

from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er

from custom_components.familylink import SCHEMA_SET_DOWNTIME_UNLIMITED_APPS, async_setup_services
from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN
from custom_components.familylink.schedules import parse_downtime_unlimited_apps
from custom_components.familylink.switch import FamilyLinkDowntimeUnlimitedAppsSwitch

CHILD_ID = "child-1"
SWITCH = "switch.kid_unlimited_apps_during_downtime"
BEDTIME_RULE = "802c3176-8b24-452c-9ccd-2b19aebe487c"
SCHOOL_RULE = "5c0d1f2e-1111-4222-8333-944455556666"


def _time_limit_data(settings=None) -> list:
    """An unwrapped timeLimit payload, ending with the downtime settings when given."""
    data = [
        [2, [["CAEQAQ", 1, 2, [20, 0], [7, 0], "1", "2", BEDTIME_RULE]], "1", "2", 1],
        [[["CAEQAQ", 1, 2, 120, "1", "2"]]],
        None,
        None,
        [1],
        [[BEDTIME_RULE, 1, 2, ["1", 0]], [SCHOOL_RULE, 2, 2, ["1", 0]]],
    ]
    if settings is not None:
        data += [None, settings]
    return data


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ([[1, 1], [0, 2]], True),
        ([[0, 1], [0, 2]], False),
        ([[0, 1], [1, 2]], False),
        # Found by its setting number, not by its position
        ([[0, 2], [1, 1]], True),
    ],
)
def test_reads_setting_1_of_the_trailing_pairs(settings, expected) -> None:
    assert parse_downtime_unlimited_apps(_time_limit_data(settings)) is expected


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"not": "a list"},
        # No settings list: the response ends with the revisions
        _time_limit_data(),
        _time_limit_data([]),
        _time_limit_data([[0, 2]]),
        _time_limit_data([[1]]),
        _time_limit_data([1, 1]),
        _time_limit_data([["1", 1]]),
        _time_limit_data([[True, 1]]),
        _time_limit_data([[2, 1]]),
        _time_limit_data([None, [1, None]]),
    ],
)
def test_missing_or_malformed_settings_read_as_unknown(data) -> None:
    assert parse_downtime_unlimited_apps(data) is None


class _Response:
    def __init__(self, status: int = 200, payload=None) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def text(self) -> str:
        return ""

    async def json(self):
        return self._payload


def _client(response: _Response) -> tuple[FamilyLinkClient, MagicMock]:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    session.put = MagicMock(return_value=response)
    client._get_session = AsyncMock(return_value=session)
    return client, session


@pytest.mark.parametrize(("settings", "expected"), [([[1, 1], [0, 2]], True), ([[0, 1], [0, 2]], False), (None, None)])
async def test_time_limit_read_reports_the_setting(settings, expected) -> None:
    client, _ = _client(_Response(payload=[[None, "1"], _time_limit_data(settings)]))

    result = await client.async_get_time_limit(account_id=CHILD_ID)

    assert result["downtime_unlimited_apps"] is expected
    # The trailing pairs do not disturb the revisions found before them
    assert result["bedtime_rule_id"] == BEDTIME_RULE
    assert result["schooltime_rule_id"] == SCHOOL_RULE


@pytest.mark.parametrize(("allow", "flag"), [(True, 1), (False, 0)])
async def test_write_sends_the_flag_of_setting_1(allow: bool, flag: int) -> None:
    client, session = _client(_Response())

    assert await client.async_set_downtime_unlimited_apps(allow, account_id=CHILD_ID)

    url = session.put.call_args.args[0]
    kwargs = session.put.call_args.kwargs
    assert url.endswith(f"/people/{CHILD_ID}/timeLimit:update")
    assert kwargs["params"] == {"$httpMethod": "PUT"}
    assert json.loads(kwargs["data"]) == [
        None,
        CHILD_ID,
        [None, None, None, None, [None, None, [[flag, 1]]]],
        None,
        [1],
    ]


async def test_write_without_a_child_uses_the_first_child() -> None:
    client, session = _client(_Response())
    client.async_get_supervised_child_id = AsyncMock(return_value=CHILD_ID)

    assert await client.async_set_downtime_unlimited_apps(False)

    assert json.loads(session.put.call_args.kwargs["data"])[1] == CHILD_ID


async def test_rejected_write_returns_false() -> None:
    client, _ = _client(_Response(status=400))

    assert not await client.async_set_downtime_unlimited_apps(True, account_id=CHILD_ID)


def _switch(value, *, pending=None) -> FamilyLinkDowntimeUnlimitedAppsSwitch:
    coordinator = SimpleNamespace(
        client=AsyncMock(),
        data={"children_data": [{"child_id": CHILD_ID, "child_name": "Kid", "downtime_unlimited_apps": value}]},
        last_update_success=True,
        async_request_refresh=AsyncMock(),
        get_pending_time_limit_state=MagicMock(return_value=pending),
        set_pending_time_limit_state=MagicMock(),
    )
    coordinator.client.async_set_downtime_unlimited_apps.return_value = True
    switch = FamilyLinkDowntimeUnlimitedAppsSwitch(coordinator, CHILD_ID, "Kid")
    switch.async_write_ha_state = MagicMock()
    return switch


@pytest.mark.parametrize("value", [True, False, None])
def test_switch_shows_the_setting(value) -> None:
    switch = _switch(value)

    assert switch.is_on is value
    assert switch.extra_state_attributes["child_id"] == CHILD_ID


def test_switch_of_an_unknown_child_is_unknown() -> None:
    switch = _switch(True)
    switch.coordinator.data = {"children_data": []}

    assert switch.is_on is None


def test_pending_state_wins_until_the_next_read() -> None:
    assert _switch(True, pending=False).is_on is False


@pytest.mark.parametrize(("method", "allow"), [("async_turn_on", True), ("async_turn_off", False)])
async def test_switch_writes_the_setting(method: str, allow: bool) -> None:
    switch = _switch(not allow)
    coordinator = switch.coordinator

    await getattr(switch, method)()

    coordinator.client.async_set_downtime_unlimited_apps.assert_awaited_once_with(allow=allow, account_id=CHILD_ID)
    coordinator.set_pending_time_limit_state.assert_called_once_with(CHILD_ID, "downtime_unlimited_apps", allow)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_failed_switch_write_drops_the_pending_state() -> None:
    switch = _switch(True)
    coordinator = switch.coordinator
    coordinator.client.async_set_downtime_unlimited_apps.return_value = False

    await switch.async_turn_off()

    assert coordinator.set_pending_time_limit_state.call_args_list[-1].args == (
        CHILD_ID, "downtime_unlimited_apps", None
    )
    coordinator.async_request_refresh.assert_not_awaited()


def test_service_schema_requires_allow() -> None:
    with pytest.raises(vol.Invalid):
        SCHEMA_SET_DOWNTIME_UNLIMITED_APPS({"child_id": CHILD_ID})
    assert SCHEMA_SET_DOWNTIME_UNLIMITED_APPS({"allow": "off"})["allow"] is False


@pytest.fixture
async def services(hass, coordinator):
    # A Family Link entity in the registry: the service guard lets a non-admin
    # target only those
    er.async_get(hass).async_get_or_create(
        "switch", DOMAIN, "kid_unlimited_apps_during_downtime",
        suggested_object_id="kid_unlimited_apps_during_downtime",
    )
    hass.states.async_set(SWITCH, "on", {"child_id": CHILD_ID, "child_name": "Kid"})
    await async_setup_services(hass, coordinator)
    return coordinator


@pytest.mark.parametrize(
    ("target", "account_id"),
    [
        ({"entity_id": SWITCH}, CHILD_ID),
        ({"child_id": "child-2"}, "child-2"),
        # No target: the client falls back to the first supervised child
        ({}, None),
    ],
)
async def test_service_targets_the_child(hass, services, target, account_id) -> None:
    await hass.services.async_call(
        DOMAIN, "set_downtime_unlimited_apps", {"allow": False, **target}, blocking=True
    )

    services.client.async_set_downtime_unlimited_apps.assert_awaited_once_with(allow=False, account_id=account_id)
    assert services.async_request_refresh.await_count == 1


@pytest.mark.parametrize(
    ("entity_id", "message"),
    [
        # Another integration's entity names no child: no fallback to the first one
        ("light.kitchen", "does not belong to a Family Link child"),
        ("sensor.missing", "not found"),
    ],
)
async def test_service_refuses_an_entity_without_a_child(hass, services, entity_id, message) -> None:
    hass.states.async_set("light.kitchen", "on")

    with pytest.raises(ServiceValidationError, match=message):
        await hass.services.async_call(
            DOMAIN, "set_downtime_unlimited_apps", {"allow": False, "entity_id": entity_id}, blocking=True
        )

    assert services.client.mock_calls == []


async def test_service_raises_when_google_rejects_the_change(hass, services) -> None:
    services.client.async_set_downtime_unlimited_apps.return_value = False

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "set_downtime_unlimited_apps", {"allow": True, "child_id": CHILD_ID}, blocking=True
        )
    assert services.async_request_refresh.await_count == 0


async def _call_as(hass, user: MockUser, data: dict) -> None:
    await hass.services.async_call(
        DOMAIN, "set_downtime_unlimited_apps", data, blocking=True, context=Context(user_id=user.id)
    )


async def test_non_admin_may_use_a_switch_they_control(hass, services) -> None:
    user = MockUser().add_to_hass(hass)
    user.mock_policy({"entities": {"entity_ids": {SWITCH: True}}})

    await _call_as(hass, user, {"allow": False, "entity_id": SWITCH})

    services.client.async_set_downtime_unlimited_apps.assert_awaited_once_with(allow=False, account_id=CHILD_ID)


@pytest.mark.parametrize(
    "data",
    [
        {"allow": False, "entity_id": SWITCH},
        {"allow": False, "child_id": CHILD_ID},
    ],
)
async def test_non_admin_is_refused_without_control_of_the_switch(hass, services, data) -> None:
    user = MockUser().add_to_hass(hass)
    user.mock_policy({"entities": {"entity_ids": {SWITCH: False}}})

    with pytest.raises(Unauthorized):
        await _call_as(hass, user, data)

    assert services.client.mock_calls == []
