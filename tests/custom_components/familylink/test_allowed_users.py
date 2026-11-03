"""The "Users allowed to control Family Link" option (issue #224).

Home Assistant lets every user press any button or flip any switch unless an
entity permission policy says otherwise. When the option lists users, a
non-administrator who is not listed is refused on every Family Link entity
action and every familylink.* service; administrators and calls without a
user (automations) stay allowed, and an empty list changes nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser

from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er

from custom_components.familylink import async_setup_services
from custom_components.familylink.config_flow import _allowed_users_selector
from custom_components.familylink.const import CONF_ALLOWED_USERS, DOMAIN
from custom_components.familylink.permissions import allowed_user_ids, async_check_entity_action

PHONE = "switch.kid_phone"
PHONE_DEVICE_ID = "device-phone"
CHILD_ID = "child-1"
EVERY_ENTITY = {"entities": True}


@pytest.fixture
async def services(hass, coordinator):
    registry = er.async_get(hass)
    registry.async_get_or_create("switch", DOMAIN, "kid_phone", suggested_object_id="kid_phone")
    hass.states.async_set(PHONE, "on", {"device_id": PHONE_DEVICE_ID, "child_id": CHILD_ID})
    await async_setup_services(hass, coordinator)
    return coordinator


def _user(hass, *, is_admin: bool = False) -> MockUser:
    user = MockUser(is_owner=is_admin).add_to_hass(hass)
    if not is_admin:
        user.mock_policy(EVERY_ENTITY)
    return user


def _restrict(hass, *user_ids: str) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_ALLOWED_USERS: list(user_ids)})
    entry.add_to_hass(hass)
    return entry


async def _bonus(hass, user: MockUser | None) -> None:
    context = Context(user_id=user.id) if user else Context()
    await hass.services.async_call(
        DOMAIN, "add_time_bonus", {"entity_id": PHONE, "bonus_minutes": 10}, blocking=True, context=context
    )


def _entity(hass, user: MockUser | None) -> SimpleNamespace:
    return SimpleNamespace(
        hass=hass,
        entity_id="button.kid_phone_15min",
        _context=Context(user_id=user.id) if user else Context(),
    )


async def test_empty_option_changes_nothing(hass, services) -> None:
    _restrict(hass)
    kid = _user(hass)

    assert allowed_user_ids(hass) is None
    await _bonus(hass, kid)
    await async_check_entity_action(_entity(hass, kid))

    assert services.client.async_add_time_bonus.await_count == 1


async def test_unlisted_user_is_refused_on_services(hass, services) -> None:
    parent = _user(hass)
    kid = _user(hass)
    _restrict(hass, parent.id)

    with pytest.raises(Unauthorized):
        await _bonus(hass, kid)

    services.client.async_add_time_bonus.assert_not_awaited()


async def test_listed_user_is_allowed_on_services(hass, services) -> None:
    parent = _user(hass)
    _restrict(hass, parent.id)

    await _bonus(hass, parent)

    assert services.client.async_add_time_bonus.await_count == 1


async def test_admin_is_allowed_without_being_listed(hass, services) -> None:
    parent = _user(hass)
    admin = _user(hass, is_admin=True)
    _restrict(hass, parent.id)

    await hass.services.async_call(
        DOMAIN, "add_time_bonus", {"device_id": PHONE_DEVICE_ID, "bonus_minutes": 10},
        blocking=True, context=Context(user_id=admin.id),
    )

    assert services.client.async_add_time_bonus.await_count == 1


async def test_automation_is_allowed(hass, services) -> None:
    parent = _user(hass)
    _restrict(hass, parent.id)

    await _bonus(hass, None)

    assert services.client.async_add_time_bonus.await_count == 1


async def test_unlisted_user_is_refused_on_entity_actions(hass) -> None:
    parent = _user(hass)
    kid = _user(hass)
    admin = _user(hass, is_admin=True)
    _restrict(hass, parent.id)

    with pytest.raises(Unauthorized):
        await async_check_entity_action(_entity(hass, kid))
    await async_check_entity_action(_entity(hass, parent))
    await async_check_entity_action(_entity(hass, admin))
    await async_check_entity_action(_entity(hass, None))


async def test_lists_of_several_entries_add_up(hass) -> None:
    first = _user(hass)
    second = _user(hass)
    _restrict(hass, first.id)
    _restrict(hass, second.id)
    _restrict(hass)

    assert allowed_user_ids(hass) == {first.id, second.id}


async def test_options_list_people_not_system_users(hass) -> None:
    person = MockUser(name="Parent").add_to_hass(hass)
    system = MockUser(name="Supervisor", system_generated=True).add_to_hass(hass)

    users_selector, user_ids = await _allowed_users_selector(hass)

    assert person.id in user_ids
    assert system.id not in user_ids
    values = [option["value"] for option in users_selector.config["options"]]
    assert person.id in values and system.id not in values
