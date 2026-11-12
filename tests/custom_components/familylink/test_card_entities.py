"""The dashboard card finds the entities of a child and of one device from a single entity of the device."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.familylink import card

CHILD = "child-1"
PHONE = "phone1"
TABLET = "tablet1"


def _registry():
	def entry(entity_id, unique_id, platform="familylink"):
		return SimpleNamespace(entity_id=entity_id, unique_id=unique_id, platform=platform)

	entries = [
		entry("switch.alex_phone", f"familylink_{CHILD}_{PHONE}"),
		entry("sensor.alex_phone_daily_limit", f"familylink_{CHILD}_{PHONE}_daily_limit"),
		entry("button.alex_phone_15min", f"familylink_{CHILD}_{PHONE}_bonus_15min"),
		entry("switch.alex_tablet", f"familylink_{CHILD}_{TABLET}"),
		entry("sensor.alex_tablet_daily_limit", f"familylink_{CHILD}_{TABLET}_daily_limit"),
		entry("switch.alex_daily_limit", f"familylink_{CHILD}_daily_limit"),
		entry("switch.alex_bedtime", f"familylink_{CHILD}_bedtime"),
		entry("number.alex_monday_limit", f"familylink_{CHILD}_daily_limit_monday"),
		entry("sensor.alex_blocked_apps", f"familylink_{CHILD}_blocked_apps"),
		entry("switch.other_child_bedtime", "familylink_child-2_bedtime"),
		entry("switch.not_ours", f"familylink_{CHILD}_{PHONE}", platform="other"),
	]
	registry = MagicMock()
	registry.entities = {e.entity_id: e for e in entries}
	registry.async_get = lambda entity_id: registry.entities.get(entity_id)
	return registry


def _hass():
	coordinator = SimpleNamespace(data={"children_data": [{"child_id": CHILD, "devices": [{"id": PHONE}, {"id": TABLET}]}]})
	return SimpleNamespace(data={"familylink": {"entry": coordinator}})


def test_roles_of_the_phone_and_its_child():
	with patch.object(card.er, "async_get", return_value=_registry()):
		result = card.card_entities(_hass(), "switch.alex_phone")
	assert result == {
		"child_id": CHILD,
		"device_id": PHONE,
		"child": {
			"daily_limit": "switch.alex_daily_limit",
			"bedtime": "switch.alex_bedtime",
			"daily_limit_monday": "number.alex_monday_limit",
			"blocked_apps": "sensor.alex_blocked_apps",
		},
		"device": {
			"lock": "switch.alex_phone",
			"daily_limit": "sensor.alex_phone_daily_limit",
			"bonus_15min": "button.alex_phone_15min",
		},
	}


def test_any_entity_of_the_device_works_and_the_tablet_stays_out():
	with patch.object(card.er, "async_get", return_value=_registry()):
		result = card.card_entities(_hass(), "sensor.alex_phone_daily_limit")
	assert result["device"]["lock"] == "switch.alex_phone"
	assert "switch.alex_tablet" not in result["device"].values()


def test_unknown_or_foreign_entity():
	with patch.object(card.er, "async_get", return_value=_registry()):
		assert card.card_entities(_hass(), "light.kitchen") is None
		assert card.card_entities(_hass(), "switch.not_ours") is None


async def test_registered_once():
	hass = MagicMock()
	hass.data = {}
	hass.http.async_register_static_paths = AsyncMock()
	hass.async_add_executor_job = AsyncMock(return_value=123)
	with (
		patch.object(card, "async_get_integration", AsyncMock(return_value=SimpleNamespace(version="9.9.9"))),
		patch.object(card, "add_extra_js_url") as add_js,
		patch.object(card.websocket_api, "async_register_command") as add_ws,
	):
		await card.async_register_card(hass)
		await card.async_register_card(hass)
	assert [c.args[1] for c in add_js.call_args_list] == [
		"/familylink_card/familylink-card.js?v=9.9.9-123",
		"/familylink_card/parental-screen-time.js?v=9.9.9-123",
	]
	add_ws.assert_called_once()
	if card.StaticPathConfig is None:  # Home Assistant before 2024.7
		hass.http.register_static_path.assert_called_once()
	else:
		hass.http.async_register_static_paths.assert_awaited_once()
