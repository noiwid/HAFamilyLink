"""IDs interpolated into API URL paths must be exactly letters, digits, '_' and '-'."""

from __future__ import annotations

import pytest

from custom_components.familylink.client.api import FamilyLinkClient


@pytest.mark.parametrize("value", ["123456789", "abc_DEF-9", "x"])
def test_valid_ids_pass_through(value) -> None:
    assert FamilyLinkClient._validate_id(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "../x", "a/b", "a b", "x?y=1", "a#b", "id\n", "id\r\n", "\nid", "id\n\n"],
)
def test_ids_that_could_alter_the_url_are_rejected(value) -> None:
    with pytest.raises(ValueError, match="Invalid"):
        FamilyLinkClient._validate_id(value)
