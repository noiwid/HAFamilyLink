"""Privacy boundaries for Family Link entities and logging."""

from __future__ import annotations

import asyncio
import ast
import inspect
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError, Unauthorized
from homeassistant.helpers.update_coordinator import UpdateFailed

import custom_components.familylink as familylink
import custom_components.familylink.privacy as privacy_module
from custom_components.familylink import (
    _privacy_safe_handler,
    async_setup_services,
    binary_sensor,
    device_tracker,
    number,
    select,
    sensor,
    switch,
    time,
)
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.entity import privacy_safe_entity_action
from custom_components.familylink.exceptions import (
    FamilyLinkException,
    FamilyLinkValidationError,
)
from custom_components.familylink.privacy import (
    FamilyLinkRedactionFilter,
    SensitiveValueRegistry,
    get_privacy_logger,
    redact_text,
    register_sensitive_values,
)

EXPECTED_UNRECORDED = {
    binary_sensor.BedtimeActiveBinarySensor: {
        "device_id", "device_name", "child_id", "child_name",
        "bedtime_start", "bedtime_end",
    },
    binary_sensor.SchoolTimeActiveBinarySensor: {
        "device_id", "device_name", "child_id", "child_name",
        "schooltime_start", "schooltime_end",
    },
    binary_sensor.DailyLimitReachedBinarySensor: {
        "device_id", "device_name", "child_id", "child_name",
    },
    device_tracker.FamilyLinkDeviceTracker: {
        "latitude", "longitude", "gps_accuracy", "source_device", "place_name",
        "address", "location_timestamp",
    },
    number.FamilyLinkDailyLimitNumber: {"child_id", "child_name"},
    select.FamilyLinkContactRestrictionSelect: {"child_id", "child_name"},
    time.FamilyLinkBedtimeTime: {"child_id", "child_name", "start", "end"},
    sensor.ScreenTimeRemainingSensor: {
        "child_id", "child_name", "device_id", "device_name",
    },
    sensor.NextRestrictionSensor: {
        "child_id", "child_name", "device_id", "device_name",
        "next_scheduled_start", "next_scheduled_end", "bedtime_start",
        "bedtime_end", "schooltime_start", "schooltime_end",
    },
    sensor.FamilyLinkScreenTimeSensor: {
        "child_id", "child_name", "apps",
    },
    sensor.FamilyLinkScreenTimeFormattedSensor: {
        "child_id", "child_name",
    },
    sensor.FamilyLinkAppCountSensor: {"child_id", "child_name"},
    sensor.FamilyLinkBlockedAppsSensor: {"child_id", "child_name", "apps"},
    sensor.FamilyLinkAppsWithLimitsSensor: {"child_id", "child_name", "apps"},
    sensor.FamilyLinkAppsWithoutLimitsSensor: {"child_id", "child_name", "apps"},
    sensor.FamilyLinkAlwaysAllowedAppsSensor: {"child_id", "child_name", "apps"},
    sensor.FamilyLinkTopAppSensor: {
        "child_id", "child_name", "app_name", "package_name",
    },
    sensor.FamilyLinkDeviceCountSensor: {"child_id", "child_name", "devices"},
    sensor.FamilyLinkChildInfoSensor: {
        "child_id", "child_name", "user_id", "role", "display_name",
        "given_name", "family_name", "email", "birthday", "age_band",
    },
    sensor.DailyLimitDeviceSensor: {
        "child_id", "child_name", "device_id", "device_name",
    },
    sensor.ActiveBonusSensor: {
        "child_id", "child_name", "device_id", "device_name",
    },
    sensor.FamilyLinkBatteryLevelSensor: {
        "child_id", "child_name", "source_device", "last_update",
    },
    switch.FamilyLinkDeviceSwitch: {
        "device_id", "device_name", "child_id", "child_name", "last_seen",
    },
    switch.FamilyLinkSchoolTimeSwitch: set(),
    switch.FamilyLinkStrictModeSwitch: {
        "child_id", "child_name", "last_action_at", "ha_decisions_today",
        "ha_device_decisions_today", "ha_reference_values",
    },
}


def test_recorder_exclusion_matrix_is_explicit_and_exact() -> None:
    """Every dynamic attribute owner has a directly auditable exact set."""
    modules = (binary_sensor, device_tracker, number, select, sensor, switch, time)
    actual = {
        candidate
        for module in modules
        for _, candidate in inspect.getmembers(module, inspect.isclass)
        if candidate.__module__ == module.__name__
        and "extra_state_attributes" in candidate.__dict__
    }
    assert actual == EXPECTED_UNRECORDED.keys()
    for entity_class, expected in EXPECTED_UNRECORDED.items():
        assert entity_class.__dict__["_unrecorded_attributes"] == frozenset(expected)
        assert "*" not in entity_class._unrecorded_attributes


def test_standard_logger_filter_is_idempotent_and_preserves_diagnostics(caplog) -> None:
    """The factory returns a Logger and retains safe arguments and levels."""
    name = "custom_components.familylink.privacy_test"
    logger = get_privacy_logger(name)
    assert isinstance(logger, logging.Logger)
    assert get_privacy_logger(name) is logger
    assert sum(isinstance(item, FamilyLinkRedactionFilter) for item in logger.filters) == 1

    with caplog.at_level(logging.DEBUG, logger=name):
        logger.warning("Strict mode action=%s duration=%d enabled=%s", "lock", 30, True)

    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert record.msg == "Strict mode action=%s duration=%d enabled=%s"
    assert record.args == ("lock", 30, True)
    assert "Strict mode action=lock duration=30 enabled=True" in caplog.text


def test_filter_redacts_static_dynamic_encoded_and_exception_values(caplog) -> None:
    """Credentials, household data, URLs, and exception chains are redacted."""
    logger = get_privacy_logger("custom_components.familylink.redaction_test")
    canaries = {
        "child": "child-id-canary",
        "name": "Minor Name Canary",
        "device": "device-id-canary",
        "package": "invalid.example.secret-package",
        "override": "override-id-canary",
    }
    register_sensitive_values(canaries)
    encoded_url = (
        "https%3A%2F%2Fuser%3Apass%40example.invalid%2Fpath%3Ftoken%3Durl-canary"
    )

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        try:
            try:
                raise ValueError(
                    "email=minor@example.invalid latitude=12.345 longitude=98.765 "
                    "Authorization: SAPISIDHASH auth-canary"
                )
            except ValueError as err:
                raise RuntimeError(f"request failed {encoded_url} {canaries['child']}") from err
        except RuntimeError:
            logger.exception(
                "Location refresh failed for %s payload=%s",
                canaries["name"],
                {"device_id": canaries["device"], "package": canaries["package"]},
            )

    for canary in (*canaries.values(), "minor@example.invalid", "auth-canary", "url-canary", "12.345", "98.765"):
        assert canary not in caplog.text
    assert "Location refresh failed" in caplog.text
    assert "Traceback" in caplog.text
    assert "ValueError" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "test_filter_redacts_static_dynamic_encoded_and_exception_values" in caplog.text


def test_filter_redacts_exception_used_as_format_argument(caplog) -> None:
    logger = get_privacy_logger("custom_components.familylink.exception_arg_test")
    opaque_text = "arbitrary-unregistered-opaque-text-7f03c1"
    error = RuntimeError(opaque_text)

    with caplog.at_level(logging.ERROR, logger=logger.name):
        logger.error("Request failed: %s", error)

    assert caplog.records[-1].args == ("RuntimeError: [REDACTED]",)
    assert "RuntimeError" in caplog.text
    assert opaque_text not in caplog.text


@pytest.mark.asyncio
async def test_expected_setup_failure_keeps_sanitized_traceback(
    monkeypatch, caplog
) -> None:
    """Expected client setup failures retain frames/type without raw detail."""
    coordinator = SimpleNamespace(
        async_load_strict_intents=AsyncMock(
            side_effect=FamilyLinkException("Cookie: SID=setup-cookie-canary")
        )
    )
    monkeypatch.setattr(
        familylink, "FamilyLinkDataUpdateCoordinator", lambda hass, entry: coordinator
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ConfigEntryNotReady, match="^Unable to connect to Family Link$"):
            await familylink.async_setup_entry(SimpleNamespace(), SimpleNamespace())

    assert "setup-cookie-canary" not in caplog.text
    assert "FamilyLinkException" in caplog.text
    assert "async_setup_entry" in caplog.text


def _unsafe_log_expression(
    node: ast.AST | None, *, aggregate: bool = False
) -> bool:
    """Return whether a logging expression can render raw transport data."""
    if node is None:
        return False
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in {"len", "type"}:
            return any(
                _unsafe_log_expression(arg, aggregate=True)
                for arg in node.args
            )
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"text", "json", "read"}
            and isinstance(node.func.value, ast.Name)
            and "response" in node.func.value.id.casefold()
        ):
            return not aggregate
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id.casefold()
            in {"data", "response_data", "payload", "headers", "cookies", "mapping"}
        ):
            return not aggregate
    if isinstance(node, ast.Name):
        normalized = node.id.casefold()
        risky = {
            "response_text", "response_data", "headers", "payload", "cookies",
            "cookie_header", "url", "api_url", "body", "mapping", "data",
        }
        renamed_transport = (
            "response" in normalized
            and any(term in normalized for term in ("body", "text", "data", "payload"))
        )
        return (normalized in risky or renamed_transport) and not aggregate
    if isinstance(node, ast.Attribute):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "response"
            and node.attr == "status"
        ):
            return False
        return node.attr.casefold() in {
            "headers", "cookies", "url", "body", "payload",
        } and not aggregate
    if isinstance(node, ast.Subscript):
        return (
            isinstance(node.value, ast.Name)
            and node.value.id.casefold()
            in {"data", "response_data", "payload", "headers", "cookies", "mapping"}
            and not aggregate
        )
    if isinstance(node, (ast.Dict, ast.DictComp, ast.List, ast.ListComp, ast.Set, ast.SetComp)):
        return not aggregate
    return any(
        _unsafe_log_expression(child, aggregate=aggregate)
        for child in ast.iter_child_nodes(node)
    )


def _contains_name(node: ast.AST, names: set[str]) -> bool:
    """Return whether an expression refers to one of the supplied names."""
    return any(
        isinstance(child, ast.Name) and child.id in names
        for child in ast.walk(node)
    )


def _unsafe_exception_render(node: ast.AST, exception_names: set[str]) -> bool:
    """Return whether an exception is converted to text before filtering."""
    if isinstance(node, ast.JoinedStr):
        return _contains_name(node, exception_names)
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, (ast.Add, ast.Mod))
        and _contains_name(node, exception_names)
    ):
        return True
    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"str", "repr", "format"}
            and _contains_name(node, exception_names)
        ):
            return True
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"format", "format_map", "join"}
            and _contains_name(node, exception_names)
        ):
            return True
    return any(
        _unsafe_exception_render(child, exception_names)
        for child in ast.iter_child_nodes(node)
    )


def _logging_audit_violations(
    tree: ast.AST, *, audit_transport: bool = True
) -> list[int]:
    """Return raw-transport or pre-rendered-exception logger calls."""
    methods = {
        "debug", "info", "warning", "warn", "error", "exception", "critical", "log"
    }
    logger_names = {"_LOGGER", "logger", "adapter"}
    bound_emitters: set[str] = set()
    exception_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.name is not None
    }
    rendered_exception_names: set[str] = set()

    changed = True
    while changed:
        changed = False
        for assignment in (
            node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
        ):
            value = assignment.value
            targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
            names = {target.id for target in targets if isinstance(target, ast.Name)}
            if (
                isinstance(value, ast.Attribute)
                and value.attr in methods
                and isinstance(value.value, ast.Name)
                and value.value.id in logger_names
            ):
                before = len(bound_emitters)
                bound_emitters.update(names)
                changed |= len(bound_emitters) != before
            if isinstance(value, ast.Name) and value.id in bound_emitters:
                before = len(bound_emitters)
                bound_emitters.update(names)
                changed |= len(bound_emitters) != before
            if value is not None and (
                _unsafe_exception_render(value, exception_names)
                or (
                    isinstance(value, ast.Name)
                    and value.id in rendered_exception_names
                )
            ):
                before = len(rendered_exception_names)
                rendered_exception_names.update(names)
                changed |= len(rendered_exception_names) != before

    violations = []
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        is_logger_call = (
            isinstance(call.func, ast.Attribute) and call.func.attr in methods
        ) or (isinstance(call.func, ast.Name) and call.func.id in bound_emitters)
        if not is_logger_call:
            continue
        expressions = [*call.args, *(keyword.value for keyword in call.keywords)]
        if any(
            (audit_transport and _unsafe_log_expression(expression))
            or _unsafe_exception_render(expression, exception_names)
            or (
                isinstance(expression, ast.Name)
                and expression.id in rendered_exception_names
            )
            for expression in expressions
        ):
            violations.append(call.lineno)
    return violations


def test_source_audit_rejects_structural_transport_logging() -> None:
    """AST audit rejects raw transport values while allowing status/count/type."""
    root = Path(familylink.__file__).parent
    violations = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        violations.extend(
            f"{path.relative_to(root)}:{line}"
            for line in _logging_audit_violations(tree)
        )
    assert violations == []


@pytest.mark.parametrize(
    "source",
    (
        "_LOGGER.log(logging.DEBUG, 'reply %s', response_text)",
        "_LOGGER.info('reply', extra={'headers': headers})",
        "logger.error('reply %s', payload['body'])",
        "adapter.warning('reply %s', response.cookies)",
        "log_method = _LOGGER.error\nlog_method('reply %s', response_text)",
        "renamed_response_body = await response.text()\n_LOGGER.info('reply %s', renamed_response_body)",
        "_LOGGER.error('reply', extra={'transport': response_data})",
    ),
)
def test_transport_logging_audit_rejects_prior_bypasses(source: str) -> None:
    tree = ast.parse(source)
    assert _logging_audit_violations(tree)


@pytest.mark.parametrize(
    "source",
    (
        "try:\n    work()\nexcept Exception as err:\n    _LOGGER.error(f'failed: {err}')",
        "try:\n    work()\nexcept Exception as err:\n    logger.warning('failed: ' + str(err))",
        "try:\n    work()\nexcept Exception as err:\n    adapter.debug('failed: {}'.format(err))",
        "try:\n    work()\nexcept Exception as err:\n    _LOGGER.critical('failed: %s' % err)",
        "try:\n    work()\nexcept Exception as err:\n    log_method = _LOGGER.error\n    log_method(str(err))",
        "try:\n    work()\nexcept Exception as err:\n    message = f'failed: {err}'\n    alias = _LOGGER.exception\n    alias(message)",
    ),
)
def test_exception_logging_audit_rejects_prerendered_exceptions(
    source: str,
) -> None:
    """Exception detail must reach the filter as a BaseException object."""
    assert _logging_audit_violations(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    (
        "try:\n    work()\nexcept Exception as err:\n    _LOGGER.error('failed: %s', err)",
        "try:\n    work()\nexcept Exception:\n    _LOGGER.exception('failed')",
    ),
)
def test_exception_logging_audit_allows_filter_safe_logging(source: str) -> None:
    """Parameterized exceptions and exc_info remain filter-safe."""
    assert _logging_audit_violations(ast.parse(source), audit_transport=False) == []


def test_every_module_logger_uses_privacy_factory() -> None:
    """No integration module can silently bypass its source logger filter."""
    root = Path(familylink.__file__).parent
    violations = []
    methods = {
        "debug", "info", "warning", "warn", "error", "exception", "critical", "log"
    }
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        privacy_loggers: set[str] = set()
        privacy_emitters: set[str] = set()
        nonprivacy_emitters: set[str] = set()
        changed = True
        while changed:
            changed = False
            for assignment in (
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.Assign, ast.AnnAssign))
            ):
                value = assignment.value
                targets = (
                    assignment.targets
                    if isinstance(assignment, ast.Assign)
                    else [assignment.target]
                )
                is_factory_call = (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "get_privacy_logger"
                )
                is_privacy_alias = (
                    isinstance(value, ast.Name) and value.id in privacy_loggers
                )
                if is_factory_call or is_privacy_alias:
                    aliases = {
                        target.id for target in targets if isinstance(target, ast.Name)
                    }
                    if not aliases.issubset(privacy_loggers):
                        privacy_loggers.update(aliases)
                        changed = True
                is_privacy_bound_method = (
                    isinstance(value, ast.Attribute)
                    and value.attr in methods
                    and isinstance(value.value, ast.Name)
                    and value.value.id in privacy_loggers
                )
                is_privacy_emitter_alias = (
                    isinstance(value, ast.Name) and value.id in privacy_emitters
                )
                if is_privacy_bound_method or is_privacy_emitter_alias:
                    aliases = {
                        target.id for target in targets if isinstance(target, ast.Name)
                    }
                    if not aliases.issubset(privacy_emitters):
                        privacy_emitters.update(aliases)
                        changed = True
                is_nonprivacy_bound_method = (
                    isinstance(value, ast.Attribute)
                    and value.attr in methods
                    and (
                        not isinstance(value.value, ast.Name)
                        or value.value.id not in privacy_loggers
                    )
                )
                is_nonprivacy_emitter_alias = (
                    isinstance(value, ast.Name) and value.id in nonprivacy_emitters
                )
                if is_nonprivacy_bound_method or is_nonprivacy_emitter_alias:
                    aliases = {
                        target.id for target in targets if isinstance(target, ast.Name)
                    }
                    if not aliases.issubset(nonprivacy_emitters):
                        nonprivacy_emitters.update(aliases)
                        changed = True
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            if (
                path.name != "privacy.py"
                and isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "logging"
                and call.func.attr == "getLogger"
            ):
                violations.append(f"{path.relative_to(root)}:{call.lineno}")
            if (
                path.name != "privacy.py"
                and isinstance(call.func, ast.Name)
                and call.func.id == "LoggerAdapter"
            ):
                violations.append(f"{path.relative_to(root)}:{call.lineno}:adapter")
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr in methods
                and (
                    not isinstance(call.func.value, ast.Name)
                    or call.func.value.id not in privacy_loggers
                )
            ):
                violations.append(f"{path.relative_to(root)}:{call.lineno}:emitter")
            if (
                isinstance(call.func, ast.Name)
                and call.func.id in nonprivacy_emitters
            ):
                violations.append(f"{path.relative_to(root)}:{call.lineno}:alias")
    assert violations == []

    modules = (
        familylink, binary_sensor, device_tracker, number, select, sensor, switch, time
    )
    for module in modules:
        assert module._LOGGER.name == module.__name__
        assert any(
            isinstance(filter_, FamilyLinkRedactionFilter)
            for filter_ in module._LOGGER.filters
        )


def test_parent_child_loggers_and_structured_extra_are_sanitized() -> None:
    """Propagation and structured handlers cannot bypass source filtering."""
    output: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            output.append(record)

    parent = get_privacy_logger("custom_components.familylink.audit")
    child = get_privacy_logger("custom_components.familylink.audit.child")
    handler = Capture()
    parent.addHandler(handler)
    parent.setLevel(logging.DEBUG)
    child.setLevel(logging.DEBUG)
    try:
        child.info(
            "child event token=message-canary",
            extra={
                "request_headers": {"Cookie": "SID=cookie-canary"},
                "context_data": {"unknown_id": "json-id-canary"},
            },
        )
    finally:
        parent.removeHandler(handler)

    assert len(output) == 1
    record = output[0]
    rendered = f"{record.getMessage()} {record.request_headers} {record.context_data}"
    assert "message-canary" not in rendered
    assert "cookie-canary" not in rendered
    assert "json-id-canary" not in rendered


def test_plain_child_logger_is_not_claimed_privacy_protected() -> None:
    """Ancestor logger filters do not sanitize records from a plain child."""
    parent = get_privacy_logger("custom_components.familylink.topology")
    child = logging.getLogger("custom_components.familylink.topology.plain")
    assert any(isinstance(item, FamilyLinkRedactionFilter) for item in parent.filters)
    assert not any(isinstance(item, FamilyLinkRedactionFilter) for item in child.filters)


def test_cookie_headers_and_iterative_percent_encoding_are_redacted() -> None:
    text = (
        "Cookie: SID=sid-canary; SAPISID=sapisid-canary; other=other-canary\n"
        "Set-Cookie: __Secure-3PSID=secure-canary; Path=/; HttpOnly\n"
        "Authorization: Bearer bearer-canary\n"
        "SAPISIDHASH%25201700000000_hash-canary"
    )
    redacted = redact_text(text)
    for canary in (
        "sid-canary", "sapisid-canary", "other-canary", "secure-canary",
        "bearer-canary", "hash-canary",
    ):
        assert canary not in redacted


def test_identifier_scope_survives_ephemeral_exhaustion_without_name_overreach() -> None:
    registry = SensitiveValueRegistry(max_ephemeral_values=2)
    registry.replace_scope(
        "household:entry", (("durable-child-identifier", "identifier"),)
    )
    registry.register("payload-value-one", "payload-value-two", kind="ephemeral")
    registry.register("payload-value-three", kind="ephemeral")
    registry.replace_scope(
        "household:names", (("Home", "name"), ("Ann", "name"))
    )

    snapshot = dict(registry.snapshot())
    assert snapshot["durable-child-identifier"] == "identifier"
    assert "payload-value-one" not in snapshot
    assert "payload-value-two" in snapshot
    assert "payload-value-three" in snapshot
    assert "Home" not in snapshot
    assert snapshot["Ann"] == "name"


def test_registry_replaces_bounded_scope_and_uses_token_boundaries() -> None:
    registry = SensitiveValueRegistry(max_ephemeral_values=1, max_scoped_values=2)
    registry.replace_scope(
        "household:entry",
        (("Ann", "name"), ("id-one", "identifier"), ("id-two", "identifier")),
    )
    assert len(registry.snapshot()) == 2
    registry.replace_scope("household:entry", (("Bob", "name"),))
    assert registry.snapshot() == (("Bob", "name"),)

    original = privacy_module._REGISTRY
    privacy_module._REGISTRY = registry
    try:
        assert redact_text("Annual diagnostic") == "Annual diagnostic"
        assert redact_text("Child Bob failed") == "Child [REDACTED] failed"
    finally:
        privacy_module._REGISTRY = original


def test_nested_mapping_redacts_google_cookies_and_camel_case_ids() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "mapping", (), None)
    record.context = {
        "cookies": {"SID": "sid-canary", "__Secure-3PAPISID": "secure-canary"},
        "cookie_jar_copy": {
            "HSID": "hsid-canary",
            "SSID": "ssid-canary",
            "APISID": "apisid-canary",
            "SAPISID": "sapisid-canary",
        },
        "nested": {
            "userId": "user-canary",
            "deviceId": "device-canary",
            "accountId": "account-canary",
            "overrideId": "override-canary",
            "count": 2,
            "grid": "safe-diagnostic-word",
        },
    }
    FamilyLinkRedactionFilter().filter(record)
    rendered = str(record.context)
    for canary in (
        "sid-canary", "secure-canary", "hsid-canary", "ssid-canary",
        "apisid-canary", "sapisid-canary", "user-canary", "device-canary",
        "account-canary", "override-canary",
    ):
        assert canary not in rendered
    assert record.context["nested"]["count"] == 2
    assert record.context["nested"]["grid"] == "safe-diagnostic-word"


def test_unknown_json_identifier_is_redacted_without_registration() -> None:
    redacted = redact_text(
        '{"newOpaqueId": "unknown-json-id-canary", "grid": "safe-word", "count": 2}'
    )
    assert "unknown-json-id-canary" not in redacted
    assert '"grid": "safe-word"' in redacted
    assert '"count": 2' in redacted


def test_identifier_boundaries_do_not_redact_embedded_hyphen_or_underscore() -> None:
    registry = SensitiveValueRegistry()
    registry.register("opaque-id", kind="identifier")
    original = privacy_module._REGISTRY
    privacy_module._REGISTRY = registry
    try:
        assert redact_text("opaque-id") == "[REDACTED]"
        assert redact_text("prefix_opaque-id_suffix") == "prefix_opaque-id_suffix"
        assert redact_text("prefix-opaque-id-suffix") == "prefix-opaque-id-suffix"
    finally:
        privacy_module._REGISTRY = original


def test_mapping_key_classification_redacts_credentials_without_false_positives() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "mapping", (), None)
    secret_keys = (
        "apiKey", "accessToken", "refreshToken", "idToken", "authorization",
        "cookie", "cookies", "credential", "password", "secret", "session",
        "google_access_token", "accountId",
    )
    safe_keys = ("token_count", "session_count", "secretary", "grid")
    record.context = {
        **{key: f"{key}-canary" for key in secret_keys},
        **{key: f"{key}-safe" for key in safe_keys},
    }

    FamilyLinkRedactionFilter().filter(record)

    for key in secret_keys:
        assert record.context[key] == "[REDACTED]"
    for key in safe_keys:
        assert record.context[key] == f"{key}-safe"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("start_time", "day", "message"),
    (("99:99", 1, "Invalid time"), ("20:00", 8, "Invalid day")),
)
async def test_set_bedtime_validation_reaches_service_boundary_unchanged(
    start_time: str, day: int, message: str
) -> None:
    client = object.__new__(FamilyLinkClient)
    client._cookies = [{}]
    client._account_id = "account-id"
    client._get_session = AsyncMock()

    with pytest.raises(FamilyLinkValidationError, match=message):
        await client.async_set_bedtime(start_time, "07:00", day=day)

    @_privacy_safe_handler
    async def handler(call) -> None:
        await client.async_set_bedtime(
            call.data["start_time"], "07:00", day=call.data["day"]
        )

    with pytest.raises(FamilyLinkValidationError, match=message):
        await handler(SimpleNamespace(data={"start_time": start_time, "day": day}))


@pytest.mark.asyncio
async def test_boundaries_pass_deliberate_and_framework_errors_by_identity() -> None:
    """HA, cancellation, and deliberate validation semantics survive."""
    errors = (
        Unauthorized(),
        HomeAssistantError("weekday error"),
        asyncio.CancelledError(),
        FamilyLinkValidationError("Invalid day: 8. Must be 1-7 (Monday-Sunday)"),
    )

    for error in errors:
        @privacy_safe_entity_action
        async def action() -> None:
            raise error

        with pytest.raises(type(error)) as raised:
            await action()
        assert raised.value is error


@pytest.mark.asyncio
async def test_transport_familylink_exception_is_wrapped_at_entity_boundary() -> None:
    @privacy_safe_entity_action
    async def action() -> None:
        raise FamilyLinkException("Cookie: SID=transport-canary")

    with pytest.raises(HomeAssistantError) as raised:
        await action()
    assert str(raised.value) == "The Family Link entity action failed"


@pytest.mark.asyncio
async def test_unexpected_boundary_error_is_stable_and_traceback_sanitized(caplog) -> None:
    """Unexpected service/entity errors expose stable text and retain safe frames."""
    get_privacy_logger("custom_components.familylink")
    @privacy_safe_entity_action
    async def action() -> None:
        raise RuntimeError("token=exception-canary")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(HomeAssistantError) as raised:
            await action()
    assert str(raised.value) == "The Family Link entity action failed"
    assert "exception-canary" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "action" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_boundary_preserves_cache_and_sanitizes_update_failure(caplog) -> None:
    get_privacy_logger("custom_components.familylink")
    coordinator = object.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator._auth_notification_sent = False
    coordinator._is_retrying_auth = False
    coordinator._last_known_data = None

    async def fail_fetch():
        raise RuntimeError("coordinator-canary")

    coordinator._async_fetch_data = fail_fetch
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(UpdateFailed, match="^Family Link update failed$"):
            await coordinator._async_update_data()
    assert "coordinator-canary" not in caplog.text
    assert "RuntimeError" in caplog.text

    coordinator._last_known_data = {"cached": True}
    assert await coordinator._async_update_data() == {"cached": True}


@pytest.mark.asyncio
async def test_setup_boundary_passes_ha_errors_and_wraps_unexpected(
    monkeypatch, caplog
) -> None:
    for error in (Unauthorized(), ConfigEntryNotReady("retry")):
        coordinator = SimpleNamespace(async_load_strict_intents=AsyncMock(side_effect=error))
        monkeypatch.setattr(
            familylink, "FamilyLinkDataUpdateCoordinator", lambda hass, entry: coordinator
        )
        with pytest.raises(type(error)) as raised:
            await familylink.async_setup_entry(SimpleNamespace(), SimpleNamespace())
        assert raised.value is error

    coordinator = SimpleNamespace(
        async_load_strict_intents=AsyncMock(side_effect=RuntimeError("setup-canary"))
    )
    monkeypatch.setattr(
        familylink, "FamilyLinkDataUpdateCoordinator", lambda hass, entry: coordinator
    )
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ConfigEntryNotReady, match="^Unable to set up Family Link$"):
            await familylink.async_setup_entry(SimpleNamespace(), SimpleNamespace())
    assert "setup-canary" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "async_setup_entry" in caplog.text


@pytest.mark.asyncio
async def test_service_boundary_registers_payload_before_failure(caplog) -> None:
    handlers = {}

    class Services:
        def async_register(self, domain, service, handler, **kwargs):
            handlers[service] = handler

    coordinator = SimpleNamespace(
        client=SimpleNamespace(
            async_block_app=AsyncMock(side_effect=RuntimeError("package-canary"))
        ),
        async_request_refresh=AsyncMock(),
    )
    hass = SimpleNamespace(services=Services(), states=SimpleNamespace(get=lambda _: None))
    await async_setup_services(hass, coordinator)
    call = SimpleNamespace(data={"package_name": "package-canary", "child_id": "id-canary"})

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(HomeAssistantError, match="^The Family Link service action failed$"):
            await handlers["block_app"](call)
    assert "package-canary" not in caplog.text
    assert "id-canary" not in caplog.text


@pytest.mark.asyncio
async def test_service_boundary_wraps_transport_familylink_exception() -> None:
    @_privacy_safe_handler
    async def handler(call) -> None:
        raise FamilyLinkException("transport failed Cookie: SID=service-canary")

    with pytest.raises(
        HomeAssistantError, match="^The Family Link service action failed$"
    ):
        await handler(SimpleNamespace(data={}))


def test_live_attributes_and_primary_state_remain_available() -> None:
    coordinator = SimpleNamespace(
        last_update_success=True,
        data={
            "children_data": [{
                "child_id": "child-id-canary",
                "child_name": "minor-name-canary",
                "screen_time": {
                    "total_seconds": 600, "formatted": "00:10:00", "hours": 0,
                    "minutes": 10, "seconds": 0, "app_breakdown": {},
                },
            }]
        },
    )
    entity = sensor.FamilyLinkScreenTimeSensor(
        coordinator, "total", "child-id-canary", "minor-name-canary"
    )
    assert entity.native_value == 10.0
    assert entity.extra_state_attributes["child_id"] == "child-id-canary"
    assert entity.extra_state_attributes["child_name"] == "minor-name-canary"


def test_compact_operational_attributes_remain_recordable() -> None:
    """Requested compact values are not accidentally excluded from Recorder."""
    assert "formatted_time" not in sensor.FamilyLinkScreenTimeSensor._unrecorded_attributes
    assert "date" not in sensor.FamilyLinkScreenTimeSensor._unrecorded_attributes
    assert "date" not in (
        sensor.FamilyLinkScreenTimeFormattedSensor._unrecorded_attributes
    )
    assert "formatted_time" not in sensor.FamilyLinkTopAppSensor._unrecorded_attributes
    assert {"device_type", "model"}.isdisjoint(
        switch.FamilyLinkDeviceSwitch._unrecorded_attributes
    )
