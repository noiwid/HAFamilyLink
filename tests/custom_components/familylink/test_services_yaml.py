"""services.yaml has no duplicated key.

YAML keeps the last value of a repeated key without an error: leftover lines
after the set_school_time "enabled" field turned its checkbox into a text list
in the action editor (Home Assistant only logs a warning at startup).
"""

from __future__ import annotations

from pathlib import Path

import yaml

SERVICES_YAML = Path(__file__).resolve().parents[3] / "custom_components" / "familylink" / "services.yaml"


class _StrictLoader(yaml.SafeLoader):
    pass


def _no_duplicates(loader, node, deep=False):
    keys = [loader.construct_object(key, deep=deep) for key, _ in node.value]
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    assert not duplicated, f"duplicated {duplicated} at {node.start_mark}"
    return loader.construct_mapping(node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def test_services_yaml_has_no_duplicated_key() -> None:
    services = yaml.load(SERVICES_YAML.read_text(encoding="utf-8"), Loader=_StrictLoader)

    assert services["set_school_time"]["fields"]["enabled"]["selector"] == {"boolean": None}
