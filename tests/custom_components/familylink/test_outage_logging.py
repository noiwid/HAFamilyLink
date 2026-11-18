"""Google's 503 come in waves: one warning per wave, not five errors a minute.

Every read is retried at the next refresh and the last data is kept, so a 503
is not an error of the integration. The API layer logs it at debug and the
coordinator warns once.
"""

from __future__ import annotations

import logging

import pytest

from custom_components.familylink.client.api import _transient

from test_transient_fetch_errors import CHILD_ID, _client, _coordinator


@pytest.mark.parametrize(("status", "transient"), [(429, True), (500, True), (503, True), (401, False), (403, False), (404, False)])
def test_which_statuses_are_google_hiccups(status: int, transient: bool) -> None:
    assert _transient(status) is transient


async def test_a_503_is_not_logged_as_an_error_by_the_api_layer(caplog) -> None:
    caplog.set_level(logging.DEBUG)

    with pytest.raises(Exception):
        await _client(503).async_get_location(account_id=CHILD_ID)

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_a_lasting_refusal_is_still_an_error(caplog) -> None:
    caplog.set_level(logging.DEBUG)

    await _client(403).async_get_location(account_id=CHILD_ID)

    assert [r for r in caplog.records if r.levelno == logging.ERROR]


async def test_a_wave_of_failed_reads_warns_once(caplog) -> None:
    coordinator = _coordinator()
    caplog.set_level(logging.DEBUG)

    for _ in range(3):  # three refreshes during the same outage
        await coordinator._async_fetch_data()

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len([w for w in warnings if "applied time limits" in w]) == 1
    assert len([w for w in warnings if "location data" in w]) == 1
    # the lines are still there, at debug, for whoever looks
    assert len([r for r in caplog.records if r.levelno == logging.DEBUG and r.getMessage().startswith("Failed to fetch applied time limits")]) == 2


async def test_a_new_wave_warns_again(caplog, monkeypatch) -> None:
    from custom_components.familylink import coordinator as coordinator_module

    coordinator = _coordinator()
    clock = [1000.0]
    monkeypatch.setattr(coordinator_module.time, "monotonic", lambda: clock[0])
    caplog.set_level(logging.WARNING)

    await coordinator._async_fetch_data()
    clock[0] += 16 * 60  # the next wave, after the quiet period
    await coordinator._async_fetch_data()

    warnings = [r.getMessage() for r in caplog.records if "applied time limits" in r.getMessage()]
    assert len(warnings) == 2


@pytest.mark.parametrize("read", ["async_get_applied_time_limits", "async_get_time_limit", "async_get_contact_restriction"])
@pytest.mark.parametrize("status", [500, 503])
async def test_no_read_logs_a_google_hiccup_as_an_error(caplog, read: str, status: int) -> None:
    """The response body, the failure and its wrapper: three error lines per failed read, seen 2026-11-18."""
    caplog.set_level(logging.DEBUG)

    with pytest.raises(Exception):
        await getattr(_client(status), read)(account_id=CHILD_ID)

    assert not [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
