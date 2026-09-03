"""Device registry helpers: link a child's devices to the child's hub device.

Home Assistant 2026.8 replaced ``DeviceInfo``'s ``via_device`` (an identifier
tuple) with ``via_device_id`` (the registry id of the parent device) and
deprecated the old key; the deprecation report raises a ``RuntimeError`` when
the calling frame cannot be attributed to an integration, which is the case
for a ``DeviceInfo`` consumed by ``entity_platform``: the first entity that
creates a device with ``via_device`` fails to be added (issue #155, seen on
2026.8.3 and 2026.9).

The key is feature-detected so releases older than 2026.8 keep the old link.
Every platform creates (or finds) the child's hub device before adding its
entities and keeps the registry id on the coordinator, so no registry lookup
by identifier is needed (that lookup is deprecated too).
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

SUPPORTS_VIA_DEVICE_ID = "via_device_id" in getattr(DeviceInfo, "__annotations__", {})


def ensure_child_device(hass: HomeAssistant, coordinator: Any, entry_id: str, child_id: str, child_name: str) -> str:
	"""Create the child's hub device if needed, remember and return its registry id."""
	device = dr.async_get(hass).async_get_or_create(
		config_entry_id=entry_id,
		identifiers={(DOMAIN, child_id)},
		name=f"{child_name} (Family Link)",
		manufacturer="Google",
		model="Family Link Account",
	)
	coordinator.child_device_ids[child_id] = device.id
	return device.id


def via_child(coordinator: Any, child_id: str) -> dict[str, Any]:
	"""DeviceInfo keys linking a device entity to its child's hub device."""
	if not SUPPORTS_VIA_DEVICE_ID:
		return {"via_device": (DOMAIN, child_id)}
	device_id = getattr(coordinator, "child_device_ids", {}).get(child_id)
	return {"via_device_id": device_id} if device_id else {}
