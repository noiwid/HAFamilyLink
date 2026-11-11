"""Google Play settings (#239): the client's reading of settingResources, the coordinator's pace, the sensors.

The answers below keep the shape of real settingResources answers (2026-11-11),
cut down to the positions the client reads.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.familylink.client.api import FamilyLinkClient
from custom_components.familylink.const import WEBSITES_REFRESH
from custom_components.familylink.coordinator import FamilyLinkDataUpdateCoordinator
from custom_components.familylink.exceptions import NetworkError, SessionExpiredError
from custom_components.familylink.sensor import FamilyLinkPlaySettingSensor

CHILD = "child-1"
TEXT_STYLE = [None, [16, 2, 16], None, None, [5], [4, 4, 4, 4], None, [19], [16, 16, 16, 16]]


def _key(resource: str, subkey: str | None = None) -> list:
    return [resource, subkey, [CHILD]]


def _radio(resource: str, subkey: str | None, selected: str, options: dict[str, str]) -> list:
    """A radio group row: [key, 2, None, None, [selected, [option, ...]], ...]."""
    key = _key(resource, subkey)
    rows = [
        [value, None, [1, key, value], None, None, None, None, [None, None, None, None, None, [[label, [8]], None, *TEXT_STYLE]]]
        for value, label in options.items()
    ]
    return [key, 2, None, None, [selected, rows], None, None, None, None, [154429]]


def _page(*categories: str) -> list:
    """The Google Play page: a title row, then one "11" row per content category."""
    rows = [[_key("2"), 2, [["Google Play", [10]], None, None, [_key("8"), *(_key("11", c) for c in categories)]]]]
    rows += [[_key("11", c), 2, None, [None, _key("4", c)], None, None, None, None, None, [154412]] for c in categories]
    return rows


APPROVALS = {"4": "All content", "3": "Paid content only", "2": "In-app purchases only", "1": "Never"}
RATINGS = {"1": "PEGI 3", "2": "PEGI 7", "3": "PEGI 12", "4": "PEGI 16", "5": "PEGI 18", "0": "Allow all"}


def _client(*answers, status: int = 200) -> tuple[FamilyLinkClient, MagicMock]:
    client = FamilyLinkClient.__new__(FamilyLinkClient)
    client.is_authenticated = MagicMock(return_value=True)
    client._get_cookie_header = MagicMock(return_value="SID=x")
    texts = [a if isinstance(a, str) else json.dumps(a) for a in answers]

    class _Resp:
        def __init__(self, text):
            self.status = status
            self._text = text

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def text(self):
            return self._text

    session = MagicMock()
    session.post = MagicMock(side_effect=[_Resp(t) for t in texts])
    client._get_session = AsyncMock(return_value=session)
    return client, session


# --- client -------------------------------------------------------------------


async def test_the_rating_is_read_under_the_category_label_google_returned() -> None:
    # A French answer: the subkey of the rating is the label of the first category
    page = [[*_page("Applications et jeux", "Films", "Télévision", "Livres"), _radio("7", None, "3", APPROVALS)]]
    client, session = _client(page, [[_radio("13", "Applications et jeux", "4", RATINGS)]])

    settings = await client.async_get_play_settings(CHILD)

    assert settings == {
        "approval": {"value": "3", "label": "Paid content only", "options": APPROVALS},
        "apps_rating": {"value": "4", "label": "PEGI 16", "options": RATINGS},
    }
    first, second = session.post.call_args_list
    assert first.args[0].endswith("/people/settingResources")  # a read, never :performAction
    assert json.loads(first.kwargs["data"]) == [None, [_key("2"), _key("7")], [[1, 3, 4, 5, 6], 1]]
    assert json.loads(second.kwargs["data"]) == [None, [_key("13", "Applications et jeux")], [[1, 3, 4, 5, 6], 1]]
    assert first.kwargs["headers"]["Accept-Language"] == "en"


@pytest.mark.parametrize("answer", [[], [[]], {}, [[["7"], [_key("7"), 2, None, None, None]]], [[[_key("7"), 2, None, None, [3, []]]]]])
async def test_a_setting_google_does_not_return_is_none(answer) -> None:
    # No category row either: the rating is not asked for
    client, session = _client(answer)
    assert await client.async_get_play_settings(CHILD) == {"approval": None, "apps_rating": None}
    assert session.post.call_count == 1


async def test_a_label_that_moved_does_not_hide_the_value() -> None:
    row = _radio("7", None, "1", APPROVALS)
    for option in row[4][1]:
        del option[7]
    client, _ = _client([[row]])
    assert (await client.async_get_play_settings(CHILD))["approval"] == {"value": "1", "label": None, "options": {}}


@pytest.mark.parametrize(("status", "error"), [(401, SessionExpiredError), (500, NetworkError)])
async def test_a_refused_read_raises(status, error) -> None:
    client, _ = _client([], status=status)
    with pytest.raises(error):
        await client.async_get_play_settings(CHILD)


async def test_an_answer_that_is_not_json_raises() -> None:
    client, _ = _client("<html>")
    with pytest.raises(NetworkError):
        await client.async_get_play_settings(CHILD)


# --- coordinator --------------------------------------------------------------


async def test_coordinator_reads_the_settings_at_most_every_refresh_interval(monkeypatch) -> None:
    clock = [1000.0]
    monkeypatch.setattr("custom_components.familylink.coordinator.time", SimpleNamespace(monotonic=lambda: clock[0]))
    coordinator = FamilyLinkDataUpdateCoordinator.__new__(FamilyLinkDataUpdateCoordinator)
    coordinator._play_settings = {}
    coordinator._play_settings_warned = set()
    read = AsyncMock(side_effect=[{"approval": None, "apps_rating": None}, NetworkError("HTTP 503")])
    coordinator.client = SimpleNamespace(async_get_play_settings=read)

    first = await coordinator._async_child_play_settings(CHILD, "Alex")
    clock[0] += WEBSITES_REFRESH - 1
    assert await coordinator._async_child_play_settings(CHILD, "Alex") is first
    assert read.await_count == 1

    # A failed read keeps the last settings
    clock[0] += 2
    assert await coordinator._async_child_play_settings(CHILD, "Alex") is first
    assert read.await_count == 2


# --- sensors ------------------------------------------------------------------


def _sensor(kind: str, play_settings) -> FamilyLinkPlaySettingSensor:
    coordinator = MagicMock()
    coordinator.last_update_success = True
    coordinator.data = {"children_data": [{"child_id": CHILD, "play_settings": play_settings}]}
    return FamilyLinkPlaySettingSensor(coordinator, CHILD, "Alex", kind)


def test_the_sensors_show_the_mode_name_and_the_rating_label() -> None:
    settings = {
        "approval": {"value": "3", "label": "Paid content only", "options": APPROVALS},
        "apps_rating": {"value": "4", "label": "PEGI 16", "options": RATINGS},
    }
    approval = _sensor("approval", settings)
    assert approval.available
    assert approval.native_value == "paid_content"
    assert approval.native_value in approval.options
    assert approval.unique_id == f"familylink_{CHILD}_play_approval"
    assert approval.extra_state_attributes["label"] == "Paid content only"

    rating = _sensor("apps_rating", settings)
    assert rating.native_value == "PEGI 16"
    assert rating.extra_state_attributes["value"] == "4"
    assert rating.extra_state_attributes["choices"] == list(RATINGS.values())


def test_the_sensors_are_unknown_or_unavailable_without_a_reading() -> None:
    # A mode added by Google is unknown, not an invalid enum state
    assert _sensor("approval", {"approval": {"value": "9", "label": "New", "options": {}}, "apps_rating": None}).native_value is None
    # Read, but Google returned no rating: unknown
    rating = _sensor("apps_rating", {"approval": None, "apps_rating": None})
    assert rating.available and rating.native_value is None
    # Never read: unavailable
    assert not _sensor("approval", None).available
