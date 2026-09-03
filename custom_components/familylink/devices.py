"""Device registry helpers: link a child's devices to the child's hub device.

Home Assistant 2026.8 replaced ``DeviceInfo``'s ``via_device`` (an identifier
tuple) with ``via_device_id`` (the registry id of the parent device) and
deprecated the old key. From 2026.9 the deprecation report raises a
``RuntimeError`` when the calling frame cannot be attributed to an
integration, which is the case for a ``DeviceInfo`` consumed by
``entity_platform``: the first entity that creates a device with
``via_device`` fails to be added (issue #155, rc3 report on 2026.9).

The key is feature-detected so releases older than 2026.8 keep the old
link, and every platform makes sure the hub device exists before it adds
device entities, whatever the platform load order.
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

SUPPORTS_VIA_DEVICE_ID = "via_device_id" in getattr(DeviceInfo, "__annotations__", {})


def ensure_child_device(hass: HomeAssistant, entry_id: str, child_id: str, child_name: str) -> str:
	"""Create the child's hub device if needed and return its registry id."""
	device = dr.async_get(hass).async_get_or_create(
		config_entry_id=entry_id,
		identifiers={(DOMAIN, child_id)},
		name=f"{child_name} (Family Link)",
		manufacturer="Google",
		model="Family Link Account",
	)
	return device.id


def via_child(hass: HomeAssistant | None, child_id: str) -> dict[str, Any]:
	"""DeviceInfo keys linking a device entity to its child's hub device."""
	if not SUPPORTS_VIA_DEVICE_ID:
		return {"via_device": (DOMAIN, child_id)}
	if hass is None:
		return {}
	device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, child_id)})
	return {"via_device_id": device.id} if device else {}
