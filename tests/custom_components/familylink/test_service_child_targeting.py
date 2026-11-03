"""Per-child services never fall back to the first child of a family of several.

Without a child the client used to target the first supervised child: with
two children, a call naming only the second one's device, or an empty
templated child_id, changed the first one's settings (and strict mode then
enforced them on the first one).
"""

from __future__ import annotations

import pytest

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.familylink import async_setup_services
from custom_components.familylink.const import DOMAIN

FIRST, SECOND = "child-1", "child-2"
SECOND_PHONE = "device-second-phone"


@pytest.fixture
async def services(hass, coordinator):
    coordinator.data = {
        "children_data": [
            {"child_id": FIRST, "devices": [{"id": "device-first-phone"}]},
            {"child_id": SECOND, "devices": [{"id": SECOND_PHONE}]},
        ]
    }
    await async_setup_services(hass, coordinator)
    return coordinator


async def _call(hass, service, data):
    await hass.services.async_call(DOMAIN, service, data, blocking=True)


@pytest.mark.parametrize(
    ("service", "data", "method"),
    [
        ("add_time_bonus", {"bonus_minutes": 10}, "async_add_time_bonus"),
        ("set_daily_limit", {"daily_minutes": 30}, "async_set_daily_limit"),
    ],
)
async def test_a_device_alone_targets_its_own_child(hass, services, service, data, method) -> None:
    await _call(hass, service, {**data, "device_id": SECOND_PHONE})

    assert getattr(services.client, method).await_args.kwargs["account_id"] == SECOND


async def test_set_daily_limit_records_the_reference_of_the_device_child(hass, services) -> None:
    await _call(hass, "set_daily_limit", {"daily_minutes": 30, "device_id": SECOND_PHONE})

    assert services.record_daily_limit_minutes.call_args.args[0] == SECOND


async def test_ring_targets_the_device_child(hass, services) -> None:
    await _call(hass, "ring_device", {"device_id": SECOND_PHONE})

    assert services.client.async_ring_device.await_args.kwargs["child_id"] == SECOND


@pytest.mark.parametrize(
    "service",
    ["enable_bedtime", "disable_bedtime", "enable_school_time", "disable_school_time", "enable_daily_limit", "disable_daily_limit"],
)
@pytest.mark.parametrize("data", [{}, {"child_id": ""}, {"child_id": "None"}])
async def test_policy_toggle_without_a_child_is_refused(hass, services, service, data) -> None:
    with pytest.raises(ServiceValidationError):
        await _call(hass, service, data)

    assert services.client.mock_calls == []
    services.record_policy_intent.assert_not_called()


async def test_unknown_device_is_refused_among_several_children(hass, services) -> None:
    with pytest.raises(ServiceValidationError):
        await _call(hass, "add_time_bonus", {"bonus_minutes": 10, "device_id": "device-unknown"})

    services.client.async_add_time_bonus.assert_not_called()


async def test_policy_toggle_targets_the_given_child(hass, services) -> None:
    await _call(hass, "disable_bedtime", {"child_id": SECOND})

    services.client.async_disable_bedtime.assert_awaited_once_with(account_id=SECOND)
    services.record_policy_intent.assert_called_once_with(SECOND, "bedtime", False)


async def test_a_refused_toggle_raises_and_records_nothing(hass, services) -> None:
    services.client.async_enable_bedtime.return_value = False

    with pytest.raises(HomeAssistantError):
        await _call(hass, "enable_bedtime", {"child_id": SECOND})

    services.record_policy_intent.assert_not_called()


async def test_a_refused_bonus_raises_and_gives_back_the_strict_mode_allowance(hass, services) -> None:
    services.client.async_add_time_bonus.return_value = False

    with pytest.raises(HomeAssistantError):
        await _call(hass, "add_time_bonus", {"bonus_minutes": 10, "device_id": SECOND_PHONE})

    services.restore_ha_bonus.assert_called_once_with(SECOND_PHONE, None)


async def test_a_refused_app_block_raises(hass, services) -> None:
    services.client.async_block_app.return_value = False

    with pytest.raises(HomeAssistantError):
        await _call(hass, "block_app", {"package_name": "com.example.app", "child_id": SECOND})
