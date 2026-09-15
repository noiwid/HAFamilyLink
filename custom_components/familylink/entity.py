"""Shared entity helpers for the Family Link integration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from homeassistant.exceptions import HomeAssistantError

from .exceptions import FamilyLinkException, FamilyLinkValidationError
from .privacy import get_privacy_logger, register_household_data

_P = ParamSpec("_P")
_ResultT = TypeVar("_ResultT")

ENTITY_ACTION_ERROR = "The Family Link entity action failed"
_LOGGER = get_privacy_logger(__name__)


def async_error_boundary(
    error_message: str,
) -> Callable[
    [Callable[_P, Awaitable[_ResultT]]], Callable[_P, Awaitable[_ResultT]]
]:
    """Wrap an async HA entrypoint with a stable public error boundary."""

    def decorate(
        handler: Callable[_P, Awaitable[_ResultT]],
    ) -> Callable[_P, Awaitable[_ResultT]]:
        @wraps(handler)
        async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _ResultT:
            for arg in args:
                register_household_data(getattr(arg, "data", None))
                register_household_data(
                    {
                        "child_id": getattr(arg, "_child_id", None),
                        "child_name": getattr(arg, "_child_name", None),
                        "device_id": getattr(arg, "_device_id", None),
                        "device_name": getattr(arg, "_device_name", None),
                    }
                )
            try:
                return await handler(*args, **kwargs)
            except (
                HomeAssistantError,
                FamilyLinkValidationError,
                asyncio.CancelledError,
            ):
                raise
            except FamilyLinkException:
                _LOGGER.exception("Family Link transport error at HA entrypoint")
                raise HomeAssistantError(error_message) from None
            except Exception:
                _LOGGER.exception("Unexpected error in Family Link entrypoint")
                raise HomeAssistantError(error_message) from None

        return wrapped

    return decorate


privacy_safe_entity_action = async_error_boundary(ENTITY_ACTION_ERROR)
