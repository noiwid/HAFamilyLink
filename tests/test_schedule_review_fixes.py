"""Regression tests for Family Link schedule review fixes."""
from __future__ import annotations

import asyncio
from datetime import datetime
import importlib
import json
import re
import sys
import types
from typing import Any
from unittest.mock import AsyncMock

import pytest


def _install_dependency_stubs() -> None:
	"""Install small stubs for HA-only dependencies not needed by these tests."""
	vol = types.ModuleType("voluptuous")

	class Marker:
		def __init__(self, key: str, required: bool) -> None:
			self.key = key
			self.required = required

		def __hash__(self) -> int:
			return hash((self.key, self.required))

		def __eq__(self, other: object) -> bool:
			return (
				isinstance(other, Marker)
				and self.key == other.key
				and self.required == other.required
			)

	class Schema:
		def __init__(self, schema: dict[Any, Any]) -> None:
			self.schema = schema

		def __call__(self, data: dict[str, Any]) -> dict[str, Any]:
			result = dict(data)
			for marker, validator in self.schema.items():
				key = marker.key if isinstance(marker, Marker) else marker
				required = isinstance(marker, Marker) and marker.required
				if key not in data:
					if required:
						raise ValueError(f"Missing required key: {key}")
					continue
				result[key] = _apply_validator(validator, data[key])
			return result

	def _apply_validator(validator: Any, value: Any) -> Any:
		if isinstance(validator, list):
			item_validator = validator[0]
			return [_apply_validator(item_validator, item) for item in value]
		return validator(value) if callable(validator) else value

	def All(*validators: Any):
		def validate(value: Any) -> Any:
			for validator in validators:
				value = _apply_validator(validator, value)
			return value
		return validate

	def Coerce(value_type: type):
		return value_type

	def Range(min: int | None = None, max: int | None = None):
		def validate(value: int) -> int:
			if min is not None and value < min:
				raise ValueError("Value is too small")
			if max is not None and value > max:
				raise ValueError("Value is too large")
			return value
		return validate

	def Match(pattern: str):
		regex = re.compile(pattern)

		def validate(value: str) -> str:
			if not isinstance(value, str) or not regex.match(value):
				raise ValueError("Value does not match pattern")
			return value
		return validate

	vol.Schema = Schema
	vol.Required = lambda key: Marker(key, True)
	vol.Optional = lambda key: Marker(key, False)
	vol.All = All
	vol.Coerce = Coerce
	vol.Range = Range
	vol.Match = Match
	sys.modules["voluptuous"] = vol

	ha = types.ModuleType("homeassistant")
	core = types.ModuleType("homeassistant.core")

	class HomeAssistant:
		pass

	class ServiceCall:
		def __init__(self, data: dict[str, Any]) -> None:
			self.data = data

	core.HomeAssistant = HomeAssistant
	core.ServiceCall = ServiceCall

	const = types.ModuleType("homeassistant.const")
	const.Platform = types.SimpleNamespace(
		BINARY_SENSOR="binary_sensor",
		BUTTON="button",
		DEVICE_TRACKER="device_tracker",
		SENSOR="sensor",
		SWITCH="switch",
	)

	exceptions = types.ModuleType("homeassistant.exceptions")
	exceptions.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})

	config_entries = types.ModuleType("homeassistant.config_entries")
	config_entries.ConfigEntry = type("ConfigEntry", (), {})

	helpers = types.ModuleType("homeassistant.helpers")
	cv = types.ModuleType("homeassistant.helpers.config_validation")
	cv.ensure_list = lambda value: value if isinstance(value, list) else [value]
	cv.string = lambda value: value if isinstance(value, str) else str(value)
	cv.entity_id = cv.string

	def boolean(value: Any) -> bool:
		if isinstance(value, bool):
			return value
		if isinstance(value, str) and value.lower() in {"true", "on", "yes", "1"}:
			return True
		if isinstance(value, str) and value.lower() in {"false", "off", "no", "0"}:
			return False
		raise ValueError("Expected boolean")

	cv.boolean = boolean

	update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

	class DataUpdateCoordinator:
		def __init__(self, *args: Any, **kwargs: Any) -> None:
			pass

	update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
	update_coordinator.UpdateFailed = type("UpdateFailed", (Exception,), {})

	util = types.ModuleType("homeassistant.util")
	dt = types.ModuleType("homeassistant.util.dt")
	dt.now = lambda time_zone=None: datetime(2026, 6, 22, 12, 0, tzinfo=time_zone)
	util.dt = dt

	sys.modules["homeassistant"] = ha
	sys.modules["homeassistant.core"] = core
	sys.modules["homeassistant.const"] = const
	sys.modules["homeassistant.exceptions"] = exceptions
	sys.modules["homeassistant.config_entries"] = config_entries
	sys.modules["homeassistant.helpers"] = helpers
	sys.modules["homeassistant.helpers.config_validation"] = cv
	sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
	sys.modules["homeassistant.util"] = util
	sys.modules["homeassistant.util.dt"] = dt

	aiohttp = types.ModuleType("aiohttp")
	aiohttp.ClientSession = object
	sys.modules["aiohttp"] = aiohttp

	auth_pkg = types.ModuleType("custom_components.familylink.auth")
	auth_pkg.__path__ = []
	addon_client = types.ModuleType("custom_components.familylink.auth.addon_client")

	class AddonCookieClient:
		def __init__(self, *args: Any, **kwargs: Any) -> None:
			pass

	addon_client.AddonCookieClient = AddonCookieClient
	sys.modules["custom_components.familylink.auth"] = auth_pkg
	sys.modules["custom_components.familylink.auth.addon_client"] = addon_client


if importlib.util.find_spec("homeassistant") is None:
	_install_dependency_stubs()
import voluptuous as vol
familylink = importlib.import_module("custom_components.familylink")
api = importlib.import_module("custom_components.familylink.client.api")
schedules = importlib.import_module("custom_components.familylink.schedules")


class FakeResponse:
	def __init__(
		self,
		status: int,
		payload: Any | None = None,
		text: str = "response body",
	) -> None:
		self.status = status
		self._payload = payload
		self._text = text

	async def __aenter__(self):
		return self

	async def __aexit__(self, exc_type, exc, tb) -> None:
		return None

	async def text(self) -> str:
		return self._text

	async def json(self) -> Any:
		return self._payload


class FakeSession:
	def __init__(
		self,
		put_statuses: list[int] | None = None,
		get_payload: Any | None = None,
	) -> None:
		self.put_statuses = put_statuses or [200]
		self.get_payload = get_payload
		self.put_calls: list[dict[str, Any]] = []
		self.get_calls: list[dict[str, Any]] = []

	def put(self, url: str, **kwargs: Any) -> FakeResponse:
		self.put_calls.append({"url": url, **kwargs})
		status = self.put_statuses.pop(0)
		return FakeResponse(status)

	def get(self, url: str, **kwargs: Any) -> FakeResponse:
		self.get_calls.append({"url": url, **kwargs})
		return FakeResponse(200, payload=self.get_payload)


class FakeHass:
	config = types.SimpleNamespace(time_zone="UTC")

	def __init__(self) -> None:
		self.services = FakeServices()
		self.states = FakeStates()


class FakeServices:
	def __init__(self) -> None:
		self.registrations: dict[tuple[str, str], dict[str, Any]] = {}

	def async_register(self, domain: str, service: str, handler: Any, schema: Any = None) -> None:
		self.registrations[(domain, service)] = {
			"handler": handler,
			"schema": schema,
		}


class FakeStates:
	def __init__(self) -> None:
		self._states: dict[str, Any] = {}

	def get(self, entity_id: str) -> Any:
		return self._states.get(entity_id)


def make_client(session: FakeSession | None = None) -> api.FamilyLinkClient:
	client = api.FamilyLinkClient(FakeHass(), {})
	client._cookies = [{"name": "SAPISID", "value": "cookie", "domain": "google.com"}]
	if session is not None:
		async def get_session() -> FakeSession:
			return session
		client._get_session = get_session
	return client


def test_effective_source_preserves_same_window_today_override_origin():
	weekly_schedule = [{
		"day": 1,
		"day_name": "Monday",
		"enabled": True,
		"start": [21, 0],
		"end": [6, 30],
		"state_flag": 2,
	}]

	window = schedules.describe_effective_window(
		"21:00", "06:30", weekly_schedule, 1
	)

	assert window["source"] == "weekly"
	assert window["differs_from_weekly"] is False
	assert (
		schedules.effective_bedtime_window_source(window, "today_override")
		== "today_override"
	)


def test_effective_source_marks_different_today_override():
	weekly_schedule = [{
		"day": 1,
		"day_name": "Monday",
		"enabled": True,
		"start": [20, 0],
		"end": [6, 30],
		"state_flag": 2,
	}]

	window = schedules.describe_effective_window(
		"21:00", "06:30", weekly_schedule, 1
	)

	assert window["source"] == "today_override"
	assert window["differs_from_weekly"] is True
	assert (
		schedules.effective_bedtime_window_source(window, "today_override")
		== "today_override"
	)


def test_effective_source_reports_none_when_today_override_turns_window_off():
	weekly_schedule = [{
		"day": 1,
		"day_name": "Monday",
		"enabled": True,
		"start": [21, 0],
		"end": [6, 30],
		"state_flag": 2,
	}]

	window = schedules.describe_effective_window(None, None, weekly_schedule, 1)

	assert window["label"] is None
	assert schedules.effective_bedtime_window_source(window, "today_override") == "none"


def test_recurring_time_limit_update_uses_put_with_method_override():
	session = FakeSession([200])
	client = make_client(session)

	assert asyncio.run(
		client._async_update_time_limit("child123", ["payload"], "test update")
	)
	assert len(session.put_calls) == 1
	assert session.put_calls[0]["url"].endswith("/people/child123/timeLimit:update")
	assert session.put_calls[0]["params"] == {"$httpMethod": "PUT"}
	assert json.loads(session.put_calls[0]["data"]) == ["payload"]


def test_recurring_time_limit_update_returns_false_on_non_200():
	session = FakeSession([503])
	client = make_client(session)

	assert not asyncio.run(
		client._async_update_time_limit("child123", ["payload"], "test update")
	)
	assert len(session.put_calls) == 1


def test_bedtime_schedule_partial_failure_raises_with_completed_step():
	client = make_client()
	client._async_update_time_limit = AsyncMock(side_effect=[True, False])

	with pytest.raises(api.ScheduleUpdatePartialError) as exc:
		asyncio.run(
			client.async_set_bedtime_schedule(
				1,
				start_time="21:00",
				end_time="06:30",
				enabled=False,
				account_id="child123",
			)
		)

	assert exc.value.successful_updates == ["bedtime schedule for day 1"]
	assert exc.value.failed_update == "bedtime schedule enabled state for day 1"
	assert client._async_update_time_limit.await_count == 2


def test_daily_limit_schedule_first_failure_returns_false_without_partial_error():
	client = make_client()
	client._async_update_time_limit = AsyncMock(return_value=False)

	assert not asyncio.run(
		client.async_set_daily_limit_schedule(
			1,
			daily_minutes=90,
			enabled=True,
			account_id="child123",
		)
	)
	assert client._async_update_time_limit.await_count == 1


def test_time_limit_parser_uses_newest_today_override_by_timestamp(monkeypatch):
	monkeypatch.setattr(
		api.dt_util,
		"now",
		lambda time_zone=None: datetime(2026, 6, 22, 12, 0, tzinfo=time_zone),
	)
	rule_id = "x" * 32
	response_data = [
		["metadata"],
		[
			[
				2,
				[["CAEQAQ", 1, 2, [21, 0], [6, 30], "1", "2", "bedtime-rule"]],
				"created",
				"updated",
				1,
			],
			[[2, [6, 0], [["CAEQAQ", 1, 2, 90, "1", "2"]], "created", "updated"]],
			[
				["newer", "2000", 9, None, None, None, [2, [21, 0], [6, 30], "CAEQAQ"]],
				["older", "1000", 9, None, None, None, [1, [21, 0], [6, 30], "CAEQAQ"]],
			],
			None,
			[1],
			[[rule_id, 1, 2, [123, 0]]],
		],
	]
	session = FakeSession(get_payload=response_data)
	client = make_client(session)

	result = asyncio.run(client.async_get_time_limit(account_id="child123"))

	assert result["bedtime_enabled"] is True
	assert result["bedtime_enabled_today"] is True
	assert result["bedtime_today_source"] == "today_override"
	assert result["bedtime_today_override_action"] == 2
	assert result["daily_limit_schedule"] == [{
		"day": 1,
		"day_name": "Monday",
		"enabled": True,
		"minutes": 90,
		"state_flag": 2,
	}]


def test_time_limit_parser_handles_missing_blocks_without_crashing():
	session = FakeSession(get_payload=[["metadata"], []])
	client = make_client(session)

	result = asyncio.run(client.async_get_time_limit(account_id="child123"))

	assert result["bedtime_enabled"] is False
	assert result["bedtime_enabled_today"] is False
	assert result["bedtime_today_source"] == "weekly"
	assert result["bedtime_schedule"] == []
	assert result["daily_limit_schedule"] == []


def test_daily_limit_parser_dedupes_duplicate_days_and_disables_zero_minutes():
	config = [[
		2,
		[6, 0],
		[
			["CAEQAQ", 1, 2, 90, "old"],
			["CAEQAQ", 1, 2, 120, "new"],
			["CAEQAg", 2, 2, 0, "zero"],
			["CAEQAw", 3, 1, 45, "disabled"],
			["CAEQBA", 4, 2, None, "malformed"],
		],
	]]

	assert schedules.parse_daily_limit_schedule(config) == [
		{
			"day": 1,
			"day_name": "Monday",
			"enabled": True,
			"minutes": 120,
			"state_flag": 2,
		},
		{
			"day": 2,
			"day_name": "Tuesday",
			"enabled": False,
			"minutes": 0,
			"state_flag": 2,
		},
		{
			"day": 3,
			"day_name": "Wednesday",
			"enabled": False,
			"minutes": 45,
			"state_flag": 1,
		},
	]


def test_schedule_service_schema_rejects_invalid_times():
	schema = familylink.SCHEMA_SET_BEDTIME_SCHEDULE
	invalid_error = getattr(vol, "Invalid", ValueError)

	assert schema({
		"day": "1",
		"start_time": "21:00",
		"end_time": "06:30",
	})["day"] == 1
	with pytest.raises((ValueError, invalid_error)):
		schema({"day": "1", "start_time": "24:00", "end_time": "06:30"})
	with pytest.raises((ValueError, invalid_error)):
		schema({"day": "1", "start_time": "21:5", "end_time": "06:30"})


def test_schedule_services_register_without_weekly_schooltime_write_service():
	hass = FakeHass()
	coordinator = types.SimpleNamespace(client=object())

	asyncio.run(familylink.async_setup_services(hass, coordinator))

	service_names = {service for _, service in hass.services.registrations}
	assert "set_bedtime_schedule" in service_names
	assert "set_daily_limit_schedule" in service_names
	assert "set_school_time_schedule" not in service_names


def test_schedule_service_without_target_uses_client_default_child_resolution():
	class Client:
		def __init__(self) -> None:
			self.calls: list[dict[str, Any]] = []

		async def async_set_daily_limit_schedule(
			self,
			day: int,
			daily_minutes: int | None = None,
			enabled: bool | None = None,
			account_id: str | None = None,
		) -> bool:
			self.calls.append({
				"day": day,
				"daily_minutes": daily_minutes,
				"enabled": enabled,
				"account_id": account_id,
			})
			return True

	client = Client()
	coordinator = types.SimpleNamespace(
		client=client,
		refreshes=0,
		async_request_refresh=AsyncMock(),
	)
	hass = FakeHass()
	asyncio.run(familylink.async_setup_services(hass, coordinator))
	handler = hass.services.registrations[
		("familylink", "set_daily_limit_schedule")
	]["handler"]

	asyncio.run(handler(types.SimpleNamespace(data={
		"day": "2",
		"daily_minutes": 45,
	})))

	assert client.calls == [{
		"day": 2,
		"daily_minutes": 45,
		"enabled": None,
		"account_id": None,
	}]
	coordinator.async_request_refresh.assert_awaited_once()


def test_schedule_service_refreshes_after_partial_write_failure():
	err = api.ScheduleUpdatePartialError(
		["bedtime schedule for day 1"],
		"bedtime schedule enabled state for day 1",
	)

	class Client:
		async def async_set_bedtime_schedule(self, **kwargs: Any) -> bool:
			raise err

	coordinator = types.SimpleNamespace(
		client=Client(),
		async_request_refresh=AsyncMock(),
	)
	hass = FakeHass()
	asyncio.run(familylink.async_setup_services(hass, coordinator))
	handler = hass.services.registrations[
		("familylink", "set_bedtime_schedule")
	]["handler"]

	with pytest.raises(api.ScheduleUpdatePartialError):
		asyncio.run(handler(types.SimpleNamespace(data={
			"day": "1",
			"start_time": "21:00",
			"end_time": "06:30",
			"enabled": False,
		})))

	coordinator.async_request_refresh.assert_awaited_once()
