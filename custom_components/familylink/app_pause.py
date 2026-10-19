"""Pause and resume apps by their Family Link app time limit.

Pausing sets an app's daily limit to 1 minute. Measured live on Android 15:
an app whose limit is at or below the minutes it has already been used today
is paused within seconds, and stays installed. That is different from
blocking it (``block_app``), which hides the app, and for the default SMS app
(Google Messages) lost every text that arrived while it was blocked; a paused
Messages kept them. An app not used yet today gets its 1 minute, then pauses.

The setting in force before the first pause (a limit, unlimited time, or no
limit) is stored and put back by ``resume_app``, also after a restart. Limits
count per device, so a pause applies on every device of the child. Google TV
ignores app limits; there, only ``block_app`` works. A limit changed in the
Family Link app while an app is paused is overwritten by ``resume_app``. An app
blocked while it is paused is left blocked: ``resume_app`` skips it and keeps
its saved setting for a later resume.

The saved settings are one record shared by every child and changed across
network writes, so the two services run one at a time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import DOMAIN, LOGGER_NAME
from .permissions import async_register_guarded_service

_LOGGER = logging.getLogger(LOGGER_NAME)

SERVICE_PAUSE_APP = "pause_app"
SERVICE_RESUME_APP = "resume_app"
APP_PAUSE_SERVICES = (SERVICE_PAUSE_APP, SERVICE_RESUME_APP)

PAUSE_MINUTES = 1
UNLIMITED = -2  # set_app_daily_limit: unlimited time, ignores device limits
NO_LIMIT = -1  # set_app_daily_limit: app limit off, follows device limits

_TARGET = {vol.Optional("entity_id"): cv.entity_id, vol.Optional("child_id"): cv.string}
SCHEMA_PAUSE_APP = vol.Schema({**_TARGET, vol.Required("packages"): vol.All(cv.ensure_list, [cv.string], vol.Length(min=1))})
SCHEMA_RESUME_APP = vol.Schema({**_TARGET, vol.Optional("packages"): vol.All(cv.ensure_list, [cv.string])})


def app_limit_setting(app: dict[str, Any]) -> int | None:
	"""The set_app_daily_limit value matching an app's current setting; None when it is blocked."""
	supervision = app.get("supervisionSetting") or {}
	if supervision.get("hidden"):
		return None
	always = supervision.get("alwaysAllowedAppInfo") or {}
	if always.get("alwaysAllowedState") == "alwaysAllowedStateEnabled":
		return UNLIMITED
	limit = supervision.get("usageLimit") or {}
	if limit.get("enabled") and isinstance(limit.get("dailyUsageLimitMins"), int):
		return limit["dailyUsageLimitMins"]
	return NO_LIMIT


def _resolve_child(hass: HomeAssistant, call: ServiceCall) -> str:
	from . import extract_ids_from_entity  # late import: __init__ imports this module

	child_id = (call.data.get("child_id") or "").strip()
	entity_id = call.data.get("entity_id")
	if entity_id and not child_id:
		try:
			_, child_id = extract_ids_from_entity(hass, entity_id)
		except ValueError as err:
			raise ServiceValidationError(str(err)) from err
	if not child_id:
		raise ServiceValidationError("No child given. Pass child_id or a Family Link entity of the child.")
	return child_id


async def async_setup_app_pause_services(hass: HomeAssistant, coordinator: Any) -> None:
	"""Register pause_app and resume_app."""
	store: Store = Store(hass, 1, f"{DOMAIN}.app_pause")
	# A pause and a resume of one app overlapping would let the pause see the
	# setting the resume is about to put back, skip saving it, and leave the app
	# at 1 minute with nothing to resume once the resume has dropped the record
	lock = asyncio.Lock()

	def _client():
		if coordinator.client is None:
			raise HomeAssistantError("Family Link client is not connected. Please re-authenticate via the add-on.")
		return coordinator.client

	def _apps(child_id: str) -> dict[str, dict[str, Any]]:
		for child in (coordinator.data or {}).get("children_data", []):
			if child.get("child_id") == child_id:
				return {app.get("packageName"): app for app in child.get("apps", []) if app.get("packageName")}
		return {}

	async def _set_limit(child_id: str, package: str, minutes: int) -> None:
		ok = await _client().async_set_app_daily_limit(package, minutes, account_id=child_id)
		if not ok:
			raise HomeAssistantError(f"Family Link did not take the app limit for {package}")

	async def handle_pause_app(call: ServiceCall) -> ServiceResponse:
		child_id = _resolve_child(hass, call)
		# The refresh stays inside the lock so the next call reads fresh settings
		async with lock:
			apps = _apps(child_id)
			data = await store.async_load() or {}
			saved: dict[str, int] = data.setdefault(child_id, {})
			paused: list[str] = []
			skipped: dict[str, str] = {}
			for package in dict.fromkeys(call.data["packages"]):
				app = apps.get(package)
				current = app_limit_setting(app) if app is not None else NO_LIMIT
				if current is None:
					skipped[package] = "blocked"
					continue
				# Keep the setting from before the first pause; a second pause must
				# not record the pause itself as the setting to come back to
				if package not in saved:
					saved[package] = current
					# Saved before the write, so a failure part-way can still be resumed
					await store.async_save(data)
				await _set_limit(child_id, package, PAUSE_MINUTES)
				paused.append(package)
			await coordinator.async_request_refresh()
		_LOGGER.info(f"Paused apps for {child_id}: {paused}, skipped {skipped}")
		return {"child_id": child_id, "paused": paused, "skipped": skipped}

	async def handle_resume_app(call: ServiceCall) -> ServiceResponse:
		child_id = _resolve_child(hass, call)
		async with lock:
			apps = _apps(child_id)
			data = await store.async_load() or {}
			saved: dict[str, int] = data.get(child_id, {})
			packages = list(dict.fromkeys(call.data.get("packages") or saved))
			resumed: dict[str, int] = {}
			not_paused: list[str] = []
			skipped: dict[str, str] = {}
			for package in packages:
				if package not in saved:
					not_paused.append(package)
					continue
				app = apps.get(package)
				if app is not None and app_limit_setting(app) is None:
					# Blocked since the pause: writing its limit back can lift the
					# block. The saved setting stays for when it is unblocked.
					_LOGGER.warning(f"Not resuming {package} for {child_id}: it is blocked, its saved setting is kept")
					skipped[package] = "blocked"
					continue
				await _set_limit(child_id, package, saved[package])
				resumed[package] = saved.pop(package)
				if not saved:
					data.pop(child_id, None)
				await store.async_save(data)
			await coordinator.async_request_refresh()
		_LOGGER.info(f"Resumed apps for {child_id}: {resumed}, skipped {skipped}")
		return {"child_id": child_id, "resumed": resumed, "not_paused": not_paused, "skipped": skipped}

	async_register_guarded_service(
		hass, DOMAIN, SERVICE_PAUSE_APP, handle_pause_app, schema=SCHEMA_PAUSE_APP, supports_response=SupportsResponse.OPTIONAL
	)
	async_register_guarded_service(
		hass, DOMAIN, SERVICE_RESUME_APP, handle_resume_app, schema=SCHEMA_RESUME_APP, supports_response=SupportsResponse.OPTIONAL
	)


def async_remove_app_pause_services(hass: HomeAssistant) -> None:
	"""Unregister pause_app and resume_app."""
	for service in APP_PAUSE_SERVICES:
		hass.services.async_remove(DOMAIN, service)
