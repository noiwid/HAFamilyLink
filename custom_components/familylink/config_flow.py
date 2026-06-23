"""Config flow for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
	CONF_AUTH_URL,
	CONF_ENABLE_LOCATION_TRACKING,
	CONF_SCHEDULE_TIMEZONE,
	CONF_TIMEOUT,
	CONF_UPDATE_INTERVAL,
	DEFAULT_TIMEOUT,
	DEFAULT_UPDATE_INTERVAL,
	DOMAIN,
	INTEGRATION_NAME,
	LOGGER_NAME,
)
from .exceptions import AuthenticationError
from .schedules import get_time_zone

_LOGGER = logging.getLogger(LOGGER_NAME)


def _normalize_schedule_timezone(value: Any) -> str:
	"""Normalize and validate the optional schedule timezone."""
	if value is None:
		return ""
	timezone = str(value).strip()
	if timezone and get_time_zone(timezone) is None:
		raise vol.Invalid("invalid_timezone")
	return timezone


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

	@staticmethod
	def async_get_options_flow(
		config_entry: config_entries.ConfigEntry,
	) -> config_entries.OptionsFlow:
		"""Get the options flow for this handler."""
		return OptionsFlowHandler()

	async def async_step_user(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Handle the initial step - present a menu to choose how to connect."""
		from .auth.addon_client import AddonCookieClient

		# Detect available auth source (only used as a hint for the "auto" branch)
		addon_client = AddonCookieClient(self.hass)
		source_type, detected_url = await addon_client.detect_auth_source()

		self._detected_source = source_type
		self._detected_url = detected_url

		_LOGGER.debug(f"Detected auth source: {source_type}, URL: {detected_url}")

		# Always let the user choose between auto-detection and manual URL.
		# This is critical for Docker standalone setups where localhost-based
		# detection cannot reach the auth container running on another host.
		return self.async_show_menu(
			step_id="user",
			menu_options=["auto_detect", "manual_url"],
		)

	async def async_step_auto_detect(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Use the auto-detected authentication source."""
		if self._detected_source == "none":
			# Nothing was detected, fall back to the manual URL form
			return await self.async_step_manual_url()
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

				# Check if URL is reachable (use the parsed base URL — the user
				# may have appended ?api_key=... which the client strips)
				if await addon_client._check_url_available(addon_client.auth_url):
					# Check if cookies are available
					cookies = await addon_client._fetch_cookies_from_url(addon_client.auth_url)
					if cookies:
						self._detected_url = auth_url
						# Proceed to configure step with URL
						return await self.async_step_configure(None, auth_url=auth_url)
					elif addon_client.last_fetch_status == 403:
						errors["base"] = "invalid_api_key"
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
			try:
				user_input[CONF_SCHEDULE_TIMEZONE] = _normalize_schedule_timezone(
					user_input.get(CONF_SCHEDULE_TIMEZONE)
				)
			except vol.Invalid:
				errors[CONF_SCHEDULE_TIMEZONE] = "invalid_timezone"
			if errors:
				return self.async_show_form(
					step_id="configure",
					data_schema=self._configure_schema(user_input),
					errors=errors,
					description_placeholders=self._description_placeholders(auth_url),
				)

			# Add auth_url to data if we have one
			if auth_url:
				user_input[CONF_AUTH_URL] = auth_url

			try:
				info = await validate_input(self.hass, user_input)
				# Prevent duplicate entries for the same auth source
				unique_id = auth_url or "familylink_default"
				await self.async_set_unique_id(unique_id)
				self._abort_if_unique_id_configured()
				return self.async_create_entry(title=info["title"], data=user_input)

			except CannotConnect:
				errors["base"] = "cannot_connect"
			except InvalidAuth:
				errors["base"] = "invalid_auth"
			except AbortFlow:
				raise
			except Exception:
				_LOGGER.exception("Unexpected exception")
				errors["base"] = "unknown"

		return self.async_show_form(
			step_id="configure",
			data_schema=self._configure_schema(),
			errors=errors,
			description_placeholders=self._description_placeholders(auth_url),
		)

	def _configure_schema(self, defaults: dict[str, Any] | None = None) -> vol.Schema:
		"""Return the configure-step schema."""
		defaults = defaults or {}
		return vol.Schema({
			vol.Required(CONF_NAME, default=INTEGRATION_NAME): str,
			vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
				vol.Coerce(int), vol.Range(min=30, max=3600)
			),
			vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
				vol.Coerce(int), vol.Range(min=10, max=120)
			),
			vol.Optional(CONF_ENABLE_LOCATION_TRACKING, default=False): bool,
			vol.Optional(
				CONF_SCHEDULE_TIMEZONE,
				default=defaults.get(CONF_SCHEDULE_TIMEZONE, ""),
			): str,
		})

	def _description_placeholders(self, auth_url: str | None) -> dict[str, str]:
		"""Return configure-step description placeholders."""
		if self._detected_source == "api":
			auth_source = f"API ({self._detected_url})"
		elif self._detected_source == "file":
			auth_source = "Local file (/share/familylink/)"
		else:
			auth_source = auth_url or "Manual URL"
		return {"auth_source": auth_source}

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


class OptionsFlowHandler(config_entries.OptionsFlow):
	"""Handle options flow for Family Link."""

	async def async_step_init(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Manage the options."""
		if user_input is not None:
			try:
				user_input[CONF_SCHEDULE_TIMEZONE] = _normalize_schedule_timezone(
					user_input.get(CONF_SCHEDULE_TIMEZONE)
				)
			except vol.Invalid:
				return self.async_show_form(
					step_id="init",
					data_schema=self._options_schema(user_input),
					errors={CONF_SCHEDULE_TIMEZONE: "invalid_timezone"},
				)
			# Update the config entry with new options
			return self.async_create_entry(title="", data=user_input)

		return self.async_show_form(
			step_id="init",
			data_schema=self._options_schema(),
		)

	def _options_schema(self, defaults: dict[str, Any] | None = None) -> vol.Schema:
		"""Return the options-flow schema."""
		defaults = defaults or {}
		current_options = self.config_entry.options
		current_data = self.config_entry.data
		return vol.Schema({
			vol.Optional(
				CONF_UPDATE_INTERVAL,
				default=defaults.get(CONF_UPDATE_INTERVAL, current_options.get(
					CONF_UPDATE_INTERVAL,
					current_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
				)),
			): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
			vol.Optional(
				CONF_TIMEOUT,
				default=defaults.get(CONF_TIMEOUT, current_options.get(
					CONF_TIMEOUT,
					current_data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
				)),
			): vol.All(vol.Coerce(int), vol.Range(min=10, max=120)),
			vol.Optional(
				CONF_ENABLE_LOCATION_TRACKING,
				default=defaults.get(CONF_ENABLE_LOCATION_TRACKING, current_options.get(
					CONF_ENABLE_LOCATION_TRACKING,
					current_data.get(CONF_ENABLE_LOCATION_TRACKING, False)
				)),
			): bool,
			vol.Optional(
				CONF_SCHEDULE_TIMEZONE,
				default=defaults.get(CONF_SCHEDULE_TIMEZONE, current_options.get(
					CONF_SCHEDULE_TIMEZONE,
					current_data.get(CONF_SCHEDULE_TIMEZONE, "")
				)),
			): str,
		})
