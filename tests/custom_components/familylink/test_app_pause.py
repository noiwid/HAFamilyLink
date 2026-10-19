"""pause_app / resume_app: what is stored, what is written, and what comes back."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.familylink.app_pause import (
    NO_LIMIT,
    UNLIMITED,
    app_limit_setting,
    async_setup_app_pause_services,
)
from custom_components.familylink.const import DOMAIN

CHILD = "child-1"
OTHER_CHILD = "child-2"
MESSAGES = "com.google.android.apps.messaging"
CHROME = "com.android.chrome"
YOUTUBE = "com.google.android.youtube"
GAME = "com.example.game"


def _app(package: str, **supervision) -> dict:
    return {"packageName": package, "supervisionSetting": supervision}


APPS = [
    _app(MESSAGES),
    _app(CHROME, usageLimit={"dailyUsageLimitMins": 45, "enabled": True}),
    _app(YOUTUBE, alwaysAllowedAppInfo={"alwaysAllowedState": "alwaysAllowedStateEnabled"}),
    _app(GAME, hidden=True),
]


@pytest.mark.parametrize(
    ("app", "expected"),
    [
        (_app(MESSAGES), NO_LIMIT),
        (_app(MESSAGES, usageLimit={"dailyUsageLimitMins": 45, "enabled": False}), NO_LIMIT),
        (_app(CHROME, usageLimit={"dailyUsageLimitMins": 45, "enabled": True}), 45),
        (_app(YOUTUBE, alwaysAllowedAppInfo={"alwaysAllowedState": "alwaysAllowedStateEnabled"}), UNLIMITED),
        (_app(YOUTUBE, alwaysAllowedAppInfo={"alwaysAllowedState": "alwaysAllowedStateDisabled"}), NO_LIMIT),
        (_app(GAME, hidden=True), None),
    ],
)
def test_app_limit_setting_reads_the_supervision_setting(app, expected) -> None:
    assert app_limit_setting(app) == expected


@pytest.fixture
async def pause_services(hass):
    client = SimpleNamespace(async_set_app_daily_limit=AsyncMock(return_value=True))
    coordinator = SimpleNamespace(
        client=client,
        data={"children_data": [{"child_id": CHILD, "apps": APPS}]},
        async_request_refresh=AsyncMock(),
    )
    await async_setup_app_pause_services(hass, coordinator)
    return coordinator


async def _call(hass, service, data):
    return await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=True)


def _writes(coordinator) -> list[tuple[str, int]]:
    return [(c.args[0], c.args[1]) for c in coordinator.client.async_set_app_daily_limit.await_args_list]


async def test_pause_sets_one_minute_and_skips_blocked_apps(hass, pause_services) -> None:
    result = await _call(hass, "pause_app", {"child_id": CHILD, "packages": [MESSAGES, CHROME, GAME]})

    assert result["paused"] == [MESSAGES, CHROME]
    assert result["skipped"] == {GAME: "blocked"}
    assert _writes(pause_services) == [(MESSAGES, 1), (CHROME, 1)]
    assert pause_services.client.async_set_app_daily_limit.await_args.kwargs["account_id"] == CHILD


async def test_resume_restores_each_setting_from_before_the_pause(hass, pause_services) -> None:
    await _call(hass, "pause_app", {"child_id": CHILD, "packages": [MESSAGES, CHROME, YOUTUBE]})
    pause_services.client.async_set_app_daily_limit.reset_mock()

    result = await _call(hass, "resume_app", {"child_id": CHILD})

    assert result["resumed"] == {MESSAGES: NO_LIMIT, CHROME: 45, YOUTUBE: UNLIMITED}
    assert _writes(pause_services) == [(MESSAGES, NO_LIMIT), (CHROME, 45), (YOUTUBE, UNLIMITED)]


async def test_a_second_pause_keeps_the_first_setting(hass, pause_services) -> None:
    await _call(hass, "pause_app", {"child_id": CHILD, "packages": [CHROME]})
    # The refresh now shows the paused limit of 1 minute
    pause_services.data["children_data"][0]["apps"] = [_app(CHROME, usageLimit={"dailyUsageLimitMins": 1, "enabled": True})]
    await _call(hass, "pause_app", {"child_id": CHILD, "packages": [CHROME]})

    result = await _call(hass, "resume_app", {"child_id": CHILD, "packages": [CHROME]})

    assert result["resumed"] == {CHROME: 45}


async def test_resume_only_touches_apps_it_paused(hass, pause_services) -> None:
    await _call(hass, "pause_app", {"child_id": CHILD, "packages": [MESSAGES]})
    pause_services.client.async_set_app_daily_limit.reset_mock()

    result = await _call(hass, "resume_app", {"child_id": CHILD, "packages": [CHROME, MESSAGES]})

    assert result["resumed"] == {MESSAGES: NO_LIMIT}
    assert result["not_paused"] == [CHROME]
    assert _writes(pause_services) == [(MESSAGES, NO_LIMIT)]

    again = await _call(hass, "resume_app", {"child_id": CHILD})
    assert again["resumed"] == {}


async def test_the_saved_settings_survive_a_restart(hass, pause_services) -> None:
    await _call(hass, "pause_app", {"child_id": CHILD, "packages": [CHROME]})
    hass.services.async_remove(DOMAIN, "pause_app")
    hass.services.async_remove(DOMAIN, "resume_app")
    await async_setup_app_pause_services(hass, pause_services)

    result = await _call(hass, "resume_app", {"child_id": CHILD})

    assert result["resumed"] == {CHROME: 45}


async def test_a_failed_write_raises_and_the_setting_is_still_saved(hass, pause_services) -> None:
    pause_services.client.async_set_app_daily_limit.return_value = False
    with pytest.raises(HomeAssistantError, match=CHROME):
        await _call(hass, "pause_app", {"child_id": CHILD, "packages": [CHROME]})

    pause_services.client.async_set_app_daily_limit.return_value = True
    result = await _call(hass, "resume_app", {"child_id": CHILD})
    assert result["resumed"] == {CHROME: 45}


async def test_a_pause_service_needs_a_child(hass, pause_services) -> None:
    with pytest.raises(ServiceValidationError, match="No child given"):
        await _call(hass, "pause_app", {"packages": [MESSAGES]})

    pause_services.client.async_set_app_daily_limit.assert_not_called()


def _slow_writes(coordinator) -> None:
    """Make every write yield to the event loop, as the network does."""

    async def write(package, minutes, account_id=None):
        for _ in range(5):
            await asyncio.sleep(0)
        return True

    coordinator.client.async_set_app_daily_limit = AsyncMock(side_effect=write)


async def test_pauses_for_two_children_at_once_both_keep_their_saved_setting(hass, pause_services) -> None:
    pause_services.data["children_data"].append({"child_id": OTHER_CHILD, "apps": APPS})
    _slow_writes(pause_services)

    await asyncio.gather(
        _call(hass, "pause_app", {"child_id": CHILD, "packages": [CHROME]}),
        _call(hass, "pause_app", {"child_id": OTHER_CHILD, "packages": [CHROME]}),
    )

    assert (await _call(hass, "resume_app", {"child_id": CHILD}))["resumed"] == {CHROME: 45}
    assert (await _call(hass, "resume_app", {"child_id": OTHER_CHILD}))["resumed"] == {CHROME: 45}


@pytest.mark.parametrize("first", ["pause_app", "resume_app"])
async def test_a_pause_and_a_resume_of_one_app_never_leave_it_paused_with_nothing_saved(
    hass, pause_services, first
) -> None:
    await _call(hass, "pause_app", {"child_id": CHILD, "packages": [CHROME]})
    _slow_writes(pause_services)

    calls = {
        "pause_app": _call(hass, "pause_app", {"child_id": CHILD, "packages": [CHROME]}),
        "resume_app": _call(hass, "resume_app", {"child_id": CHILD, "packages": [CHROME]}),
    }
    await asyncio.gather(*(calls[name] for name in (first, "resume_app" if first == "pause_app" else "pause_app")))

    last_write = _writes(pause_services)[-1]
    left = (await _call(hass, "resume_app", {"child_id": CHILD}))["resumed"]
    if last_write == (CHROME, 1):
        assert left == {CHROME: 45}
    else:
        assert last_write == (CHROME, 45)
        assert left == {}


async def test_resume_leaves_a_blocked_app_blocked_and_keeps_its_saved_setting(hass, pause_services) -> None:
    await _call(hass, "pause_app", {"child_id": CHILD, "packages": [MESSAGES, CHROME]})
    # The parent blocks Chrome while it is paused
    pause_services.data["children_data"][0]["apps"] = [_app(MESSAGES), _app(CHROME, hidden=True)]
    pause_services.client.async_set_app_daily_limit.reset_mock()

    result = await _call(hass, "resume_app", {"child_id": CHILD})

    assert result["resumed"] == {MESSAGES: NO_LIMIT}
    assert result["skipped"] == {CHROME: "blocked"}
    assert _writes(pause_services) == [(MESSAGES, NO_LIMIT)]

    # Once it is unblocked, the setting from before the pause is still there
    pause_services.data["children_data"][0]["apps"] = [_app(CHROME, usageLimit={"dailyUsageLimitMins": 1, "enabled": True})]
    again = await _call(hass, "resume_app", {"child_id": CHILD})
    assert again["resumed"] == {CHROME: 45}
    assert again["skipped"] == {}
