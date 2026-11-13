"""The same Google cookie from several domains: .google.com wins over regional TLDs (#92).

The Cookie header and the SAPISIDHASH must both use the .google.com SAPISID,
or Google answers 401 and the integration loops on re-authentication.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.familylink.client.api import FamilyLinkClient, _domain_priority


@pytest.mark.parametrize(
    ("domain", "rank"),
    [(".google.com", 0), ("google.com", 0), ("accounts.google.com", 1), (".google.com.au", 2), (".google.co.uk", 2)],
)
def test_domain_priority(domain: str, rank: int) -> None:
    assert _domain_priority(domain) == rank


def _client(cookies: list[dict]) -> FamilyLinkClient:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client._cookies = cookies
    return client


COOKIES = [
    {"name": "SAPISID", "value": "regional", "domain": ".google.com.au"},
    {"name": "SAPISID", "value": "main", "domain": ".google.com"},
    {"name": "SID", "value": "sid", "domain": ".google.com.au"},
]


def test_cookie_header_uses_the_google_com_value_whatever_the_order() -> None:
    assert _client(COOKIES)._get_cookies_dict() == {"SAPISID": "main", "SID": "sid"}
    assert _client(list(reversed(COOKIES)))._get_cookies_dict() == {"SAPISID": "main", "SID": "sid"}


async def test_sapisidhash_uses_the_google_com_value() -> None:
    import asyncio

    client = _client(COOKIES)
    client._session = None
    client._session_lock = asyncio.Lock()
    client.request_timeout = 30
    with patch.object(FamilyLinkClient, "_generate_sapisidhash", MagicMock(return_value="h")) as sign, patch(
        "custom_components.familylink.client.api.aiohttp.ClientSession", MagicMock()
    ):
        await client._get_session()
    assert sign.call_args.args[0] == "main"
