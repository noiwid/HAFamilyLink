"""Services for the child's Chrome site lists (Family Link "Google Chrome and Web").

block_site / allow_site / remove_site edit any entry, including ones a parent
added in the Family Link app; get_sites returns both lists and the filter
level. sync_site_list keeps the blocked list in step with a published list of
domains (for example a daily-updated block list on GitHub): it adds what the
list gained and removes only what that same list had added before and has
since dropped, so entries made by hand are left alone. The list is a third
party's and is downloaded from inside Home Assistant, so that service is for
administrators only and holds the list to https, a size cap, plain domains, and
a refusal of an empty or cut-short answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
import logging
from typing import Any
from urllib.parse import urlsplit

import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .client.api import FamilyLinkClient
from .const import DOMAIN, LOGGER_NAME
from .permissions import async_register_guarded_service, async_require_admin
from .websites import domain_patterns, normalize_site, parse_site_list

_LOGGER = logging.getLogger(LOGGER_NAME)

SERVICE_GET_SITES = "get_sites"
SERVICE_BLOCK_SITE = "block_site"
SERVICE_ALLOW_SITE = "allow_site"
SERVICE_REMOVE_SITE = "remove_site"
SERVICE_SYNC_SITE_LIST = "sync_site_list"
WEBSITE_SERVICES = (SERVICE_GET_SITES, SERVICE_BLOCK_SITE, SERVICE_ALLOW_SITE, SERVICE_REMOVE_SITE, SERVICE_SYNC_SITE_LIST)

# One sync must not push an unbounded list
MAX_SYNC_DOMAINS = 2000
# A list is read up to this size; one of MAX_SYNC_DOMAINS domains is far smaller
MAX_LIST_BYTES = 1024 * 1024
# One update call carries at most this many entries: what was tried live
UPDATE_BATCH = 2500
# A sync removes at most half of what its list added, or this many entries if that is more
SYNC_REMOVE_FLOOR = 20


def _https_url(value: Any) -> str:
	"""The site list URL; the list is a third party's, so only over https."""
	url = cv.url(value)
	if urlsplit(url).scheme != "https":
		raise vol.Invalid("The site list URL must start with https://")
	return url


_TARGET = {
	vol.Optional("entity_id"): cv.entity_id,
	vol.Optional("child_id"): cv.string,
}
SCHEMA_GET_SITES = vol.Schema(_TARGET)
SCHEMA_EDIT_SITES = vol.Schema({**_TARGET, vol.Required("sites"): vol.All(cv.ensure_list, [cv.string], vol.Length(min=1))})
SCHEMA_SYNC_SITE_LIST = vol.Schema({
	**_TARGET,
	vol.Required("url"): _https_url,
	vol.Optional("max_domains", default=MAX_SYNC_DOMAINS): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_SYNC_DOMAINS)),
	vol.Optional("stop", default=False): cv.boolean,
})
# Responses list at most this many patterns; counts are always complete
RESPONSE_SAMPLE = 20
ALLOW = FamilyLinkClient.WEBSITE_ALLOW
BLOCK = FamilyLinkClient.WEBSITE_BLOCK


def _resolve_child(hass: HomeAssistant, call: ServiceCall) -> str:
	"""The child a site service targets; a child is always required."""
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


def _batches(
	insert: list[tuple[str, str]], remove: list[tuple[str, str]]
) -> Iterator[tuple[list[tuple[str, str]], list[tuple[str, str]]]]:
	"""Split a change into update calls of at most UPDATE_BATCH entries, inserts first."""
	entries = [(entry, True) for entry in insert] + [(entry, False) for entry in remove]
	for start in range(0, len(entries), UPDATE_BATCH):
		chunk = entries[start : start + UPDATE_BATCH]
		yield [entry for entry, inserted in chunk if inserted], [entry for entry, inserted in chunk if not inserted]


def _patterns(sites: list[str]) -> list[str]:
	patterns: list[str] = []
	for site in sites:
		try:
			pattern = normalize_site(site)
		except ValueError as err:
			raise ServiceValidationError(str(err)) from err
		if pattern not in patterns:
			patterns.append(pattern)
	return patterns


async def async_setup_website_services(hass: HomeAssistant, coordinator: Any) -> None:
	"""Register the site list services."""
	store: Store = Store(hass, 1, f"{DOMAIN}.site_sync")
	# The store is one record for every child and list, read and saved around network
	# calls: two syncs at once would each save their own copy and lose the other's
	store_lock = asyncio.Lock()

	def _client():
		if coordinator.client is None:
			raise HomeAssistantError("Family Link client is not connected. Please re-authenticate via the add-on.")
		return coordinator.client

	async def _apply(child_id: str, insert: list[tuple[str, str]], remove: list[tuple[str, str]]) -> dict[str, Any]:
		try:
			result = await _client().async_update_website_restrictions(child_id, insert=insert, remove=remove)
		except HomeAssistantError:
			raise
		except Exception as err:
			raise HomeAssistantError(f"Updating the site lists failed: {err}") from err
		coordinator.store_websites(child_id, result)
		await coordinator.async_request_refresh()
		return result

	async def _read(child_id: str) -> dict[str, Any]:
		try:
			return await _client().async_get_website_restrictions(child_id)
		except HomeAssistantError:
			raise
		except Exception as err:
			raise HomeAssistantError(f"Reading the site lists failed: {err}") from err

	async def handle_get_sites(call: ServiceCall) -> ServiceResponse:
		child_id = _resolve_child(hass, call)
		lists = await _read(child_id)
		coordinator.store_websites(child_id, lists)
		return {"child_id": child_id, **lists}

	async def _edit(call: ServiceCall, kind: str) -> ServiceResponse:
		child_id = _resolve_child(hass, call)
		patterns = _patterns(call.data["sites"])
		result = await _apply(child_id, [(p, kind) for p in patterns], [])
		return {"child_id": child_id, "covered": result.get("covered") or {}}

	async def handle_block_site(call: ServiceCall) -> ServiceResponse:
		return await _edit(call, BLOCK)

	async def handle_allow_site(call: ServiceCall) -> ServiceResponse:
		return await _edit(call, ALLOW)

	async def handle_remove_site(call: ServiceCall) -> ServiceResponse:
		child_id = _resolve_child(hass, call)
		patterns = _patterns(call.data["sites"])
		current = await _read(child_id)
		remove = [(p, BLOCK) for p in patterns if p in current["blocked"]]
		remove += [(p, ALLOW) for p in patterns if p in current["approved"]]
		missing = [p for p in patterns if p not in current["blocked"] and p not in current["approved"]]
		if remove:
			await _apply(child_id, [], remove)
		return {"child_id": child_id, "removed": [p for p, _ in remove], "not_listed": missing}

	async def _download(url: str) -> str:
		"""The list at ``url``, refused when it is larger than MAX_LIST_BYTES."""
		too_large = f"The site list {url} is larger than {MAX_LIST_BYTES // 1024} KiB."
		body = bytearray()
		try:
			# Redirects are not followed: an https address could send the download to http or to a host inside the network
			async with async_get_clientsession(hass).get(
				url, timeout=aiohttp.ClientTimeout(total=60), allow_redirects=False
			) as response:
				if 300 <= response.status < 400:
					raise HomeAssistantError(
						f"The site list {url} redirects to another address, which is not followed. Use the final https:// address."
					)
				response.raise_for_status()
				declared = response.headers.get("Content-Length", "")
				if declared.isdigit() and int(declared) > MAX_LIST_BYTES:
					raise HomeAssistantError(too_large)
				async for chunk in response.content.iter_chunked(64 * 1024):
					body.extend(chunk)
					if len(body) > MAX_LIST_BYTES:
						raise HomeAssistantError(too_large)
		except HomeAssistantError:
			raise
		except Exception as err:
			raise HomeAssistantError(f"Could not download the site list {url}: {err}") from err
		# utf-8-sig: a byte order mark would otherwise stick to the first domain
		return body.decode("utf-8-sig", errors="replace")

	async def handle_sync_site_list(call: ServiceCall) -> ServiceResponse:
		# It downloads a URL from inside Home Assistant: no entity permission makes
		# that safe for a non-administrator
		await async_require_admin(hass, call)
		async with store_lock:
			return await _sync_site_list(call)

	async def _sync_site_list(call: ServiceCall) -> ServiceResponse:
		child_id = _resolve_child(hass, call)
		url = call.data["url"]
		if call.data["stop"]:
			return await _stop_sync(child_id, url)
		text = await _download(url)
		ignored: list[str] = []
		domains = parse_site_list(text, ignored)
		if not domains:
			# An emptied file, an HTML error page or a captive portal reads as a
			# list that dropped every domain, and would take back all it added
			raise HomeAssistantError(
				f"The site list {url} has no usable domains ({len(ignored)} entries ignored), so nothing was "
				"changed. To remove what the list added, call sync_site_list with stop: true."
			)
		if len(domains) > call.data["max_domains"]:
			raise HomeAssistantError(
				f"The site list has {len(domains)} domains, more than max_domains ({call.data['max_domains']})."
			)
		data = await store.async_load() or {}
		pushed = set(data.get(child_id, {}).get(url, []))
		current = await _read(child_id)
		blocked, approved = set(current["blocked"]), set(current["approved"])
		# A domain the parent approved in any form is skipped whole: Chrome lets
		# a block win over an allow, so blocking example.com while *.example.com
		# is approved would block the approved site.
		wanted: list[str] = []
		skipped: list[str] = []
		for domain in domains:
			patterns = domain_patterns(domain)
			if approved & set(patterns):
				skipped.append(domain)
				continue
			wanted.extend(p for p in patterns if p not in wanted)
		insert = [(p, BLOCK) for p in wanted if p not in blocked]
		# Remove only what this list pushed before and no longer contains
		remove = [(p, BLOCK) for p in sorted(pushed - set(wanted)) if p in blocked]
		# A list cut short by a failed or partial download also reads as a list that
		# dropped most of its domains: refuse what a real change would not remove
		if len(remove) > max(SYNC_REMOVE_FLOOR, len(pushed) // 2):
			raise HomeAssistantError(
				f"Refusing to remove {len(remove)} of the {len(pushed)} entries {url} added: the list looks cut "
				"short. Nothing was changed. If it really shrank that much, call sync_site_list with stop: true "
				"and then sync again."
			)
		covered: dict[str, Any] = {}
		for batch_insert, batch_remove in _batches(insert, remove):
			result = await _apply(child_id, batch_insert, batch_remove)
			covered.update(result.get("covered") or {})
			pushed |= {p for p, _ in batch_insert} - set(covered)
			pushed -= {p for p, _ in batch_remove}
			# Saved after each call, so a failure part-way leaves no entry untracked
			data.setdefault(child_id, {})[url] = sorted(pushed)
			await store.async_save(data)
		added = [p for p, _ in insert if p not in covered]
		removed = [p for p, _ in remove]
		_LOGGER.info(
			f"Site list sync for {child_id} from {url}: added {len(added)}, removed {len(removed)}, "
			f"skipped {len(skipped)} approved, ignored {len(ignored)} unfit"
		)
		return {
			"child_id": child_id,
			"url": url,
			"domains": len(domains),
			"added_count": len(added),
			"added": added[:RESPONSE_SAMPLE],
			"removed_count": len(removed),
			"removed": removed[:RESPONSE_SAMPLE],
			"skipped_approved": skipped[:RESPONSE_SAMPLE],
			"ignored_count": len(ignored),
			"ignored": ignored[:RESPONSE_SAMPLE],
		}

	async def _stop_sync(child_id: str, url: str) -> dict[str, Any]:
		"""Take out everything a list pushed for the child, and forget the list."""
		data = await store.async_load() or {}
		pushed = set(data.get(child_id, {}).pop(url, []))
		current = await _read(child_id)
		remove = [(p, BLOCK) for p in sorted(pushed) if p in set(current["blocked"])]
		# Same batch size as a sync: a full list is about 4,000 patterns
		for _, batch_remove in _batches([], remove):
			await _apply(child_id, [], batch_remove)
		await store.async_save(data)
		_LOGGER.info(f"Site list sync for {child_id} from {url} stopped: removed {len(remove)}")
		return {"child_id": child_id, "url": url, "stopped": True, "removed_count": len(remove), "removed": [p for p, _ in remove][:RESPONSE_SAMPLE]}

	for service, handler, schema, response in (
		(SERVICE_GET_SITES, handle_get_sites, SCHEMA_GET_SITES, SupportsResponse.ONLY),
		(SERVICE_BLOCK_SITE, handle_block_site, SCHEMA_EDIT_SITES, SupportsResponse.OPTIONAL),
		(SERVICE_ALLOW_SITE, handle_allow_site, SCHEMA_EDIT_SITES, SupportsResponse.OPTIONAL),
		(SERVICE_REMOVE_SITE, handle_remove_site, SCHEMA_EDIT_SITES, SupportsResponse.OPTIONAL),
		(SERVICE_SYNC_SITE_LIST, handle_sync_site_list, SCHEMA_SYNC_SITE_LIST, SupportsResponse.OPTIONAL),
	):
		async_register_guarded_service(hass, DOMAIN, service, handler, schema=schema, supports_response=response)


def async_remove_website_services(hass: HomeAssistant) -> None:
	"""Unregister the site list services."""
	for service in WEBSITE_SERVICES:
		hass.services.async_remove(DOMAIN, service)
