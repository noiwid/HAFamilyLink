"""The familylink.* services only run for callers allowed to control the entities.

Home Assistant checks entity permissions on entity actions, not on domain
services that take raw identifiers. These tests pin the rule the integration
applies on top: automations are trusted, administrators can do anything, a
non-administrator may target an entity they control, and raw identifiers or
target-less calls need an administrator.
"""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockUser

from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized, UnknownUser

from custom_components.familylink import async_setup_services
from custom_components.familylink.const import DOMAIN

PHONE = "switch.kid_phone"
PHONE_DEVICE_ID = "device-phone"
TABLET_DEVICE_ID = "device-tablet"
CHILD_ID = "child-1"

# Every service the integration registers, with the smallest data its schema
# accepts and no target at all. Kept exhaustive on purpose: a service added
# without a line here fails test_every_registered_service_is_covered.
ALL_SERVICES = [
    ("block_device_for_school", {}),
    ("unblock_all_apps", {}),
    ("block_app", {"package_name": "com.example.app"}),
    ("unblock_app", {"package_name": "com.example.app"}),
    ("set_app_daily_limit", {"package_name": "com.example.app", "minutes": 30}),
    ("add_time_bonus", {"bonus_minutes": 10}),
    ("enable_bedtime", {}),
    ("disable_bedtime", {}),
    ("enable_school_time", {}),
    ("disable_school_time", {}),
    ("enable_daily_limit", {}),
    ("disable_daily_limit", {}),
    ("set_daily_limit", {"daily_minutes": 60}),
    ("set_bedtime", {"start_time": "21:00", "end_time": "07:00"}),
    ("set_school_time", {"start_time": "08:00", "end_time": "13:00"}),
    ("refresh_location", {}),
    ("ring_device", {}),
    ("set_update_interval", {"seconds": 300}),
]


@pytest.fixture
async def services(hass, coordinator):
    """Register the services against a mocked coordinator and one device entity."""
    hass.states.async_set(
        PHONE, "on", {"device_id": PHONE_DEVICE_ID, "child_id": CHILD_ID}
    )
    await async_setup_services(hass, coordinator)
    return coordinator


def _user(hass, *, is_admin: bool = False, policy: dict | None = None) -> MockUser:
    # MockUser has no is_admin flag: an owner is an administrator, a user
    # without groups is not.
    user = MockUser(is_owner=is_admin).add_to_hass(hass)
    if policy is not None:
        user.mock_policy(policy)
    return user


async def _call(hass, service: str, data: dict, user: MockUser | None = None) -> None:
    context = Context(user_id=user.id) if user else Context()
    await hass.services.async_call(DOMAIN, service, data, blocking=True, context=context)


async def test_every_registered_service_is_covered(hass, services) -> None:
    """The exhaustive list above matches what the integration registers."""
    registered = set(hass.services.async_services().get(DOMAIN, {}))
    assert registered == {name for name, _ in ALL_SERVICES}


async def test_automation_context_is_trusted(hass, services) -> None:
    """A call without a user, as an automation makes, runs as before."""
    await _call(hass, "add_time_bonus", {"device_id": PHONE_DEVICE_ID, "bonus_minutes": 10})

    assert services.client.async_add_time_bonus.await_count == 1


async def test_admin_may_use_raw_identifiers(hass, services) -> None:
    """An administrator keeps full access, raw identifiers included."""
    admin = _user(hass, is_admin=True)

    await _call(hass, "add_time_bonus", {"device_id": PHONE_DEVICE_ID, "bonus_minutes": 10}, admin)

    assert services.client.async_add_time_bonus.await_count == 1


async def test_unknown_user_is_refused(hass, services) -> None:
    """A context naming a user that does not exist is refused, not trusted."""
    with pytest.raises(UnknownUser):
        await hass.services.async_call(
            DOMAIN,
            "add_time_bonus",
            {"device_id": PHONE_DEVICE_ID, "bonus_minutes": 10},
            blocking=True,
            context=Context(user_id="no-such-user"),
        )

    assert services.client.mock_calls == []


@pytest.mark.parametrize(("service", "data"), ALL_SERVICES)
async def test_non_admin_without_entity_target_is_refused(hass, services, service, data) -> None:
    """Without an entity to evaluate a policy against, a non-administrator is refused."""
    user = _user(hass, policy={"entities": True})

    with pytest.raises(Unauthorized):
        await _call(hass, service, data, user)

    assert services.client.mock_calls == []
    assert services.async_request_refresh.await_count == 0


async def test_non_admin_with_raw_identifier_is_refused(hass, services) -> None:
    """Controlling every entity does not extend to raw identifiers."""
    user = _user(hass, policy={"entities": True})

    with pytest.raises(Unauthorized):
        await _call(hass, "add_time_bonus", {"device_id": PHONE_DEVICE_ID, "bonus_minutes": 10}, user)

    assert services.client.mock_calls == []


async def test_non_admin_may_target_an_entity_they_control(hass, services) -> None:
    """Naming an entity the user controls works like toggling it from a dashboard."""
    user = _user(hass, policy={"entities": {"entity_ids": {PHONE: True}}})

    await _call(hass, "add_time_bonus", {"entity_id": PHONE, "bonus_minutes": 10}, user)

    assert services.client.async_add_time_bonus.await_count == 1
    assert PHONE_DEVICE_ID in repr(services.client.async_add_time_bonus.await_args)


async def test_non_admin_denied_on_the_entity_is_refused(hass, services) -> None:
    """An entity policy that denies the entity denies the service too."""
    user = _user(hass, policy={"entities": {"entity_ids": {PHONE: False}}})

    with pytest.raises(Unauthorized):
        await _call(hass, "add_time_bonus", {"entity_id": PHONE, "bonus_minutes": 10}, user)

    assert services.client.mock_calls == []


async def test_non_admin_cannot_pair_entity_with_another_raw_identifier(hass, services) -> None:
    """A permitted entity must not become a key for any other device.

    The handlers let a raw device_id win over the one read from the entity, so
    the combination is refused outright for a non-administrator.
    """
    user = _user(hass, policy={"entities": {"entity_ids": {PHONE: True}}})

    with pytest.raises(Unauthorized):
        await _call(
            hass,
            "add_time_bonus",
            {"entity_id": PHONE, "device_id": TABLET_DEVICE_ID, "bonus_minutes": 10},
            user,
        )

    assert services.client.mock_calls == []
