"""set_bedtime takes an entity_id like the other child services.

It was the only child-targeted service whose schema had child_id alone, so a
call naming an entity was rejected, and a non-administrator, who may only
target an entity, could not call it at all.
"""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser

from homeassistant.core import Context
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.familylink import async_setup_services
from custom_components.familylink.const import DOMAIN

FIRST_CHILD_ID = "child-1"
SECOND_CHILD_ID = "child-2"
# A per-child sensor carries the child_id attribute.
SECOND_CHILD_SENSOR = "sensor.second_child_daily_screen_time"
BEDTIME = {"start_time": "21:00", "end_time": "07:00", "day": "5"}


@pytest.fixture
async def services(hass, coordinator):
    # A Family Link entity in the registry: the service guard lets a non-admin
    # target only those
    er.async_get(hass).async_get_or_create(
        "sensor", DOMAIN, "second_child_daily_screen_time",
        suggested_object_id="second_child_daily_screen_time",
    )
    hass.states.async_set(SECOND_CHILD_SENSOR, "42", {"child_id": SECOND_CHILD_ID})
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
        "switch", DOMAIN, f"{child_id}_bedtime", config_entry=entry, device_id=device.id
    )
    hass.states.async_set(reg.entity_id, "on")
    return reg.entity_id


def _non_admin(hass, policy: dict) -> MockUser:
    user = MockUser(is_owner=False).add_to_hass(hass)
    user.mock_policy(policy)
    return user


async def _call(hass, data: dict, user: MockUser | None = None) -> None:
    context = Context(user_id=user.id) if user else Context()
    await hass.services.async_call(DOMAIN, "set_bedtime", data, blocking=True, context=context)


async def test_entity_id_resolves_the_child_from_its_attribute(hass, services) -> None:
    await _call(hass, {"entity_id": SECOND_CHILD_SENSOR, **BEDTIME})

    services.client.async_set_bedtime.assert_awaited_once_with(
        start_time="21:00", end_time="07:00", day=5, account_id=SECOND_CHILD_ID, scope="weekly"
    )
    # The strict mode reference is recorded for that child, not the first one.
    services.record_bedtime_hours.assert_called_once_with(SECOND_CHILD_ID, 5, [21, 0], [7, 0])
    assert services.async_request_refresh.await_count == 1


async def test_entity_id_resolves_the_child_from_its_device(hass, services) -> None:
    entity_id = _child_switch(hass, SECOND_CHILD_ID)

    await _call(hass, {"entity_id": entity_id, **BEDTIME, "scope": "today"})

    services.client.async_set_bedtime.assert_awaited_once_with(
        start_time="21:00", end_time="07:00", day=5, account_id=SECOND_CHILD_ID, scope="today"
    )


async def test_entity_without_a_child_is_refused(hass, services) -> None:
    """Another integration's entity names no child: no fallback to the first one."""
    hass.states.async_set("light.kitchen", "on")

    with pytest.raises(ServiceValidationError, match="does not belong to a Family Link child"):
        await _call(hass, {"entity_id": "light.kitchen", **BEDTIME})

    assert services.client.mock_calls == []
    services.record_bedtime_hours.assert_not_called()


async def test_unknown_entity_is_refused(hass, services) -> None:
    with pytest.raises(ServiceValidationError, match="not found"):
        await _call(hass, {"entity_id": "sensor.missing", **BEDTIME})

    assert services.client.mock_calls == []


async def test_child_id_still_works(hass, services) -> None:
    await _call(hass, {"child_id": FIRST_CHILD_ID, **BEDTIME})

    services.client.async_set_bedtime.assert_awaited_once_with(
        start_time="21:00", end_time="07:00", day=5, account_id=FIRST_CHILD_ID, scope="weekly"
    )
    services.record_bedtime_hours.assert_called_once_with(FIRST_CHILD_ID, 5, [21, 0], [7, 0])


async def test_manual_child_id_takes_precedence_over_the_entity(hass, services) -> None:
    await _call(hass, {"entity_id": SECOND_CHILD_SENSOR, "child_id": FIRST_CHILD_ID, **BEDTIME})

    assert services.client.async_set_bedtime.await_args.kwargs["account_id"] == FIRST_CHILD_ID


async def test_non_admin_may_target_an_entity_they_control(hass, services) -> None:
    """What lets a non-admin dashboard call set_bedtime at all."""
    user = _non_admin(hass, {"entities": {"entity_ids": {SECOND_CHILD_SENSOR: True}}})

    await _call(hass, {"entity_id": SECOND_CHILD_SENSOR, **BEDTIME}, user)

    assert services.client.async_set_bedtime.await_args.kwargs["account_id"] == SECOND_CHILD_ID


async def test_non_admin_with_child_id_is_refused(hass, services) -> None:
    user = _non_admin(hass, {"entities": True})

    with pytest.raises(Unauthorized):
        await _call(hass, {"child_id": SECOND_CHILD_ID, **BEDTIME}, user)

    assert services.client.mock_calls == []
    services.record_bedtime_hours.assert_not_called()


async def test_non_admin_cannot_pair_the_entity_with_a_child_id(hass, services) -> None:
    """A permitted entity must not become a key for another child."""
    user = _non_admin(hass, {"entities": {"entity_ids": {SECOND_CHILD_SENSOR: True}}})

    with pytest.raises(Unauthorized):
        await _call(hass, {"entity_id": SECOND_CHILD_SENSOR, "child_id": FIRST_CHILD_ID, **BEDTIME}, user)

    assert services.client.mock_calls == []
