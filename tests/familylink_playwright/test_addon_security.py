"""Auth add-on: cookie endpoint key and login session start.

Run with the add-on's own dependencies (see the "Auth add-on" job in tests.yml),
not inside the Home Assistant harness.
"""
import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "familylink-playwright"))

from app import config as addon_config  # noqa: E402
from app.auth.browser import BrowserAuthManager  # noqa: E402


@pytest.fixture
def standalone_app(tmp_path, monkeypatch):
    """app.main imported fresh as a standalone container without API_KEY."""
    from fastapi.testclient import TestClient

    for var in ("API_KEY", "ADDON_MODE", "SUPERVISOR_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(addon_config, "get_config", lambda: addon_config.Config(share_dir=str(tmp_path)))
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    yield main, TestClient(main.app), tmp_path
    sys.modules.pop("app.main", None)


def test_standalone_cookie_endpoint_requires_the_generated_key(standalone_app):
    main, client, share = standalone_app
    key = (share / "api_key").read_text()
    assert key and main._COOKIE_API_KEY == key

    assert client.get("/api/cookies").status_code == 403
    assert client.get("/api/cookies", headers={"X-API-Key": "wrong"}).status_code == 403
    # A non-ASCII key used to raise inside compare_digest: 500 instead of 403
    assert client.get("/api/cookies", params={"api_key": "é"}).status_code == 403
    assert client.delete("/api/cookies").status_code == 403
    # No cookies stored yet: past the key check
    assert client.get("/api/cookies", headers={"X-API-Key": key}).status_code == 404


def test_generated_key_survives_a_restart(standalone_app, monkeypatch):
    main, _, share = standalone_app
    first = main._COOKIE_API_KEY
    sys.modules.pop("app.main", None)
    assert importlib.import_module("app.main")._COOKIE_API_KEY == first


def _fake_playwright(goto):
    page = MagicMock()
    page.goto = goto
    page.close = AsyncMock()
    context = MagicMock()
    context.new_page = AsyncMock(return_value=page)
    context.close = AsyncMock()
    browser = MagicMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    async def launch(*args, **kwargs):
        await asyncio.sleep(0.01)  # a real launch takes seconds and yields to other requests
        return browser

    playwright = MagicMock()
    playwright.chromium.launch = AsyncMock(side_effect=launch)
    return playwright


async def test_failed_navigation_does_not_block_the_next_login():
    manager = BrowserAuthManager()
    manager._playwright = _fake_playwright(AsyncMock(side_effect=TimeoutError("goto timed out")))

    with pytest.raises(TimeoutError):
        await manager.start_auth_session()
    # Before the fix the dead session stayed "authenticating": RuntimeError here
    with pytest.raises(TimeoutError):
        await manager.start_auth_session()
    assert manager._sessions == {}


async def test_parallel_starts_launch_a_single_browser():
    release = asyncio.Event()

    async def slow_goto(*args, **kwargs):
        await release.wait()

    manager = BrowserAuthManager()
    manager._playwright = _fake_playwright(slow_goto)
    manager._monitor_authentication = AsyncMock()

    first = asyncio.create_task(manager.start_auth_session())
    second = asyncio.create_task(manager.start_auth_session())
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)

    assert isinstance(results[0], str)
    assert isinstance(results[1], RuntimeError)
    assert manager._playwright.chromium.launch.await_count == 1
