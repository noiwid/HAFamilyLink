"""Tests for secret-free transport to the authentication service."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from custom_components.familylink.auth import addon_client
from custom_components.familylink.client import api as familylink_api
from custom_components.familylink.const import (
    AUTH_SOURCE_MANAGED,
    AUTH_SOURCE_MANUAL,
    CONF_API_KEY,
    CONF_AUTH_SOURCE,
    CONF_AUTH_URL,
)
from custom_components.familylink.exceptions import AuthenticationError

FAKE_API_KEY = "test-api-key-not-a-real-secret"
FAKE_AUTH_URL = "http://auth.invalid:8099"
FAKE_PREFIXED_AUTH_URL = f"{FAKE_AUTH_URL}/familylink-auth"


class _Response:
    status = 200

    async def json(self):
        return {"cookies": [{"name": "TEST_SESSION", "value": "fake-value"}]}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


class _MalformedResponse(_Response):
    async def json(self):
        return {"cookies": "not-a-list"}


class _Session:
    def __init__(self, requests: list[tuple[str, dict]]) -> None:
        self.requests = requests

    def get(self, url: str, **kwargs):
        self.requests.append((url, kwargs))
        return _Response()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


async def test_health_probe_does_not_follow_redirects(hass, monkeypatch) -> None:
    """Availability checks and credentialed requests use the same origin policy."""
    requests: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        addon_client.aiohttp,
        "ClientSession",
        lambda: _Session(requests),
    )
    client = addon_client.AddonCookieClient(hass)

    assert await client._check_url_available(FAKE_AUTH_URL)
    assert requests == [
        (
            f"{FAKE_AUTH_URL}/api/health",
            {
                "timeout": addon_client.aiohttp.ClientTimeout(total=5),
                "allow_redirects": False,
            },
        )
    ]


async def test_separate_key_is_sent_only_as_header(
    hass,
    monkeypatch,
    caplog,
) -> None:
    """A separate key must be used only in the outbound request header."""
    requests: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        addon_client.aiohttp,
        "ClientSession",
        lambda: _Session(requests),
    )
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=f"{FAKE_AUTH_URL}/",
        api_key=f" {FAKE_API_KEY} ",
    )

    with caplog.at_level(logging.DEBUG):
        cookies = await client._fetch_cookies_from_url(
            client.auth_url,
            api_key=client._api_key,
        )

    assert cookies
    assert client.auth_url == FAKE_AUTH_URL
    assert requests == [
        (
            f"{FAKE_AUTH_URL}/api/cookies",
            {
                "headers": {"X-API-Key": FAKE_API_KEY},
                "timeout": addon_client.aiohttp.ClientTimeout(total=10),
                "allow_redirects": False,
            },
        )
    ]
    assert FAKE_API_KEY not in requests[0][0]
    assert FAKE_API_KEY not in caplog.text
    assert "api_key=" not in caplog.text


async def test_auth_url_path_is_preserved_for_reverse_proxy(
    hass,
    monkeypatch,
) -> None:
    """A configured path is a base-path prefix, not discarded URL metadata."""
    requests: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        addon_client.aiohttp,
        "ClientSession",
        lambda: _Session(requests),
    )
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=f"{FAKE_PREFIXED_AUTH_URL}/",
        api_key=FAKE_API_KEY,
        auth_source=AUTH_SOURCE_MANUAL,
    )

    assert await client.load_cookies()
    assert client.auth_url == FAKE_PREFIXED_AUTH_URL
    assert requests[0][0] == f"{FAKE_PREFIXED_AUTH_URL}/api/cookies"


async def test_manual_validation_reports_connection_failure(
    hass,
    monkeypatch,
) -> None:
    """The public validation API distinguishes an unreachable endpoint."""
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=FAKE_AUTH_URL,
        auth_source=AUTH_SOURCE_MANUAL,
    )
    monkeypatch.setattr(client, "_check_url_available", AsyncMock(return_value=False))

    with pytest.raises(addon_client.AuthServerConnectionError):
        await client.async_validate_manual_endpoint()


async def test_manual_validation_reports_rejected_key(
    hass,
    monkeypatch,
) -> None:
    """The public validation API distinguishes an API-key rejection."""
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=FAKE_AUTH_URL,
        api_key=FAKE_API_KEY,
        auth_source=AUTH_SOURCE_MANUAL,
    )
    monkeypatch.setattr(client, "_check_url_available", AsyncMock(return_value=True))

    async def _rejected(_url, *, api_key=None):
        assert api_key == FAKE_API_KEY
        client.last_fetch_status = 403
        return None

    monkeypatch.setattr(client, "_fetch_cookies_from_url", _rejected)

    with pytest.raises(addon_client.AuthServerApiKeyError):
        await client.async_validate_manual_endpoint()


async def test_manual_validation_reports_missing_cookies(
    hass,
    monkeypatch,
) -> None:
    """The public validation API distinguishes an empty cookie endpoint."""
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=FAKE_AUTH_URL,
        auth_source=AUTH_SOURCE_MANUAL,
    )
    monkeypatch.setattr(client, "_check_url_available", AsyncMock(return_value=True))

    async def _empty(_url, *, api_key=None):
        client.last_fetch_status = 404
        return None

    monkeypatch.setattr(client, "_fetch_cookies_from_url", _empty)

    with pytest.raises(addon_client.AuthServerCookiesUnavailable):
        await client.async_validate_manual_endpoint()


async def test_malformed_cookie_response_is_rejected(hass, monkeypatch) -> None:
    """A malformed success response cannot become cookie state."""
    class _MalformedSession(_Session):
        def get(self, url: str, **kwargs):
            self.requests.append((url, kwargs))
            return _MalformedResponse()

    monkeypatch.setattr(
        addon_client.aiohttp,
        "ClientSession",
        lambda: _MalformedSession([]),
    )
    client = addon_client.AddonCookieClient(hass)

    assert await client._fetch_cookies_from_url(FAKE_AUTH_URL) is None


def test_query_credentials_are_rejected_by_runtime_client(hass) -> None:
    """Legacy query parsing belongs to migration, not normal client setup."""
    with pytest.raises(ValueError, match="query"):
        addon_client.AddonCookieClient(
            hass,
            auth_url=f"{FAKE_AUTH_URL}?api_key={FAKE_API_KEY}",
        )


@pytest.mark.parametrize(
    "auth_url",
    [
        "ftp://auth.invalid:8099",
        "http://user:password@auth.invalid:8099",
        "http://auth.invalid:8099/#fragment",
        "not-a-url",
    ],
)
def test_unsafe_auth_urls_are_rejected(hass, auth_url: str) -> None:
    """Authentication URLs cannot embed credentials or unsupported parts."""
    with pytest.raises(ValueError):
        addon_client.AddonCookieClient(hass, auth_url=auth_url, api_key=FAKE_API_KEY)


def test_familylink_client_passes_separate_auth_fields(hass, monkeypatch) -> None:
    """Runtime wiring must not rebuild a credential-bearing URL."""
    captured: dict[str, str | None] = {}

    class _AddonClient:
        def __init__(
            self,
            _hass,
            auth_url=None,
            api_key=None,
            auth_source=None,
        ) -> None:
            captured.update(
                auth_url=auth_url,
                api_key=api_key,
                auth_source=auth_source,
            )

    monkeypatch.setattr(familylink_api, "AddonCookieClient", _AddonClient)

    familylink_api.FamilyLinkClient(
        hass,
        {
            CONF_AUTH_URL: FAKE_AUTH_URL,
            CONF_API_KEY: FAKE_API_KEY,
            CONF_AUTH_SOURCE: AUTH_SOURCE_MANUAL,
        },
    )

    assert captured == {
        "auth_url": FAKE_AUTH_URL,
        "api_key": FAKE_API_KEY,
        "auth_source": AUTH_SOURCE_MANUAL,
    }


async def test_403_error_does_not_recommend_url_credentials(
    hass,
    monkeypatch,
) -> None:
    """Authentication errors must not send users back to query parameters."""
    client = familylink_api.FamilyLinkClient(
        hass,
        {CONF_AUTH_URL: FAKE_AUTH_URL, CONF_API_KEY: FAKE_API_KEY},
    )
    monkeypatch.setattr(client.addon_client, "load_cookies", _return_none)
    client.addon_client.last_fetch_status = 403

    with pytest.raises(AuthenticationError) as caught:
        await client.async_authenticate()

    message = str(caught.value)
    assert FAKE_API_KEY not in message
    assert "api_key=" not in message


async def test_manual_server_failure_does_not_fall_back_to_other_sources(
    hass,
    monkeypatch,
) -> None:
    """A manual endpoint is authoritative even for non-403 failures."""
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=FAKE_AUTH_URL,
        api_key=FAKE_API_KEY,
    )

    async def _failed(_url, *, api_key=None):
        assert api_key == FAKE_API_KEY
        client.last_fetch_status = None
        return None

    local_api = AsyncMock()
    file_fallback = AsyncMock()
    monkeypatch.setattr(client, "_fetch_cookies_from_url", _failed)
    monkeypatch.setattr(client, "_get_addon_url", local_api)
    monkeypatch.setattr(client, "_load_cookies_from_file", file_fallback)

    assert await client.load_cookies() is None
    local_api.assert_not_awaited()
    file_fallback.assert_not_awaited()


async def test_credentialed_request_does_not_follow_redirects(
    hass,
    monkeypatch,
) -> None:
    """A key cannot cross origins through an HTTP redirect."""
    requests: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        addon_client.aiohttp,
        "ClientSession",
        lambda: _Session(requests),
    )
    client = addon_client.AddonCookieClient(hass)

    assert await client._fetch_cookies_from_url(
        FAKE_AUTH_URL,
        api_key=FAKE_API_KEY,
    )
    assert requests[0][1]["allow_redirects"] is False


async def test_shared_key_is_not_sent_to_manual_remote(
    hass,
    monkeypatch,
) -> None:
    """A key from shared HAOS storage never authenticates a manual URL."""
    client = addon_client.AddonCookieClient(hass, auth_url=FAKE_AUTH_URL)
    shared_key = AsyncMock(return_value=FAKE_API_KEY)
    requests: list[tuple[str, str | None]] = []

    async def _fetch(url, *, api_key=None):
        requests.append((url, api_key))
        return None

    monkeypatch.setattr(client, "_get_shared_api_key", shared_key)
    monkeypatch.setattr(client, "_fetch_cookies_from_url", _fetch)

    assert await client.load_cookies() is None
    assert requests == [(FAKE_AUTH_URL, None)]
    shared_key.assert_not_awaited()


async def test_stored_managed_url_uses_shared_key(
    hass,
    monkeypatch,
) -> None:
    """A migrated HAOS URL can still use its matching shared key."""
    client = addon_client.AddonCookieClient(hass, auth_url=FAKE_AUTH_URL)
    requests: list[tuple[str, str | None]] = []

    async def _fetch(url, *, api_key=None):
        requests.append((url, api_key))
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    monkeypatch.setattr(client, "_get_addon_url", AsyncMock(return_value=FAKE_AUTH_URL))
    monkeypatch.setattr(client, "_get_shared_api_key", AsyncMock(return_value=FAKE_API_KEY))
    monkeypatch.setattr(client, "_fetch_cookies_from_url", _fetch)

    assert await client.load_cookies()
    assert requests == [(FAKE_AUTH_URL, FAKE_API_KEY)]


async def test_rejected_explicit_key_does_not_fall_back_to_other_sources(
    hass,
    monkeypatch,
) -> None:
    """A configured server's 403 must fail closed instead of changing source."""
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=FAKE_AUTH_URL,
        api_key=FAKE_API_KEY,
    )

    async def _rejected(_url, *, api_key=None):
        assert api_key == FAKE_API_KEY
        client.last_fetch_status = 403
        return None

    local_api = AsyncMock()
    file_fallback = AsyncMock()
    monkeypatch.setattr(client, "_fetch_cookies_from_url", _rejected)
    monkeypatch.setattr(client, "_get_addon_url", local_api)
    monkeypatch.setattr(client, "_load_cookies_from_file", file_fallback)

    assert await client.load_cookies() is None
    local_api.assert_not_awaited()
    file_fallback.assert_not_awaited()


async def test_supervisor_endpoint_uses_only_shared_key(
    hass,
    monkeypatch,
) -> None:
    """The shared key is scoped to the Supervisor-resolved add-on."""
    client = addon_client.AddonCookieClient(hass)
    file_fallback = AsyncMock()
    requests: list[tuple[str, str | None]] = []

    async def _fetch(url, *, api_key=None):
        requests.append((url, api_key))
        client.last_fetch_status = 403
        return None

    monkeypatch.setattr(client, "_fetch_cookies_from_url", _fetch)
    monkeypatch.setattr(client, "_get_addon_url", AsyncMock(return_value=FAKE_AUTH_URL))
    monkeypatch.setattr(client, "_get_shared_api_key", AsyncMock(return_value=FAKE_API_KEY))
    monkeypatch.setattr(client, "_load_cookies_from_file", file_fallback)

    assert await client.load_cookies() is None
    assert requests == [(FAKE_AUTH_URL, FAKE_API_KEY)]
    file_fallback.assert_not_awaited()


async def test_managed_source_ignores_stale_manual_credentials(
    hass,
    monkeypatch,
) -> None:
    """Managed mode uses only the current Supervisor endpoint and shared key."""
    stale_url = "http://stale-auth.invalid:8099"
    client = addon_client.AddonCookieClient(
        hass,
        auth_url=stale_url,
        api_key="stale-fake-key",
        auth_source=AUTH_SOURCE_MANAGED,
    )
    requests: list[tuple[str, str | None]] = []

    async def _fetch(url, *, api_key=None):
        requests.append((url, api_key))
        return [{"name": "TEST_SESSION", "value": "fake-value"}]

    monkeypatch.setattr(client, "_get_addon_url", AsyncMock(return_value=FAKE_AUTH_URL))
    monkeypatch.setattr(client, "_get_shared_api_key", AsyncMock(return_value=FAKE_API_KEY))
    monkeypatch.setattr(client, "_fetch_cookies_from_url", _fetch)

    assert await client.load_cookies()
    assert requests == [(FAKE_AUTH_URL, FAKE_API_KEY)]


def test_unknown_auth_source_is_rejected(hass) -> None:
    """Unexpected persisted source markers fail before any request."""
    with pytest.raises(ValueError, match="Unknown authentication source"):
        addon_client.AddonCookieClient(hass, auth_source="unexpected")


async def _return_none():
    return None
