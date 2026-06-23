"""Tests for the Family Link auth add-on cookie client."""
from __future__ import annotations

import json

from cryptography.fernet import Fernet

from custom_components.familylink.auth.addon_client import AddonCookieClient


class FakeResponse:
	"""Async response context manager for aiohttp calls."""

	def __init__(self, status: int, payload: dict[str, object] | None = None) -> None:
		self.status = status
		self._payload = payload or {}

	async def __aenter__(self):
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		return None

	async def json(self):
		return self._payload


class FakeSession:
	"""Async session context manager that records GET calls."""

	calls: list[dict[str, object]] = []
	status = 200
	payload: dict[str, object] = {"cookies": [{"name": "SAPISID", "value": "cookie"}]}

	async def __aenter__(self):
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		return None

	def get(self, url, **kwargs):
		self.calls.append({"url": url, **kwargs})
		return FakeResponse(self.status, self.payload)


def _patch_client_session(monkeypatch, status=200, payload=None):
	FakeSession.calls = []
	FakeSession.status = status
	FakeSession.payload = payload or {"cookies": [{"name": "SAPISID", "value": "cookie"}]}
	monkeypatch.setattr(
		"custom_components.familylink.auth.addon_client.aiohttp.ClientSession",
		FakeSession,
	)


async def test_auth_url_strips_api_key_and_uses_it_for_cookie_fetch(hass, monkeypatch):
	"""Auth URLs may carry ?api_key, but API calls use the stripped base URL."""
	_patch_client_session(monkeypatch)
	client = AddonCookieClient(
		hass,
		auth_url="http://familylink-auth.local:8099?api_key=test-key",
	)

	cookies = await client._fetch_cookies_from_url(client.auth_url)

	assert client.auth_url == "http://familylink-auth.local:8099"
	assert cookies == [{"name": "SAPISID", "value": "cookie"}]
	assert FakeSession.calls == [
		{
			"url": "http://familylink-auth.local:8099/api/cookies",
			"headers": {"X-API-Key": "test-key"},
			"timeout": FakeSession.calls[0]["timeout"],
		}
	]


async def test_cookie_fetch_records_403_invalid_api_key(hass, monkeypatch):
	"""A 403 response returns no cookies and leaves last_fetch_status for callers."""
	_patch_client_session(monkeypatch, status=403, payload={})
	client = AddonCookieClient(hass, auth_url="http://familylink-auth.local:8099")

	assert await client._fetch_cookies_from_url(client.auth_url) is None
	assert client.last_fetch_status == 403


async def test_encrypted_storage_path_uses_configured_share_dir(
	hass, monkeypatch, tmp_path
):
	"""Encrypted cookie fallback reads from the patched share directory only."""
	monkeypatch.setattr(AddonCookieClient, "SHARE_DIR", tmp_path)
	key = Fernet.generate_key()
	cookies = [{"name": "SAPISID", "value": "cookie"}]
	(tmp_path / AddonCookieClient.KEY_FILE).write_bytes(key)
	(tmp_path / AddonCookieClient.COOKIE_FILE).write_bytes(
		Fernet(key).encrypt(json.dumps({"cookies": cookies}).encode())
	)
	client = AddonCookieClient(hass)

	assert client.storage_path == tmp_path / AddonCookieClient.COOKIE_FILE
	assert await client._load_cookies_from_file() == cookies
