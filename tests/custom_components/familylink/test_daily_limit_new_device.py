"""A daily limit sent to a device Google does not list yet says so.

A newly supervised device has no applied time limits for a while (about 30
minutes seen live on a tablet): Google answers the override with HTTP 200 but
never applies it, and the readback reported the generic "accepted but not
applied" failure. The client now logs that the device is not listed yet, and
the service adds the hint to its error so it shows in the automation trace.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.familylink import async_setup_services
from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN

CHILD_ID = "child-1"
PHONE = "device-phone"
NEW_TABLET = "device-new-tablet"


def _client(applied: dict) -> FamilyLinkClient:
    client = object.__new__(FamilyLinkClient)
    client.async_get_applied_time_limits = AsyncMock(return_value=applied)
    return client


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("custom_components.familylink.client.api.asyncio.sleep", AsyncMock()):
        yield


async def test_readback_names_a_device_google_does_not_list_yet(caplog) -> None:
    client = _client({"devices": {PHONE: {"daily_limit_minutes": 120}}})

    with caplog.at_level(logging.WARNING):
        assert not await client._async_verify_daily_limit_applied(CHILD_ID, NEW_TABLET, 45)

    assert "lists no time limits for this device yet" in caplog.text
    assert "issue #157" not in caplog.text


async def test_readback_of_a_listed_device_keeps_the_157_message(caplog) -> None:
    client = _client({"devices": {PHONE: {"daily_limit_minutes": 120}}})

    with caplog.at_level(logging.WARNING):
        assert not await client._async_verify_daily_limit_applied(CHILD_ID, PHONE, 45)

    assert "issue #157" in caplog.text
    assert "lists no time limits" not in caplog.text


async def test_readback_of_an_applied_value_passes() -> None:
    client = _client({"devices": {PHONE: {"daily_limit_minutes": 45}}})

    assert await client._async_verify_daily_limit_applied(CHILD_ID, PHONE, 45)


@pytest.fixture
async def services(hass, coordinator):
    coordinator.data = {
        "children_data": [
            {
                "child_id": CHILD_ID,
                "devices": [{"id": PHONE}, {"id": NEW_TABLET}],
                "devices_time_data": {PHONE: {"daily_limit_minutes": 120}},
            }
        ]
    }
    await async_setup_services(hass, coordinator)
    return coordinator


async def test_service_error_hints_at_a_device_without_time_limits(hass, services) -> None:
    services.client.async_set_daily_limit = AsyncMock(side_effect=lambda **kw: kw["device_id"] == PHONE)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN, "set_daily_limit", {"device_id": NEW_TABLET, "child_id": CHILD_ID, "daily_minutes": 45}, blocking=True
        )

    assert "no time limits for device(s) device-new-tablet yet" in str(err.value)


async def test_service_error_has_no_hint_for_a_listed_device(hass, services) -> None:
    services.client.async_set_daily_limit = AsyncMock(return_value=False)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN, "set_daily_limit", {"device_id": PHONE, "child_id": CHILD_ID, "daily_minutes": 45}, blocking=True
        )

    assert "yet" not in str(err.value)
