"""Config flow for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
	CONF_AUTH_URL,
	CONF_ENABLE_LOCATION_TRACKING,
	CONF_TIMEOUT,
	CONF_UPDATE_INTERVAL,
	DEFAULT_TIMEOUT,
	DEFAULT_UPDATE_INTERVAL,
	DOMAIN,
	INTEGRATION_NAME,
	LOGGER_NAME,
)
from .exceptions import AuthenticationError

_LOGGER = logging.getLogger(LOGGER_NAME)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
	"""Validate the user input allows us to connect."""
	from .auth.addon_client import AddonCookieClient

	# Get auth URL from data if provided
	auth_url = data.get(CONF_AUTH_URL)

	try:
		addon_client = AddonCookieClient(hass, auth_url=auth_url)

		# Try to load cookies
		cookies = await addon_client.load_cookies()

		if not cookies:
			raise AuthenticationError(
				"No cookies found. Please authenticate first using the Family Link Auth add-on or container."
			)

		# Return info to store in config entry
		return {
			"title": data.get(CONF_NAME, INTEGRATION_NAME),
			"cookies": cookies,
		}

	except AuthenticationError as err:
		_LOGGER.error("Authentication failed: %s", err)
		raise InvalidAuth from err
	except Exception as err:
		_LOGGER.exception("Unexpected error during validation")
		raise CannotConnect from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
	"""Handle a config flow for Google Family Link."""

	VERSION = 1

	def __init__(self) -> None:
		"""Initialize config flow."""
		self._detected_source: str | None = None
		self._detected_url: str | None = None

	async def async_step_user(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Handle the initial step - detect auth source."""
		from .auth.addon_client import AddonCookieClient

		# Detect available auth source
		addon_client = AddonCookieClient(self.hass)
		source_type, detected_url = await addon_client.detect_auth_source()

		self._detected_source = source_type
		self._detected_url = detected_url

		_LOGGER.debug(f"Detected auth source: {source_type}, URL: {detected_url}")

		if source_type == "none":
			# No auto-detection possible, ask for URL
			return await self.async_step_manual_url()

		# Auto-detected, proceed with standard form
		return await self.async_step_configure(user_input)

	async def async_step_manual_url(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Handle manual URL configuration for Docker standalone."""
		errors: dict[str, str] = {}

		if user_input is not None:
			# Validate the provided URL
			auth_url = user_input.get(CONF_AUTH_URL, "").strip()

			if not auth_url:
				errors["base"] = "url_required"
			else:
				from .auth.addon_client import AddonCookieClient

				addon_client = AddonCookieClient(self.hass, auth_url=auth_url)

				# Check if URL is reachable
				if await addon_client._check_url_available(auth_url):
					# Check if cookies are available
					cookies = await addon_client._fetch_cookies_from_url(auth_url)
					if cookies:
						self._detected_url = auth_url
						# Proceed to configure step with URL
						return await self.async_step_configure(None, auth_url=auth_url)
					else:
						errors["base"] = "no_cookies"
				else:
					errors["base"] = "cannot_connect"

		# Show URL input form
		return self.async_show_form(
			step_id="manual_url",
			data_schema=vol.Schema({
				vol.Required(CONF_AUTH_URL, default="http://192.168.1.x:8099"): str,
			}),
			errors=errors,
			description_placeholders={
				"default_url": "http://localhost:8099",
			},
		)

	async def async_step_configure(
		self, user_input: dict[str, Any] | None = None, auth_url: str | None = None
	) -> FlowResult:
		"""Handle configuration step."""
		errors: dict[str, str] = {}

		# Use passed auth_url or detected URL
		if auth_url is None:
			auth_url = self._detected_url

		if user_input is not None:
			# Add auth_url to data if we have one
			if auth_url:
				user_input[CONF_AUTH_URL] = auth_url

			try:
				info = await validate_input(self.hass, user_input)
				return self.async_create_entry(title=info["title"], data=user_input)

			except CannotConnect:
				errors["base"] = "cannot_connect"
			except InvalidAuth:
				errors["base"] = "invalid_auth"
			except Exception:
				_LOGGER.exception("Unexpected exception")
				errors["base"] = "unknown"

		# Build schema
		schema = vol.Schema({
			vol.Required(CONF_NAME, default=INTEGRATION_NAME): str,
			vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
				vol.Coerce(int), vol.Range(min=30, max=3600)
			),
			vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
				vol.Coerce(int), vol.Range(min=10, max=120)
			),
			vol.Optional(CONF_ENABLE_LOCATION_TRACKING, default=False): bool,
		})

		# Add description about detected source
		description_placeholders = {}
		if self._detected_source == "api":
			description_placeholders["auth_source"] = f"API ({self._detected_url})"
		elif self._detected_source == "file":
			description_placeholders["auth_source"] = "Local file (/share/familylink/)"
		else:
			description_placeholders["auth_source"] = auth_url or "Manual URL"

		return self.async_show_form(
			step_id="configure",
			data_schema=schema,
			errors=errors,
			description_placeholders=description_placeholders,
		)

	async def async_step_import(self, import_info: dict[str, Any]) -> FlowResult:
		"""Handle import from configuration.yaml."""
		await self.async_set_unique_id(DOMAIN)
		self._abort_if_unique_id_configured()

		try:
			info = await validate_input(self.hass, import_info)
			return self.async_create_entry(title=info["title"], data=import_info)
		except (CannotConnect, InvalidAuth):
			return self.async_abort(reason="invalid_config")


class CannotConnect(HomeAssistantError):
	"""Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
	"""Error to indicate there is invalid auth."""
