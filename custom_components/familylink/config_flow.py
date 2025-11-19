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

from .const import (
	CONF_TIMEOUT,
	CONF_UPDATE_INTERVAL,
	DEFAULT_TIMEOUT,
	DEFAULT_UPDATE_INTERVAL,
	DOMAIN,
	INTEGRATION_NAME,
	LOGGER_NAME,
)
from .exceptions import AuthenticationError, BrowserError, FamilyLinkException

_LOGGER = logging.getLogger(LOGGER_NAME)

STEP_USER_DATA_SCHEMA = vol.Schema(
	{
		vol.Required(CONF_NAME, default=INTEGRATION_NAME): str,
		vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
			vol.Coerce(int), vol.Range(min=30, max=3600)
		),
		vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
			vol.Coerce(int), vol.Range(min=10, max=120)
		),
	}
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
	"""Validate the user input allows us to connect."""
	# Import here to avoid circular imports
	from .auth.addon_client import AddonCookieClient

	try:
		# Check if add-on has provided cookies
		addon_client = AddonCookieClient(hass)

		if not await addon_client.cookies_available():
			raise AuthenticationError(
				"No cookies found. Please use the Family Link Auth add-on to authenticate first. "
				"Install and run the add-on, then return here to complete setup."
			)

		# Load cookies from add-on
		cookies = await addon_client.load_cookies()

		if not cookies:
			raise AuthenticationError("Failed to load cookies from add-on")

		# Return info that you want to store in the config entry
		return {
			"title": data[CONF_NAME],
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

	async def async_step_user(
		self, user_input: dict[str, Any] | None = None
	) -> FlowResult:
		"""Handle the initial step."""
		errors: dict[str, str] = {}

		if user_input is not None:
			try:
				# Validate user input
				info = await validate_input(self.hass, user_input)
				
				# Create the config entry
				return self.async_create_entry(title=info["title"], data=user_input)

			except CannotConnect:
				errors["base"] = "cannot_connect"
			except InvalidAuth:
				errors["base"] = "invalid_auth"
			except Exception:  # pylint: disable=broad-except
				_LOGGER.exception("Unexpected exception")
				errors["base"] = "unknown"

		return self.async_show_form(
			step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
		)

	async def async_step_import(self, import_info: dict[str, Any]) -> FlowResult:
		"""Handle import from configuration.yaml."""
		# Check if already configured
		await self.async_set_unique_id(DOMAIN)
		self._abort_if_unique_id_configured()

		# Validate imported configuration
		try:
			info = await validate_input(self.hass, import_info)
			return self.async_create_entry(title=info["title"], data=import_info)
		except (CannotConnect, InvalidAuth):
			return self.async_abort(reason="invalid_config")


class CannotConnect(HomeAssistantError):
	"""Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
	"""Error to indicate there is invalid auth.""" 