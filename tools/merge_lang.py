#!/usr/bin/env python3
"""Merge a flat translation map from a JSON file into `translations/<lang>.json`.

Structure and key order come from `en.json` (the complete base). Keys that are
already translated are left untouched; only gaps are filled.

Usage: python3 tools/merge_lang.py <lang> <translations.json>
Input file: a flat object {"entity.select.web_filter.name": "...", ...}.
The script refuses to write when keys are missing or unexpected, or when
`{...}` placeholders do not match `en.json`.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

BASE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "familylink"
    / "translations"
)
PH = re.compile(r"\{(\w+)\}")


def flat(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flat(value, path))
        else:
            out[path] = value
    return out


def build(en: dict, cur: dict, tr: dict[str, str], prefix: str = "") -> dict:
    """Build a dict following the English structure: keep existing or use new."""
    out: dict = {}
    for key, value in en.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            sub = cur.get(key) if isinstance(cur, dict) else None
            out[key] = build(value, sub if isinstance(sub, dict) else {}, tr, path)
        else:
            old = cur.get(key) if isinstance(cur, dict) else None
            out[key] = old if isinstance(old, str) else tr[path]
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    lang, src = sys.argv[1], pathlib.Path(sys.argv[2])
    en = json.loads((BASE / "en.json").read_text(encoding="utf-8"))
    path = BASE / f"{lang}.json"
    cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    tr = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(tr, dict):
        print("ERROR: the input file must be a flat JSON object")
        return 1

    en_f, cur_f = flat(en), flat(cur)
    need = set(en_f) - set(cur_f)
    missing = sorted(need - set(tr))
    extra = sorted(set(tr) - need)
    empty = sorted(k for k in tr if not isinstance(tr[k], str) or not tr[k].strip())
    bad = sorted(
        k
        for k in tr
        if k in en_f
        and isinstance(tr[k], str)
        and set(PH.findall(tr[k])) != set(PH.findall(en_f[k]))
    )

    if missing:
        print(f"ERROR: {len(missing)} keys missing, e.g. {missing[:10]}")
    if extra:
        print(f"ERROR: {len(extra)} unexpected/already translated keys, e.g. {extra[:10]}")
    if empty:
        print(f"ERROR: {len(empty)} empty translations, e.g. {empty[:10]}")
    for k in bad[:10]:
        print(f"ERROR placeholder: {k} EN={sorted(PH.findall(en_f[k]))} -> {sorted(PH.findall(tr[k]))}")
    if bad:
        print(f"ERROR: {len(bad)} keys with mismatched placeholders")
    if missing or extra or empty or bad:
        return 1

    merged = build(en, cur, tr)
    path.write_text(
        json.dumps(merged, ensure_ascii=False, indent="\t") + "\n", encoding="utf-8"
    )
    merged_f = flat(merged)
    kept = sum(1 for k in cur_f if merged_f.get(k) == cur_f[k])
    print(
        f"{lang}: added {len(tr)} keys, kept {kept}/{len(cur_f)} existing, "
        f"total {len(merged_f)}/{len(en_f)} -> {path.name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
