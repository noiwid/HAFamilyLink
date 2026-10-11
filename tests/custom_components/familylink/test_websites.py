"""Chrome site lists: patterns, the client's parsing of responses, the site services and sensors.

The response shapes below are real websites:listRestrictions /
websites:updateRestrictions answers.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import DOMAIN, WEBSITES_REFRESH
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.exceptions import SessionExpiredError
from custom_components.familylink.sensor import FamilyLinkWebsitesSensor
from custom_components.familylink.website_services import async_setup_website_services
from custom_components.familylink.websites import domain_patterns, normalize_site, parse_site_list

CHILD = "child-1"
LIST_URL = "https://lists.example.org/gaps.txt"

LIST_RESPONSE = {
    "filterLevel": "safeSites",
    "explicitWebsiteExceptions": [
        {"pattern": "*.example.*", "exceptionType": "block", "iconUrl": "https://encrypted-tbn2.gstatic.com/x"},
        {"pattern": "https://example.org/path?q=1", "exceptionType": "block"},
        {"pattern": "*.wikipedia.*", "exceptionType": "allow"},
    ],
}
UPDATE_RESPONSE = {
    "filterLevel": "safeSites",
    "explicitWebsiteExceptions": [{"pattern": "*.example.*", "exceptionType": "block"}],
    "filteredExceptions": [
        {
            "exception": {"pattern": "example.net", "exceptionType": "block"},
            "coveredByException": {"pattern": "*.example.*", "exceptionType": "block"},
        }
    ],
}


# --- patterns -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("www.Example.com", "www.example.com"),
        ("  example.com/ ", "example.com"),
        ("*.example.com", "*.example.com"),
        ("*.example.*", "*.example.*"),
        ("https://example.com", "example.com"),
        ("https://example.org/path?q=1", "https://example.org/path?q=1"),
    ],
)
def test_normalize_site_accepts_the_documented_forms(value, expected) -> None:
    assert normalize_site(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "ex*ample.com", "*example.com", "example", "a" * 64 + ".com", "ftp://example.com/x", "exa mple.com", "*.*"],
)
def test_normalize_site_rejects_what_google_would_store_blindly(value) -> None:
    with pytest.raises(ValueError):
        normalize_site(value)


def test_domain_patterns_cover_the_domain_and_its_subdomains() -> None:
    assert domain_patterns("Example.com") == ["*.example.com", "example.com"]
    assert domain_patterns("*.example.*") == ["*.example.*"]


def test_parse_site_list_reads_comments_hosts_lines_and_skips_junk() -> None:
    text = "# header\nexample.com\n0.0.0.0 tracker.example.net  # hosts style\nexample.com\nnot a domain!\n\n"
    assert parse_site_list(text) == ["example.com", "tracker.example.net"]


# --- client parsing -----------------------------------------------------------


def test_client_reads_the_lists_and_lowercase_types() -> None:
    lists = FamilyLinkClient._website_lists(LIST_RESPONSE)

    assert lists == {
        "filter_level": "safeSites",
        "approved": ["*.wikipedia.*"],
        "blocked": ["*.example.*", "https://example.org/path?q=1"],
    }


def test_client_reads_an_empty_list() -> None:
    assert FamilyLinkClient._website_lists({"filterLevel": "safeSites"}) == {
        "filter_level": "safeSites",
        "approved": [],
        "blocked": [],
    }


async def test_client_update_reports_covered_entries_without_listing_them() -> None:
    client = object.__new__(FamilyLinkClient)
    client._website_request = AsyncMock(return_value=UPDATE_RESPONSE)

    result = await client.async_update_website_restrictions(CHILD, insert=[("example.net", "BLOCK")])

    method, child, suffix, body = client._website_request.await_args.args
    assert (method, child, suffix) == ("POST", CHILD, "websites:updateRestrictions")
    assert body["insertedWebsiteExceptions"] == [{"pattern": "example.net", "exceptionType": "BLOCK"}]
    assert result["blocked"] == ["*.example.*"]
    assert result["covered"] == {"example.net": "*.example.*"}


# --- services ---------------------------------------------------------------------


@pytest.fixture
async def site_services(hass):
    client = SimpleNamespace(
        async_get_website_restrictions=AsyncMock(
            return_value={"filter_level": "safeSites", "approved": ["*.wikipedia.*"], "blocked": ["manual.example"]}
        ),
        async_update_website_restrictions=AsyncMock(
            return_value={"filter_level": "safeSites", "approved": [], "blocked": [], "covered": {}}
        ),
    )
    coordinator = SimpleNamespace(client=client, store_websites=MagicMock(), async_request_refresh=AsyncMock())
    await async_setup_website_services(hass, coordinator)
    return coordinator


async def _call(hass, service, data):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=True)


async def test_get_sites_returns_the_lists(hass, site_services) -> None:
    result = await _call(hass, "get_sites", {"child_id": CHILD})

    assert result["blocked"] == ["manual.example"]
    assert result["approved"] == ["*.wikipedia.*"]


async def test_block_and_allow_send_normalised_patterns(hass, site_services) -> None:
    update = site_services.client.async_update_website_restrictions

    await _call(hass, "block_site", {"child_id": CHILD, "sites": ["WWW.Example.com", "https://example.com"]})
    await _call(hass, "allow_site", {"child_id": CHILD, "sites": ["*.wikipedia.*"]})

    assert update.await_args_list[0].kwargs["insert"] == [("www.example.com", "BLOCK"), ("example.com", "BLOCK")]
    assert update.await_args_list[1].kwargs["insert"] == [("*.wikipedia.*", "ALLOW")]
    assert site_services.store_websites.call_count == 2


async def test_an_invalid_site_raises_before_any_write(hass, site_services) -> None:
    with pytest.raises(ServiceValidationError, match="Wildcards"):
        await _call(hass, "block_site", {"child_id": CHILD, "sites": ["ex*ample.com"]})

    site_services.client.async_update_website_restrictions.assert_not_called()


async def test_a_site_service_needs_a_child(hass, site_services) -> None:
    with pytest.raises(ServiceValidationError, match="No child given"):
        await _call(hass, "block_site", {"sites": ["example.com"]})


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("get_sites", {}),
        ("remove_site", {"sites": ["example.com"]}),
        ("sync_site_list", {"url": LIST_URL, "stop": True}),
    ],
)
async def test_a_failed_read_gives_the_same_error_everywhere(hass, site_services, service, data) -> None:
    site_services.client.async_get_website_restrictions.side_effect = RuntimeError("HTTP 503")

    with pytest.raises(HomeAssistantError, match="Reading the site lists failed: HTTP 503"):
        await _call(hass, service, {"child_id": CHILD, **data})


async def test_remove_site_removes_manual_entries_with_their_type(hass, site_services) -> None:
    result = await _call(hass, "remove_site", {"child_id": CHILD, "sites": ["manual.example", "*.wikipedia.*", "other.example"]})

    remove = site_services.client.async_update_website_restrictions.await_args.kwargs["remove"]
    assert remove == [("manual.example", "BLOCK"), ("*.wikipedia.*", "ALLOW")]
    assert result["not_listed"] == ["other.example"]


async def test_sync_adds_new_domains_and_removes_only_what_it_pushed(hass, site_services, aioclient_mock) -> None:
    update = site_services.client.async_update_website_restrictions
    lists = site_services.client.async_get_website_restrictions

    # First sync: a and b are new; the manual entry and the approved site are left alone
    aioclient_mock.get(LIST_URL, text="# list\na.example\nb.example\nwikipedia.org\n")
    lists.return_value = {"filter_level": "safeSites", "approved": ["*.wikipedia.org"], "blocked": ["manual.example"]}
    first = await _call(hass, "sync_site_list", {"child_id": CHILD, "url": LIST_URL})

    inserted = [p for p, _ in update.await_args.kwargs["insert"]]
    # wikipedia.org is skipped whole: blocking it would beat the approved *.wikipedia.org
    assert inserted == ["*.a.example", "a.example", "*.b.example", "b.example"]
    assert update.await_args.kwargs["remove"] == []
    assert first["skipped_approved"] == ["wikipedia.org"]

    # Second sync: b dropped from the list; it is removed, the manual entry is not
    aioclient_mock.clear_requests()
    aioclient_mock.get(LIST_URL, text="a.example\nwikipedia.org\n")
    lists.return_value = {
        "filter_level": "safeSites",
        "approved": ["*.wikipedia.org"],
        "blocked": ["manual.example", "*.a.example", "a.example", "*.b.example", "b.example"],
    }
    second = await _call(hass, "sync_site_list", {"child_id": CHILD, "url": LIST_URL})

    assert update.await_args.kwargs["insert"] == []
    assert sorted(p for p, _ in update.await_args.kwargs["remove"]) == ["*.b.example", "b.example"]
    assert second["removed"] == ["*.b.example", "b.example"]
    assert second["removed_count"] == 2


async def test_sync_refuses_a_list_over_the_cap(hass, site_services, aioclient_mock) -> None:
    aioclient_mock.get(LIST_URL, text="\n".join(f"d{i}.example" for i in range(5)))

    with pytest.raises(HomeAssistantError, match="more than max_domains"):
        await _call(hass, "sync_site_list", {"child_id": CHILD, "url": LIST_URL, "max_domains": 3})

    site_services.client.async_update_website_restrictions.assert_not_called()


async def test_sync_stop_removes_what_the_list_added_and_forgets_it(hass, site_services, aioclient_mock) -> None:
    update = site_services.client.async_update_website_restrictions
    lists = site_services.client.async_get_website_restrictions
    aioclient_mock.get(LIST_URL, text="a.example\n")
    lists.return_value = {"filter_level": "safeSites", "approved": [], "blocked": ["manual.example"]}
    await _call(hass, "sync_site_list", {"child_id": CHILD, "url": LIST_URL})

    lists.return_value = {"filter_level": "safeSites", "approved": [], "blocked": ["manual.example", "*.a.example", "a.example"]}
    stopped = await _call(hass, "sync_site_list", {"child_id": CHILD, "url": LIST_URL, "stop": True})

    assert sorted(p for p, _ in update.await_args.kwargs["remove"]) == ["*.a.example", "a.example"]
    assert stopped["removed_count"] == 2
    # Forgotten: a second stop has nothing to remove and makes no call
    calls = update.await_count
    again = await _call(hass, "sync_site_list", {"child_id": CHILD, "url": LIST_URL, "stop": True})
    assert again["removed_count"] == 0
    assert update.await_count == calls


# --- sensors ------------------------------------------------------------------


def _sensor_coordinator(websites) -> SimpleNamespace:
    return SimpleNamespace(
        data={"children_data": [{"child_id": CHILD, "websites": websites}]},
        child_device_ids={},
        last_update_success=True,
    )


def test_sensors_show_count_sorted_sites_and_filter_level() -> None:
    coordinator = _sensor_coordinator(
        {"filter_level": "safeSites", "approved": ["*.wikipedia.*"], "blocked": ["b.example", "*.a.example"]}
    )
    blocked = FamilyLinkWebsitesSensor(coordinator, CHILD, "Alex", "blocked")
    approved = FamilyLinkWebsitesSensor(coordinator, CHILD, "Alex", "approved")

    assert blocked.unique_id == f"{DOMAIN}_{CHILD}_blocked_sites"
    assert blocked.name == "Alex Blocked Sites"
    assert blocked.available
    assert blocked.native_value == 2
    assert blocked.extra_state_attributes == {
        "child_id": CHILD,
        "child_name": "Alex",
        "filter_level": "safeSites",
        "count": 2,
        "sites": ["*.a.example", "b.example"],
    }
    assert approved.native_value == 1
    assert approved.extra_state_attributes["sites"] == ["*.wikipedia.*"]


def test_sensors_are_unavailable_until_the_lists_are_read() -> None:
    sensor = FamilyLinkWebsitesSensor(_sensor_coordinator(None), CHILD, "Alex", "blocked")
    assert not sensor.available
    assert sensor.native_value is None

    other_child = FamilyLinkWebsitesSensor(_sensor_coordinator({"blocked": []}), "child-2", "Sam", "blocked")
    assert not other_child.available


def test_an_empty_list_counts_zero() -> None:
    sensor = FamilyLinkWebsitesSensor(_sensor_coordinator({"filter_level": "safeSites"}), CHILD, "Alex", "approved")
    assert sensor.available
    assert sensor.native_value == 0
    assert sensor.extra_state_attributes["sites"] == []


def test_a_long_list_is_truncated_in_the_attributes_but_counted_in_full() -> None:
    sites = [f"*.site-{i:04d}.example" for i in range(2000)]
    sensor = FamilyLinkWebsitesSensor(_sensor_coordinator({"blocked": sites}), CHILD, "Alex", "blocked")

    attrs = sensor.extra_state_attributes
    assert sensor.native_value == 2000
    assert attrs["count"] == 2000
    assert attrs["truncated"] is True
    assert 0 < len(attrs["sites"]) < 2000
    assert attrs["sites"] == sorted(sites)[: len(attrs["sites"])]


# --- coordinator --------------------------------------------------------------


def _websites_coordinator(read) -> FamilyLinkDataUpdateCoordinator:
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator._websites = {}
    coordinator.client = SimpleNamespace(async_get_website_restrictions=AsyncMock(side_effect=read))
    return coordinator


async def test_coordinator_reads_the_lists_at_most_every_refresh_interval(monkeypatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr("custom_components.familylink.coordinator.time", SimpleNamespace(monotonic=lambda: clock[0]))
    lists = {"filter_level": "safeSites", "approved": [], "blocked": ["a.example"]}
    coordinator = _websites_coordinator([lists, {**lists, "blocked": ["b.example"]}])

    assert await coordinator._async_child_websites(CHILD, "Alex") == lists
    clock[0] += WEBSITES_REFRESH - 1
    assert await coordinator._async_child_websites(CHILD, "Alex") == lists
    assert coordinator.client.async_get_website_restrictions.await_count == 1

    clock[0] += 2
    assert (await coordinator._async_child_websites(CHILD, "Alex"))["blocked"] == ["b.example"]
    assert coordinator.client.async_get_website_restrictions.await_count == 2


async def test_coordinator_keeps_the_last_lists_when_a_read_fails(monkeypatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr("custom_components.familylink.coordinator.time", SimpleNamespace(monotonic=lambda: clock[0]))
    lists = {"filter_level": "safeSites", "approved": [], "blocked": ["a.example"]}
    coordinator = _websites_coordinator([HomeAssistantError("HTTP 503"), lists, HomeAssistantError("HTTP 503")])

    # No lists yet: the sensors stay unavailable
    assert await coordinator._async_child_websites(CHILD, "Alex") is None
    assert await coordinator._async_child_websites(CHILD, "Alex") == lists
    clock[0] += WEBSITES_REFRESH + 1
    assert await coordinator._async_child_websites(CHILD, "Alex") == lists


async def test_coordinator_passes_on_an_expired_session() -> None:
    coordinator = _websites_coordinator([SessionExpiredError("expired")])
    with pytest.raises(SessionExpiredError):
        await coordinator._async_child_websites(CHILD, "Alex")


def test_a_change_made_from_home_assistant_updates_the_sensors_without_a_read() -> None:
    coordinator = _websites_coordinator([])
    coordinator.store_websites(CHILD, {"filter_level": "safeSites", "approved": [], "blocked": ["a.example"], "covered": {}})
    assert coordinator._websites[CHILD][1] == {"filter_level": "safeSites", "approved": [], "blocked": ["a.example"]}
    coordinator.client.async_get_website_restrictions.assert_not_awaited()
