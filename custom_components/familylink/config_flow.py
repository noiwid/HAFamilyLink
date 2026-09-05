"""Config flow for Google Family Link integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
	TextSelector,
	TextSelectorConfig,
	TextSelectorType,
)

from .const import (
	AUTH_SOURCE_MANAGED,
	AUTH_SOURCE_MANUAL,
	CONF_API_KEY,
	CONF_AUTH_SOURCE,
	CONF_AUTH_URL,
	CONF_CLEAR_API_KEY,
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
	api_key = data.get(CONF_API_KEY)
	auth_source = data.get(CONF_AUTH_SOURCE)

	try:
		addon_client = AddonCookieClient(
			hass,
			auth_url=auth_url,
			api_key=api_key,
			auth_source=auth_source,
		)

		# Try to load cookies
		cookies = await addon_client.load_cookies()

		if not cookies:
			if addon_client.last_fetch_status == 403:
				raise InvalidApiKey
			raise AuthenticationError(
				"No cookies found. Please authenticate first using the Family Link Auth add-on or container."
			)

		# Return info to store in config entry
		return {
			"title": data.get(CONF_NAME, INTEGRATION_NAME),
			"cookies": cookies,
		}

	except InvalidApiKey:
		raise
	except AuthenticationError as err:
		_LOGGER.error("Authentication failed")
		raise InvalidAuth from err
	except Exception as err:
		_LOGGER.exception("Unexpected error during validation")
		raise CannotConnect from err


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
	"""Handle a config flow for Google Family Link."""

	VERSION = 2

	def __init__(self) -> None:
		"""Initialize config flow."""
		self._detected_source: str | None = None
		self._detected_url: str | None = None
		self._api_key: str | None = None
		self._auth_source: str | None = None

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

		_LOGGER.debug("Authentication source detection completed: %s", source_type)

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
		self._api_key = None
		self._auth_source = (
			AUTH_SOURCE_MANAGED
			if self._detected_source in {"managed_addon", "file"}
			else AUTH_SOURCE_MANUAL
		)
		return await self.async_step_configure(user_input)

	async def async_step_manual_url(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Handle manual URL configuration for Docker standalone."""
		self._detected_source = "api"
		self._detected_url = None
		self._api_key = None
		self._auth_source = AUTH_SOURCE_MANUAL
		errors: dict[str, str] = {}

		if user_input is not None:
			from .auth.addon_client import (
				AddonCookieClient,
				AuthServerApiKeyError,
				AuthServerConnectionError,
				AuthServerCookiesUnavailable,
				normalize_auth_url,
			)

			auth_url = user_input.get(CONF_AUTH_URL, "").strip()
			api_key = user_input.get(CONF_API_KEY, "").strip() or None

			if not auth_url:
				errors["base"] = "url_required"
			else:
				try:
					auth_url = normalize_auth_url(auth_url)
				except (TypeError, ValueError):
					errors["base"] = "invalid_url"
				else:
					addon_client = AddonCookieClient(
						self.hass,
						auth_url=auth_url,
						api_key=api_key,
						auth_source=AUTH_SOURCE_MANUAL,
					)
					try:
						await addon_client.async_validate_manual_endpoint()
					except AuthServerConnectionError:
						errors["base"] = "cannot_connect"
					except AuthServerApiKeyError:
						errors["base"] = "invalid_api_key"
					except AuthServerCookiesUnavailable:
						errors["base"] = "no_cookies"
					else:
						self._detected_source = "api"
						self._detected_url = auth_url
						self._api_key = api_key
						self._auth_source = AUTH_SOURCE_MANUAL
						return await self.async_step_configure(None)

		# Show URL input form
		return self.async_show_form(
			step_id="manual_url",
			data_schema=vol.Schema({
				vol.Required(
					CONF_AUTH_URL,
					default="http://192.168.1.100:8099",
				): TextSelector(
					TextSelectorConfig(
						type=TextSelectorType.URL,
					)
				),
				vol.Optional(CONF_API_KEY): TextSelector(
					TextSelectorConfig(
						type=TextSelectorType.PASSWORD,
					)
				),
			}),
			errors=errors,
			description_placeholders={
				"default_url": "http://localhost:8099",
			},
		)

	async def async_step_configure(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Handle configuration step."""
		errors: dict[str, str] = {}

		auth_url = self._detected_url

		if user_input is not None:
			if self._auth_source not in {AUTH_SOURCE_MANAGED, AUTH_SOURCE_MANUAL}:
				return self.async_abort(reason="unknown")
			entry_data = dict(user_input)
			entry_data[CONF_AUTH_SOURCE] = self._auth_source
			if auth_url and self._auth_source == AUTH_SOURCE_MANUAL:
				entry_data[CONF_AUTH_URL] = auth_url
			if self._api_key:
				entry_data[CONF_API_KEY] = self._api_key

			try:
				info = await validate_input(self.hass, entry_data)
				# Managed/file sources have a stable identity that does not expose
				# an internal Supervisor hostname.
				unique_id = (
					"familylink_default"
					if self._auth_source == AUTH_SOURCE_MANAGED
					else auth_url or "familylink_default"
				)
				await self.async_set_unique_id(unique_id)
				self._abort_if_unique_id_configured()
				return self.async_create_entry(title=info["title"], data=entry_data)

			except CannotConnect:
				errors["base"] = "cannot_connect"
			except InvalidAuth:
				errors["base"] = "invalid_auth"
			except InvalidApiKey:
				errors["base"] = "invalid_api_key"
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
		if self._detected_source in {"api", "managed_addon"}:
			description_placeholders["auth_source"] = "Detected authentication server"
		elif self._detected_source == "file":
			description_placeholders["auth_source"] = "Local file (/share/familylink/)"
		else:
			description_placeholders["auth_source"] = "Manual authentication server"

		return self.async_show_form(
			step_id="configure",
			data_schema=schema,
			errors=errors,
			description_placeholders=description_placeholders,
		)

	async def async_step_import(self, import_info: dict[str, Any]) -> FlowResult:
		"""Handle import from configuration.yaml."""
		from .auth.addon_client import split_legacy_auth_url

		entry_data = dict(import_info)
		if auth_url := entry_data.get(CONF_AUTH_URL):
			try:
				clean_url, legacy_key = split_legacy_auth_url(auth_url)
			except (TypeError, ValueError):
				return self.async_abort(reason="invalid_config")
			existing_key = entry_data.get(CONF_API_KEY)
			if existing_key and legacy_key and existing_key != legacy_key:
				return self.async_abort(reason="invalid_config")
			entry_data[CONF_AUTH_URL] = clean_url
			if legacy_key:
				entry_data[CONF_API_KEY] = existing_key or legacy_key
			entry_data[CONF_AUTH_SOURCE] = AUTH_SOURCE_MANUAL
			unique_id = clean_url
		else:
			entry_data[CONF_AUTH_SOURCE] = AUTH_SOURCE_MANAGED
			unique_id = "familylink_default"

		await self.async_set_unique_id(unique_id)
		self._abort_if_unique_id_configured()

		try:
			info = await validate_input(self.hass, entry_data)
			return self.async_create_entry(title=info["title"], data=entry_data)
		except (CannotConnect, InvalidAuth, InvalidApiKey):
			return self.async_abort(reason="invalid_config")

	async def async_step_reconfigure(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Update the authentication server URL and API key."""
		from .auth.addon_client import normalize_auth_url

		entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
		if entry is None:
			return self.async_abort(reason="unknown")
		errors: dict[str, str] = {}
		if user_input is not None:
			try:
				auth_url = normalize_auth_url(user_input[CONF_AUTH_URL])
			except (KeyError, TypeError, ValueError):
				errors["base"] = "invalid_url"
			else:
				submitted_key = user_input.get(CONF_API_KEY, "").strip()
				clear_api_key = user_input.get(CONF_CLEAR_API_KEY, False)
				if submitted_key and clear_api_key:
					errors["base"] = "api_key_conflict"
					return self._show_reconfigure_form(entry, errors)
				current_url = entry.data.get(CONF_AUTH_URL)
				existing_key = entry.data.get(CONF_API_KEY)
				if (
					auth_url != current_url
					and existing_key
					and not submitted_key
					and not clear_api_key
				):
					errors["base"] = "api_key_required_for_new_url"
					return self._show_reconfigure_form(entry, errors)
				api_key = None if clear_api_key else submitted_key or existing_key
				new_data = {
					**entry.data,
					CONF_AUTH_SOURCE: AUTH_SOURCE_MANUAL,
					CONF_AUTH_URL: auth_url,
				}
				if api_key:
					new_data[CONF_API_KEY] = api_key
				else:
					new_data.pop(CONF_API_KEY, None)
				if any(
					other_entry.entry_id != entry.entry_id
					and other_entry.unique_id == auth_url
					for other_entry in self.hass.config_entries.async_entries(DOMAIN)
				):
					return self.async_abort(reason="already_configured")
				try:
					await validate_input(self.hass, new_data)
				except CannotConnect:
					errors["base"] = "cannot_connect"
				except InvalidAuth:
					errors["base"] = "invalid_auth"
				except InvalidApiKey:
					errors["base"] = "invalid_api_key"
				else:
					return self.async_update_reload_and_abort(
						entry,
						data=new_data,
						unique_id=auth_url,
						reason="reconfigure_successful",
					)

		return self._show_reconfigure_form(entry, errors)

	def _show_reconfigure_form(
		self,
		entry: config_entries.ConfigEntry,
		errors: dict[str, str],
	) -> FlowResult:
		"""Show the credential reconfiguration form without exposing the key."""
		return self.async_show_form(
			step_id="reconfigure",
			data_schema=vol.Schema({
				vol.Required(
					CONF_AUTH_URL,
					default=entry.data.get(CONF_AUTH_URL, "http://localhost:8099"),
				): TextSelector(
					TextSelectorConfig(
						type=TextSelectorType.URL,
					)
				),
				vol.Optional(CONF_API_KEY): TextSelector(
					TextSelectorConfig(
						type=TextSelectorType.PASSWORD,
					)
				),
				vol.Optional(CONF_CLEAR_API_KEY, default=False): bool,
			}),
			errors=errors,
		)


class CannotConnect(HomeAssistantError):
	"""Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
	"""Error to indicate there is invalid auth."""


class InvalidApiKey(HomeAssistantError):
	"""Error to indicate the cookie API key was rejected."""


class OptionsFlowHandler(config_entries.OptionsFlow):
	"""Handle options flow for Family Link."""

	async def async_step_init(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Manage the options."""
		if user_input is not None:
			# Update the config entry with new options
			return self.async_create_entry(title="", data=user_input)

		# Get current values from config entry data (options first, then data)
		current_options = self.config_entry.options
		current_data = self.config_entry.data

		return self.async_show_form(
			step_id="init",
			data_schema=vol.Schema({
				vol.Optional(
					CONF_UPDATE_INTERVAL,
					default=current_options.get(
						CONF_UPDATE_INTERVAL,
						current_data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
					),
				): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
				vol.Optional(
					CONF_TIMEOUT,
					default=current_options.get(
						CONF_TIMEOUT,
						current_data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
					),
				): vol.All(vol.Coerce(int), vol.Range(min=10, max=120)),
				vol.Optional(
					CONF_ENABLE_LOCATION_TRACKING,
					default=current_options.get(
						CONF_ENABLE_LOCATION_TRACKING,
						current_data.get(CONF_ENABLE_LOCATION_TRACKING, False)
					),
				): bool,
			}),
		)
