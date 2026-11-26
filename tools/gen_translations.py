#!/usr/bin/env python3
"""Generate entity and service translation entries for the familylink integration.

All entity/state texts live in `translation_source.json` (English base plus a
per-language overlay), keyed by the `translation_key` values used by the code.
Service texts in Polish live in `pl_services.json`. This script only assembles
the translation files, so adding a language means adding data, not Python.

Writes:
  - strings.json                -> "entity" + "services" sections (English)
  - translations/en.json        -> same content, used at runtime (English)
  - translations/pl.json        -> Polish runtime file, keeping existing sections
  - entity_keys.json            -> key inventory, for tools/validate.py
"""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
BASE = HERE.parent / "custom_components" / "familylink"
SOURCE = HERE / "translation_source.json"
PL_SERVICES = HERE / "pl_services.json"

# Language keys used inside translation_source.json, in entity_section() order.
LANGS = ("en", "pl")


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: pathlib.Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8"
    )


def entity_section(source: dict, lang: int) -> dict:
    """Build the "entity" block for one language (index into LANGS)."""
    out: dict[str, dict] = {}
    for domain, keys in source["entity"].items():
        if not keys:
            continue
        section: dict[str, dict] = {}
        for key, texts in keys.items():
            entry: dict = {"name": texts[LANGS[lang]]}
            states = source.get("states", {}).get(f"{domain}.{key}")
            if states:
                entry["state"] = {sk: sv[LANGS[lang]] for sk, sv in states.items()}
            section[key] = entry
        out[domain] = section
    return out


def services_section_en() -> dict:
    import yaml

    raw = yaml.safe_load((BASE / "services.yaml").read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for key, spec in raw.items():
        entry: dict = {}
        if spec.get("name"):
            entry["name"] = spec["name"]
        if spec.get("description"):
            entry["description"] = " ".join(spec["description"].split())
        fields = {}
        for fkey, fspec in (spec.get("fields") or {}).items():
            fentry = {}
            if fspec.get("name"):
                fentry["name"] = fspec["name"]
            if fspec.get("description"):
                fentry["description"] = " ".join(fspec["description"].split())
            fields[fkey] = fentry
        if fields:
            entry["fields"] = fields
        out[key] = entry
    return out


def services_section_pl() -> dict:
    if not PL_SERVICES.exists():
        return {}
    return load(PL_SERVICES)


def merge(path: pathlib.Path, entity: dict, services: dict) -> None:
    data = load(path)
    if entity:
        data["entity"] = entity
    if services:
        data["services"] = services
    dump(path, data)
    ents = sum(len(v) for v in (data.get("entity") or {}).values())
    print(f"{path.name}: entities {ents}, services {len(data.get('services') or {})}")


def main() -> None:
    source = load(SOURCE)
    en_ent, pl_ent = entity_section(source, 0), entity_section(source, 1)
    svc_en = services_section_en()
    svc_pl = services_section_pl()

    merge(BASE / "strings.json", en_ent, svc_en)
    merge(BASE / "translations" / "en.json", en_ent, svc_en)
    merge(BASE / "translations" / "pl.json", pl_ent, svc_pl or {})

    print(
        f"entity keys: {sum(len(v) for v in en_ent.values())} "
        f"(services EN: {len(svc_en)}, PL: {len(svc_pl)})"
    )
    dump(
        HERE / "entity_keys.json",
        {d: sorted(k) for d, k in source["entity"].items() if k},
    )


if __name__ == "__main__":
    main()
