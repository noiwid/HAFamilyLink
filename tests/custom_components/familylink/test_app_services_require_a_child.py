"""The app services need a child, or an explicit all_children: true.

A call without a child used to change every supervised child, which an
automation could do by mistake (a templated child_id that came out empty, or
an entity that carries no child, #73). Every child is now only targeted on
all_children: true.
"""

from __future__ import annotations

import pytest

from homeassistant.exceptions import ServiceValidationError

from custom_components.familylink import async_setup_services
from custom_components.familylink.const import DOMAIN

CHILD_1 = "child-1"
CHILD_2 = "child-2"

# service -> (client method, extra data)
SERVICES = {
    "block_app": ("async_block_app", {"package_name": "com.example.game"}),
    "unblock_app": ("async_unblock_app", {"package_name": "com.example.game"}),
    "set_app_daily_limit": ("async_set_app_daily_limit", {"package_name": "com.example.game", "minutes": 30}),
    "block_device_for_school": ("async_block_device_for_school", {}),
    "unblock_all_apps": ("async_unblock_all_apps", {}),
}


@pytest.fixture
async def services(hass, coordinator):
    coordinator.client.async_get_all_supervised_children.return_value = [
        {"id": CHILD_1, "name": "Alex"},
        {"id": CHILD_2, "name": "Sam"},
    ]
    hass.states.async_set("sensor.alex_screen_time", "10", {"child_id": CHILD_1})
    hass.states.async_set("sensor.no_child", "10", {})
    await async_setup_services(hass, coordinator)
    return coordinator


def _accounts(method) -> list[str]:
    return [call.kwargs["account_id"] for call in method.call_args_list]


@pytest.mark.parametrize("service", list(SERVICES))
async def test_a_call_without_a_child_raises_and_changes_nothing(hass, services, service) -> None:
    method_name, extra = SERVICES[service]

    with pytest.raises(ServiceValidationError, match="No child given"):
        await hass.services.async_call(DOMAIN, service, dict(extra), blocking=True)

    getattr(services.client, method_name).assert_not_called()


@pytest.mark.parametrize("service", list(SERVICES))
async def test_all_children_true_changes_every_child(hass, services, service) -> None:
    method_name, extra = SERVICES[service]

    await hass.services.async_call(DOMAIN, service, {**extra, "all_children": True}, blocking=True)

    assert _accounts(getattr(services.client, method_name)) == [CHILD_1, CHILD_2]


@pytest.mark.parametrize("service", list(SERVICES))
async def test_a_child_from_an_entity_or_child_id_changes_that_child_only(hass, services, service) -> None:
    method_name, extra = SERVICES[service]
    method = getattr(services.client, method_name)

    await hass.services.async_call(DOMAIN, service, {**extra, "entity_id": "sensor.alex_screen_time"}, blocking=True)
    await hass.services.async_call(DOMAIN, service, {**extra, "child_id": CHILD_2}, blocking=True)

    assert _accounts(method) == [CHILD_1, CHILD_2]


async def test_an_entity_without_a_child_raises_instead_of_changing_every_child(hass, services) -> None:
    with pytest.raises(ServiceValidationError, match="does not belong to a Family Link child"):
        await hass.services.async_call(
            DOMAIN, "block_app", {"package_name": "com.example.game", "entity_id": "sensor.no_child"}, blocking=True
        )

    services.client.async_block_app.assert_not_called()


async def test_a_child_and_all_children_together_raise(hass, services) -> None:
    with pytest.raises(ServiceValidationError, match="not both"):
        await hass.services.async_call(
            DOMAIN, "block_app", {"package_name": "com.example.game", "child_id": CHILD_1, "all_children": True}, blocking=True
        )

    services.client.async_block_app.assert_not_called()
