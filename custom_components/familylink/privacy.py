"""Privacy-safe logging for the Family Link integration."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
import logging
import re
import threading
from typing import Any, Literal
from urllib.parse import unquote

REDACTED = "[REDACTED]"
REDACTED_URL = "[REDACTED_URL]"
_MAX_EPHEMERAL_VALUES = 2048
_MAX_SCOPED_VALUES = 4096
_FILTER_MARKER = "_familylink_privacy_filter"
_FILTER_LOCK = threading.Lock()
_MAX_DECODE_PASSES = 3

SensitiveValueKind = Literal["identifier", "credential", "name", "ephemeral"]

_SENSITIVE_KEY = re.compile(
    r"(?i)^(?:api[_-]?key|authorization|cookies?|credential|password|secret|"
    r"sapisidhash|session|token|package(?:_?name)?|address|latitude|longitude|"
    r"coordinates?|response[_-]?text|payload|body)$"
)
_COOKIE_KEY = re.compile(
    r"(?i)^(?:(?:__secure-|__host-).+|sid|hsid|ssid|apisid|sapisid|nid|aid|"
    r"oauth_token|gaps|lsid|osid|sidcc|__secure-1psid|__secure-3psid|"
    r"__secure-1papisid|__secure-3papisid)$"
)
_HEADER_VALUE = re.compile(
    r"(?im)\b(Cookie|Set-Cookie|Authorization)(\s*:\s*)[^\r\n]*"
)
_COOKIE_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])((?:__Secure-|__Host-)?[A-Za-z0-9_-]*SID)\s*=\s*"
    r"[^\s;,]+"
)
_LABELED_VALUE = re.compile(
    r"(?i)\b(api[_ -]?key|credential|password|secret|sapisidhash|session|token|"
    r"address|latitude|longitude|coordinates?|payload|body)(\s*[:=]\s*)"
    r"(?!%)([^\s,;]+|\[[^]]*\]|\{[^}]*\})"
)
_AUTH_VALUE = re.compile(r"(?i)\b(?:bearer|sapisidhash)\s+[A-Za-z0-9._~+/=-]+")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_URL = re.compile(r"(?i)\b(?:https?|wss?)://[^\s'\"<>]+")
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:api[_-]?key|auth|authorization|cookie|credential|password|"
    r"secret|sapisidhash|session|token)=)[^&#\s]+"
)
_JSON_STRING_PAIR = re.compile(
    r'(?P<prefix>["\'](?P<key>[^"\']+)["\']\s*:\s*["\'])'
    r'(?P<value>[^"\']+)(?P<suffix>["\'])'
)
_COORDINATES = re.compile(
    r"(?i)\b(?:lat(?:itude)?|lon(?:gitude)?|lng|coordinates?)\b"
    r"\s*[:=]?\s*-?\d{1,3}(?:\.\d+)?(?:\s*[,/]\s*-?\d{1,3}(?:\.\d+)?)?"
)
_GENERIC_NAMES = frozenset(
    {
        "admin",
        "android",
        "child",
        "device",
        "family",
        "google",
        "home",
        "phone",
        "tablet",
        "unknown",
        "user",
    }
)
_LOG_RECORD_FIELDS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


class SensitiveValueRegistry:
    """Thread-safe registry of bounded replaceable and ephemeral values."""

    def __init__(
        self,
        max_ephemeral_values: int = _MAX_EPHEMERAL_VALUES,
        max_scoped_values: int = _MAX_SCOPED_VALUES,
    ) -> None:
        self._max_ephemeral_values = max_ephemeral_values
        self._max_scoped_values = max_scoped_values
        self._scopes: dict[str, dict[str, SensitiveValueKind]] = {}
        self._ephemeral: deque[tuple[str, SensitiveValueKind]] = deque()
        self._ephemeral_known: set[str] = set()
        self._lock = threading.RLock()

    def register(
        self, *values: object, kind: SensitiveValueKind = "ephemeral"
    ) -> None:
        """Register nested strings in the bounded transient queue."""
        self.register_ephemeral(*values, kind=kind)

    def register_ephemeral(
        self, *values: object, kind: SensitiveValueKind = "ephemeral"
    ) -> None:
        """Register typed values in the bounded transient queue."""
        with self._lock:
            for value in _iter_strings(values):
                if not _should_register(value, kind) or value in self._ephemeral_known:
                    continue
                while len(self._ephemeral) >= self._max_ephemeral_values:
                    self._ephemeral_known.discard(self._ephemeral.popleft()[0])
                self._ephemeral.append((value, kind))
                self._ephemeral_known.add(value)

    def replace_scope(
        self,
        scope: str,
        values: Iterable[tuple[str, SensitiveValueKind]],
    ) -> None:
        """Atomically replace one bounded configuration/snapshot category."""
        replacement: dict[str, SensitiveValueKind] = {}
        for value, kind in values:
            if _should_register(value, kind):
                replacement[value] = kind
            if len(replacement) >= self._max_scoped_values:
                break
        with self._lock:
            self._scopes[scope] = replacement

    def clear_scope(self, scope: str) -> None:
        """Remove values retained for one configuration/snapshot category."""
        with self._lock:
            self._scopes.pop(scope, None)

    def snapshot(self) -> tuple[tuple[str, SensitiveValueKind], ...]:
        """Return longest values first to avoid partial replacement."""
        with self._lock:
            values = [item for scope in self._scopes.values() for item in scope.items()]
            values.extend(self._ephemeral)
            return tuple(sorted(values, key=lambda item: len(item[0]), reverse=True))


def _should_register(value: str, kind: SensitiveValueKind) -> bool:
    """Reject values likely to cause broad, low-value substring redaction."""
    normalized = value.strip()
    if kind == "name":
        return len(normalized) >= 3 and normalized.casefold() not in _GENERIC_NAMES
    if kind == "identifier":
        return len(normalized) >= 3
    if kind == "credential":
        return len(normalized) >= 4
    return len(normalized) >= 8


def _iter_strings(values: Iterable[object]) -> Iterable[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            yield value
        elif isinstance(value, Mapping):
            yield from _iter_strings(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            yield from _iter_strings(value)


_REGISTRY = SensitiveValueRegistry()


def register_sensitive_values(
    *values: object, kind: SensitiveValueKind = "ephemeral"
) -> None:
    """Register values before any diagnostic message can include them."""
    _REGISTRY.register(*values, kind=kind)


def register_household_data(value: object) -> None:
    """Register service/entity/API values in the bounded ephemeral queue."""
    for item, kind in _household_values(value):
        _REGISTRY.register_ephemeral(item, kind=kind)


def replace_household_snapshot(scope: str, value: object) -> None:
    """Replace the durable identifiers and names for one config entry refresh."""
    _REGISTRY.replace_scope(f"household:{scope}", _household_values(value))


def clear_household_snapshot(scope: str) -> None:
    """Clear retained household identifiers for an unloaded config entry."""
    _REGISTRY.clear_scope(f"household:{scope}")


def _household_values(value: object) -> Iterable[tuple[str, SensitiveValueKind]]:
    """Yield typed sensitive strings from nested household structures."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            kind: SensitiveValueKind | None = None
            normalized_key = _normalized_key(key)
            if _identifier_key(str(key)):
                kind = "identifier"
            elif _credential_key(key):
                kind = "credential"
            elif normalized_key in {
                "name",
                "title",
                "displayname",
                "childname",
                "devicename",
                "givenname",
                "familyname",
                "friendlyname",
                "placename",
                "sourcedevicename",
            }:
                kind = "name"
            elif _SENSITIVE_KEY.search(normalized_key):
                kind = "ephemeral"
            if kind is not None:
                for text in _iter_strings((item,)):
                    yield text, kind
            if isinstance(item, (Mapping, list, tuple)):
                yield from _household_values(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _household_values(item)


def _normalized_key(key: object) -> str:
    """Normalize snake/kebab/camel keys for reliable classification."""
    return re.sub(r"[^a-z0-9]", "", str(key).casefold())


def _sensitive_mapping_key(key: object) -> bool:
    """Return whether a mapping key identifies a value that must be hidden."""
    text = str(key)
    return bool(
        _identifier_key(text)
        or _SENSITIVE_KEY.fullmatch(text)
        or _COOKIE_KEY.fullmatch(text)
        or _credential_key(key)
    )


_CREDENTIAL_FIELD_NAMES = frozenset(
    {
        "apikey",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "authorization",
        "cookie",
        "cookies",
        "credential",
        "password",
        "secret",
        "session",
        "token",
    }
)


def _credential_key(key: object) -> bool:
    """Classify credential fields using exact names and real word suffixes."""
    text = str(key)
    normalized = _normalized_key(text)
    if normalized in _CREDENTIAL_FIELD_NAMES:
        return True
    words = [
        word.casefold()
        for word in re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
        .replace("-", " ")
        .replace("_", " ")
        .split()
    ]
    return any(
        "".join(words[-count:]) in _CREDENTIAL_FIELD_NAMES
        for count in (1, 2)
        if len(words) >= count
    )


def _identifier_key(key: str) -> bool:
    """Recognize explicit snake/kebab/camel identifier fields, not words."""
    return bool(
        key.casefold() == "id"
        or re.search(r"(?:^|[_-])id$", key, re.IGNORECASE)
        or re.search(r"[a-z0-9]Id$", key)
    )


def _decoded_sensitive_text(text: str) -> str:
    """Decode bounded percent-encoding only when it reveals sensitive syntax."""
    decoded = text
    for _ in range(_MAX_DECODE_PASSES):
        candidate = unquote(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    if any(
        pattern.search(decoded)
        for pattern in (
            _URL,
            _QUERY_SECRET,
            _HEADER_VALUE,
            _COOKIE_ASSIGNMENT,
            _AUTH_VALUE,
            _LABELED_VALUE,
        )
    ):
        return decoded
    return text


def redact_text(value: object) -> str:
    """Return text with static and dynamically discovered secrets removed."""
    text = _decoded_sensitive_text(str(value))
    text = _HEADER_VALUE.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", text)
    text = _COOKIE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    text = _URL.sub(REDACTED_URL, text)
    text = _QUERY_SECRET.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
    text = _AUTH_VALUE.sub(REDACTED, text)
    text = _EMAIL.sub(REDACTED, text)
    text = _COORDINATES.sub(REDACTED, text)
    text = _JSON_STRING_PAIR.sub(_redact_json_pair, text)
    text = _LABELED_VALUE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", text
    )
    for sensitive, kind in _REGISTRY.snapshot():
        if kind == "identifier":
            text = re.sub(
                rf"(?<![A-Za-z0-9_-]){re.escape(sensitive)}(?![A-Za-z0-9_-])",
                REDACTED,
                text,
                flags=re.IGNORECASE,
            )
        elif kind == "name":
            text = re.sub(
                rf"\b{re.escape(sensitive)}\b",
                REDACTED,
                text,
                flags=re.IGNORECASE,
            )
        else:
            text = text.replace(sensitive, REDACTED)
    return text


def _redact_value(value: Any, key: str | None = None) -> Any:
    if key is not None and _sensitive_mapping_key(key):
        return REDACTED
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {REDACTED}"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            item_key: _redact_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, set):
        return {_redact_value(item) for item in value}
    return value


def _redact_json_pair(match: re.Match[str]) -> str:
    """Redact JSON-like string values only when their key is sensitive."""
    if not _sensitive_mapping_key(match.group("key")):
        return match.group(0)
    return f'{match.group("prefix")}{REDACTED}{match.group("suffix")}'


class FamilyLinkRedactionFilter(logging.Filter):
    """Redact all message, exception, and structured-extra record fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.msg)
        if isinstance(record.args, Mapping):
            record.args = _redact_value(record.args)
        elif record.args:
            record.args = tuple(_redact_value(arg) for arg in record.args)

        for key in tuple(record.__dict__):
            if key not in _LOG_RECORD_FIELDS:
                record.__dict__[key] = _redact_value(record.__dict__[key], key)

        if record.exc_info:
            record.exc_text = _format_exception(record.exc_info[1])
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        return True


def _format_exception(error: BaseException) -> str:
    """Render traceback frames and exception types without exception messages."""
    sections: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        frames = []
        trace = current.__traceback__
        while trace is not None:
            frame = trace.tb_frame
            frames.append(
                f'  File "{frame.f_code.co_filename}", line {trace.tb_lineno}, '
                f'in {frame.f_code.co_name}'
            )
            trace = trace.tb_next
        sections.append(
            "Traceback (most recent call last):\n"
            + "\n".join(frames)
            + f"\n{type(current).__name__}: {REDACTED}"
        )
        current = current.__cause__ or (
            current.__context__ if not current.__suppress_context__ else None
        )
    return "\nThe above exception was caused by:\n".join(reversed(sections))


def get_privacy_logger(name: str) -> logging.Logger:
    """Return a module logger with one idempotently installed filter."""
    logger = logging.getLogger(name)
    with _FILTER_LOCK:
        if not any(getattr(item, _FILTER_MARKER, False) for item in logger.filters):
            filter_ = FamilyLinkRedactionFilter()
            setattr(filter_, _FILTER_MARKER, True)
            logger.addFilter(filter_)
    return logger
