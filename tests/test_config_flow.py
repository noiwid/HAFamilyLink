"""Tests for the Family Link config flow."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.familylink.const import (
	CONF_AUTH_URL,
	CONF_ENABLE_LOCATION_TRACKING,
	CONF_SCHEDULE_TIMEZONE,
	CONF_TIMEOUT,
	CONF_UPDATE_INTERVAL,
	DOMAIN,
	INTEGRATION_NAME,
)

from conftest import TEST_AUTH_URL


class MockAddonCookieClient:
	"""Flow-facing auth client mock."""

	detected_source = "api"
	detected_url = "http://familylink-auth.local:8099"
	url_available = True
	cookies: list[dict[str, str]] | None = [{"name": "SAPISID", "value": "cookie"}]
	fetch_status = 200
	load_error: Exception | None = None

	def __init__(self, hass, auth_url=None):
		self.hass = hass
		self.auth_url = auth_url
		self.last_fetch_status: int | None = None

	async def detect_auth_source(self):
		return self.detected_source, self.detected_url

	async def _check_url_available(self, url):
		return self.url_available

	async def _fetch_cookies_from_url(self, url):
		self.last_fetch_status = self.fetch_status
		return self.cookies

	async def load_cookies(self):
		if self.load_error is not None:
			raise self.load_error
		return self.cookies


def _patch_addon_client(monkeypatch, **overrides):
	for name, value in {
		"detected_source": "api",
		"detected_url": "http://familylink-auth.local:8099",
		"url_available": True,
		"cookies": [{"name": "SAPISID", "value": "cookie"}],
		"fetch_status": 200,
		"load_error": None,
		**overrides,
	}.items():
		setattr(MockAddonCookieClient, name, value)
	monkeypatch.setattr(
		"custom_components.familylink.auth.addon_client.AddonCookieClient",
		MockAddonCookieClient,
	)


async def _start_manual_url_flow(hass):
	result = await hass.config_entries.flow.async_init(
		DOMAIN, context={"source": config_entries.SOURCE_USER}
	)
	assert result["type"] is FlowResultType.MENU
	return await hass.config_entries.flow.async_configure(
		result["flow_id"], {"next_step_id": "manual_url"}
	)


async def _submit_valid_manual_url(hass, result):
	return await hass.config_entries.flow.async_configure(
		result["flow_id"], {CONF_AUTH_URL: TEST_AUTH_URL}
	)


async def test_user_flow_manual_url_happy_path(hass, monkeypatch):
	"""Exercise manual URL validation and final entry creation."""
	_patch_addon_client(monkeypatch)

	result = await _start_manual_url_flow(hass)
	assert result["type"] is FlowResultType.FORM
	assert result["step_id"] == "manual_url"

	result = await _submit_valid_manual_url(hass, result)
	assert result["type"] is FlowResultType.FORM
	assert result["step_id"] == "configure"

	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{
			CONF_NAME: INTEGRATION_NAME,
			CONF_UPDATE_INTERVAL: 60,
			CONF_TIMEOUT: 30,
			CONF_ENABLE_LOCATION_TRACKING: True,
			CONF_SCHEDULE_TIMEZONE: "UTC",
		},
	)

	assert result["type"] is FlowResultType.CREATE_ENTRY
	assert result["title"] == INTEGRATION_NAME
	assert result["data"][CONF_AUTH_URL] == TEST_AUTH_URL
	assert result["data"][CONF_SCHEDULE_TIMEZONE] == "UTC"


async def test_manual_url_requires_url(hass, monkeypatch):
	"""Reject blank manual auth URLs before trying to connect."""
	_patch_addon_client(monkeypatch)

	result = await _start_manual_url_flow(hass)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {CONF_AUTH_URL: " "}
	)

	assert result["type"] is FlowResultType.FORM
	assert result["errors"] == {"base": "url_required"}


async def test_manual_url_reports_cannot_connect(hass, monkeypatch):
	"""Report unreachable auth containers as cannot_connect."""
	_patch_addon_client(monkeypatch, url_available=False)

	result = await _start_manual_url_flow(hass)
	result = await _submit_valid_manual_url(hass, result)

	assert result["type"] is FlowResultType.FORM
	assert result["errors"] == {"base": "cannot_connect"}


async def test_manual_url_reports_invalid_api_key(hass, monkeypatch):
	"""A 403 from /api/cookies becomes the targeted invalid API key error."""
	_patch_addon_client(monkeypatch, cookies=None, fetch_status=403)

	result = await _start_manual_url_flow(hass)
	result = await _submit_valid_manual_url(hass, result)

	assert result["type"] is FlowResultType.FORM
	assert result["errors"] == {"base": "invalid_api_key"}


async def test_auto_detect_without_source_falls_back_to_manual_url(hass, monkeypatch):
	"""Auto-detect sends users to manual URL when no auth source is available."""
	_patch_addon_client(monkeypatch, detected_source="none", detected_url=None)

	result = await hass.config_entries.flow.async_init(
		DOMAIN, context={"source": config_entries.SOURCE_USER}
	)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"], {"next_step_id": "auto_detect"}
	)

	assert result["type"] is FlowResultType.FORM
	assert result["step_id"] == "manual_url"
	assert result["errors"] == {}


async def test_manual_url_reports_no_cookies(hass, monkeypatch):
	"""Reachable auth containers without cookies show the no_cookies error."""
	_patch_addon_client(monkeypatch, cookies=None, fetch_status=200)

	result = await _start_manual_url_flow(hass)
	result = await _submit_valid_manual_url(hass, result)

	assert result["type"] is FlowResultType.FORM
	assert result["errors"] == {"base": "no_cookies"}


async def test_configure_reports_invalid_auth(hass, monkeypatch):
	"""Missing cookies at configure time become invalid_auth."""
	_patch_addon_client(monkeypatch, cookies=[{"name": "SAPISID", "value": "cookie"}])

	result = await _start_manual_url_flow(hass)
	result = await _submit_valid_manual_url(hass, result)
	_patch_addon_client(monkeypatch, cookies=None)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{
			CONF_NAME: INTEGRATION_NAME,
			CONF_UPDATE_INTERVAL: 60,
			CONF_TIMEOUT: 30,
			CONF_ENABLE_LOCATION_TRACKING: False,
			CONF_SCHEDULE_TIMEZONE: "",
		},
	)

	assert result["type"] is FlowResultType.FORM
	assert result["errors"] == {"base": "invalid_auth"}


async def test_configure_reports_cannot_connect(hass, monkeypatch):
	"""Unexpected validation failures become cannot_connect on the form."""
	_patch_addon_client(monkeypatch)

	result = await _start_manual_url_flow(hass)
	result = await _submit_valid_manual_url(hass, result)
	_patch_addon_client(monkeypatch, load_error=RuntimeError("boom"))
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{
			CONF_NAME: INTEGRATION_NAME,
			CONF_UPDATE_INTERVAL: 60,
			CONF_TIMEOUT: 30,
			CONF_ENABLE_LOCATION_TRACKING: False,
			CONF_SCHEDULE_TIMEZONE: "",
		},
	)

	assert result["type"] is FlowResultType.FORM
	assert result["errors"] == {"base": "cannot_connect"}


async def test_configure_rejects_invalid_schedule_timezone(hass, monkeypatch):
	"""Invalid schedule timezone values stay on the configure form."""
	_patch_addon_client(monkeypatch)

	result = await _start_manual_url_flow(hass)
	result = await _submit_valid_manual_url(hass, result)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{
			CONF_NAME: INTEGRATION_NAME,
			CONF_UPDATE_INTERVAL: 60,
			CONF_TIMEOUT: 30,
			CONF_ENABLE_LOCATION_TRACKING: False,
			CONF_SCHEDULE_TIMEZONE: "Not/AZone",
		},
	)

	assert result["type"] is FlowResultType.FORM
	assert result["step_id"] == "configure"
	assert result["errors"] == {CONF_SCHEDULE_TIMEZONE: "invalid_timezone"}


async def test_duplicate_entry_aborts(hass, monkeypatch):
	"""Prevent adding the same auth source twice."""
	_patch_addon_client(monkeypatch)
	MockConfigEntry(
		domain=DOMAIN,
		title=INTEGRATION_NAME,
		data={CONF_AUTH_URL: TEST_AUTH_URL},
		unique_id=TEST_AUTH_URL,
	).add_to_hass(hass)

	result = await _start_manual_url_flow(hass)
	result = await _submit_valid_manual_url(hass, result)
	result = await hass.config_entries.flow.async_configure(
		result["flow_id"],
		{
			CONF_NAME: INTEGRATION_NAME,
			CONF_UPDATE_INTERVAL: 60,
			CONF_TIMEOUT: 30,
			CONF_ENABLE_LOCATION_TRACKING: False,
			CONF_SCHEDULE_TIMEZONE: "",
		},
	)

	assert result["type"] is FlowResultType.ABORT
	assert result["reason"] == "already_configured"


async def test_import_success_creates_entry(hass, monkeypatch):
	"""Valid YAML imports create a config entry."""
	_patch_addon_client(monkeypatch)

	result = await hass.config_entries.flow.async_init(
		DOMAIN,
		context={"source": config_entries.SOURCE_IMPORT},
		data={
			CONF_NAME: "Imported Family Link",
			CONF_UPDATE_INTERVAL: 120,
			CONF_TIMEOUT: 45,
			CONF_ENABLE_LOCATION_TRACKING: True,
			CONF_SCHEDULE_TIMEZONE: "UTC",
		},
	)

	assert result["type"] is FlowResultType.CREATE_ENTRY
	assert result["title"] == "Imported Family Link"
	assert result["data"][CONF_SCHEDULE_TIMEZONE] == "UTC"


async def test_import_invalid_config_aborts(hass, monkeypatch):
	"""The supported YAML import path aborts invalid auth cleanly."""
	_patch_addon_client(monkeypatch, cookies=None)

	result = await hass.config_entries.flow.async_init(
		DOMAIN,
		context={"source": config_entries.SOURCE_IMPORT},
		data={CONF_NAME: INTEGRATION_NAME},
	)

	assert result["type"] is FlowResultType.ABORT
	assert result["reason"] == "invalid_config"


async def test_options_flow_updates_options_and_rejects_invalid_timezone(hass):
	"""Options flow validates timezone and saves normalized option values."""
	entry = MockConfigEntry(
		domain=DOMAIN,
		title=INTEGRATION_NAME,
		data={
			CONF_UPDATE_INTERVAL: 60,
			CONF_TIMEOUT: 30,
			CONF_ENABLE_LOCATION_TRACKING: False,
			CONF_SCHEDULE_TIMEZONE: "",
		},
	)
	entry.add_to_hass(hass)

	result = await hass.config_entries.options.async_init(entry.entry_id)
	result = await hass.config_entries.options.async_configure(
		result["flow_id"],
		{
			CONF_UPDATE_INTERVAL: 90,
			CONF_TIMEOUT: 40,
			CONF_ENABLE_LOCATION_TRACKING: True,
			CONF_SCHEDULE_TIMEZONE: "Not/AZone",
		},
	)

	assert result["type"] is FlowResultType.FORM
	assert result["errors"] == {CONF_SCHEDULE_TIMEZONE: "invalid_timezone"}

	result = await hass.config_entries.options.async_init(entry.entry_id)
	result = await hass.config_entries.options.async_configure(
		result["flow_id"],
		{
			CONF_UPDATE_INTERVAL: 90,
			CONF_TIMEOUT: 40,
			CONF_ENABLE_LOCATION_TRACKING: True,
			CONF_SCHEDULE_TIMEZONE: " UTC ",
		},
	)

	assert result["type"] is FlowResultType.CREATE_ENTRY
	assert result["data"] == {
		CONF_UPDATE_INTERVAL: 90,
		CONF_TIMEOUT: 40,
		CONF_ENABLE_LOCATION_TRACKING: True,
		CONF_SCHEDULE_TIMEZONE: "UTC",
	}
