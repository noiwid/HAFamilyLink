"""Dashboard card shipped with the integration (custom:familylink-card).

The integration serves frontend/familylink-card.js and adds it to every dashboard,
so a user installs nothing else: no resource to declare, no helper, no script.
A websocket command gives the card the entities of a child and of one device,
found by unique id, so the card config only names one entity of the device.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from .const import DOMAIN

try:
	from homeassistant.components.http import StaticPathConfig
except ImportError:  # Home Assistant before 2024.7: the synchronous registration below
	StaticPathConfig = None

URL_BASE = "/familylink_card"
_REGISTERED = f"{DOMAIN}_card_registered"
FRONTEND = Path(__file__).parent / "frontend"


def _mtime(path: Path) -> int:
	"""Modification time of a frontend file, 0 when it cannot be read."""
	try:
		return int(path.stat().st_mtime)
	except OSError:
		return 0


async def async_register_card(hass: HomeAssistant) -> None:
	"""Serve the card and register its websocket command, once per Home Assistant instance."""
	if hass.data.get(_REGISTERED):
		return
	hass.data[_REGISTERED] = True
	if StaticPathConfig is None:
		hass.http.register_static_path(URL_BASE, str(FRONTEND), False)
	else:
		await hass.http.async_register_static_paths(
			[StaticPathConfig(URL_BASE, str(FRONTEND), cache_headers=False)]
		)
	# A new address for a new file, or the mobile app keeps its copy: the version for a release,
	# the modification time for a file changed in place
	version = (await async_get_integration(hass, DOMAIN)).version
	for name in ("familylink-card.js", "parental-screen-time.js"):  # the second is shared with Family Safety
		stamp = await hass.async_add_executor_job(_mtime, FRONTEND / name)
		add_extra_js_url(hass, f"{URL_BASE}/{name}?v={version}-{stamp}")
	websocket_api.async_register_command(hass, ws_card_entities)


def card_entities(hass: HomeAssistant, entity_id: str) -> dict[str, Any] | None:
	"""Entities of the child and of the device that ``entity_id`` belongs to, by role.

	Roles are the unique id suffixes: ``familylink_<child>_<role>`` for the child,
	``familylink_<child>_<device>_<role>`` for the device (``lock`` for the device switch).
	"""
	registry = er.async_get(hass)
	entry = registry.async_get(entity_id)
	if entry is None or entry.platform != DOMAIN:
		return None
	# Device ids, to tell a device's entities from the child's ones
	devices = {
		device.get("id")
		for coordinator in hass.data.get(DOMAIN, {}).values()
		for child in (getattr(coordinator, "data", None) or {}).get("children_data", [])
		for device in child.get("devices", [])
	}
	child_id, _, rest = entry.unique_id.removeprefix(f"{DOMAIN}_").partition("_")
	device_id = rest.split("_")[0] if rest.split("_")[0] in devices else None
	prefix = f"{DOMAIN}_{child_id}_"
	child: dict[str, str] = {}
	device: dict[str, str] = {}
	for other in registry.entities.values():
		if other.platform != DOMAIN or not other.unique_id.startswith(prefix):
			continue
		role = other.unique_id[len(prefix):]
		head, _, tail = role.partition("_")
		if head in devices:
			if head == device_id:
				device[tail or "lock"] = other.entity_id
		else:
			child[role] = other.entity_id
	return {"child_id": child_id, "device_id": device_id, "child": child, "device": device}


@websocket_api.websocket_command({vol.Required("type"): "familylink/card_entities", vol.Required("entity_id"): str})
@callback
def ws_card_entities(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
	"""Return the entities the card needs for the device of ``entity_id``."""
	result = card_entities(hass, msg["entity_id"])
	if result is None:
		connection.send_error(msg["id"], "not_found", f"{msg['entity_id']} is not a Family Link entity")
		return
	connection.send_result(msg["id"], result)
