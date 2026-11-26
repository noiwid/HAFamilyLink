#!/usr/bin/env python3
"""Validate translation keys: code <-> strings.json/en.json/pl.json, placeholders, services."""
from __future__ import annotations

import json
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "familylink"
PLATFORMS = {
    "sensor.py": "sensor",
    "switch.py": "switch",
    "select.py": "select",
    "number.py": "number",
    "time.py": "time",
    "binary_sensor.py": "binary_sensor",
    "button.py": "button",
    "device_tracker.py": "device_tracker",
}

err: list[str] = []
warn: list[str] = []


def load(p: pathlib.Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# --- 1. keys used by the code ----------------------------------------------
used: dict[str, set[str]] = {d: set() for d in PLATFORMS.values()}
dynamic: list[tuple[str, str]] = []
for fname, domain in PLATFORMS.items():
    src = (BASE / fname).read_text(encoding="utf-8")
    for m in re.finditer(r'_attr_translation_key = "([^"]+)"', src):
        used[domain].add(m.group(1))
    for m in re.finditer(r'_attr_translation_key = f"([^"]+)"', src):
        dynamic.append((domain, m.group(1)))

# expand f-strings
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
for domain, pattern in dynamic:
    if pattern == "websites_{kind}":
        used[domain].update({"websites_blocked", "websites_approved"})
    elif pattern.startswith("daily_limit_"):
        used[domain].update(f"daily_limit_{d}" for d in DAYS)
    elif pattern.startswith("bedtime_"):
        used[domain].update(f"bedtime_{d}_{b}" for d in DAYS for b in ("start", "end"))
    elif pattern.startswith("school_time_"):
        used[domain].update(
            f"school_time_{d}_{b}" for d in DAYS for b in ("start", "end")
        )
    else:
        err.append(f"unknown f-string pattern: {domain} {pattern}")

# --- 2. consistency with the translation files -----------------------------
files = {
    "strings.json": (BASE / "strings.json", 0),
    "en.json": (BASE / "translations" / "en.json", 0),
    "pl.json": (BASE / "translations" / "pl.json", 1),
}
data = {name: load(p) for name, (p, _) in files.items()}

KEY_RE = re.compile(r"\{(\w+)\}")
for name, (_, lang) in files.items():
    ent = data[name].get("entity") or {}
    for domain, keys in used.items():
        have = set((ent.get(domain) or {}))
        missing = keys - have
        if missing:
            err.append(f"{name}: missing {domain}: {sorted(missing)}")
        extra = have - keys
        if extra:
            warn.append(f"{name}: unused keys {domain}: {sorted(extra)}")

    # placeholders: EN vs PL, and agreement with the code
    for domain in used:
        for key, spec in (ent.get(domain) or {}).items():
            name_val = spec.get("name") or ""
            if lang == 1:
                en_val = ((data["en.json"].get("entity") or {}).get(domain) or {}).get(
                    key, {}
                ).get("name", "")
                if set(KEY_RE.findall(name_val)) != set(KEY_RE.findall(en_val)):
                    err.append(
                        f"pl.json {domain}.{key}: placeholders {KEY_RE.findall(name_val)}"
                        f" != en {KEY_RE.findall(en_val)}"
                    )
            if not name_val.strip():
                err.append(f"{name} {domain}.{key}: empty name")

# placeholders required by the code
code_ph = {
    ("sensor", "top_app"): {"rank"},
    ("button", "add_bonus"): {"minutes"},
}
for (domain, key), ph in code_ph.items():
    for name in files:
        val = ((data[name].get("entity") or {}).get(domain) or {}).get(key, {}).get(
            "name", ""
        )
        if set(KEY_RE.findall(val)) != ph:
            err.append(f"{name} {domain}.{key}: expected placeholders {ph}, got {val!r}")

# --- 3. untranslated entries (PL == EN) ------------------------------------
for domain, keys in used.items():
    for key in keys:
        en = ((data["en.json"].get("entity") or {}).get(domain) or {}).get(key, {}).get(
            "name", ""
        )
        pl = ((data["pl.json"].get("entity") or {}).get(domain) or {}).get(key, {}).get(
            "name", ""
        )
        if en and pl and en == pl and key != "add_bonus":
            warn.append(f"PL == EN: {domain}.{key} = {pl!r}")

# --- 4. services -----------------------------------------------------------
import yaml

yaml_svc = yaml.safe_load((BASE / "services.yaml").read_text(encoding="utf-8"))
for name in files:
    svc = data[name].get("services") or {}
    if set(svc) != set(yaml_svc):
        err.append(
            f"{name}: services {len(svc)} vs yaml {len(yaml_svc)}; "
            f"missing={sorted(set(yaml_svc) - set(svc))} extra={sorted(set(svc) - set(yaml_svc))}"
        )
        continue
    for sname, spec in yaml_svc.items():
        yfields = set(spec.get("fields") or {})
        tfields = set(svc[sname].get("fields") or {})
        if yfields != tfields:
            err.append(f"{name}: {sname} fields {sorted(yfields ^ tfields)}")
        if not (svc[sname].get("name") or "").strip():
            err.append(f"{name}: {sname} empty service name")
        if not (svc[sname].get("description") or "").strip():
            err.append(f"{name}: {sname} empty service description")
        for f in yfields:
            if not (svc[sname]["fields"][f].get("description") or "").strip():
                err.append(f"{name}: {sname}.{f} empty field description")

# placeholders in service descriptions (kept in sync between PL and EN)
pl_svc = data["pl.json"].get("services") or {}
en_svc = data["en.json"].get("services") or {}
for sname in set(pl_svc) & set(en_svc):
    a = set(re.findall(r"\{(\w+)\}", json.dumps(pl_svc[sname], ensure_ascii=False)))
    b = set(re.findall(r"\{(\w+)\}", json.dumps(en_svc[sname], ensure_ascii=False)))
    if a != b:
        warn.append(f"service {sname}: placeholders PL {a} vs EN {b}")

# PL services identical to EN (untranslated)
for sname, spec in pl_svc.items():
    en_spec = en_svc.get(sname, {})
    if spec.get("description") and spec.get("description") == en_spec.get("description"):
        warn.append(f"service PL == EN: {sname}")

# --- 5. languages: HA picks the file by language, a missing key falls back to EN ---
def leaf_keys(node: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in node.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out |= leaf_keys(v, path)
        else:
            out.add(path)
    return out


en_keys = leaf_keys(data["en.json"])
coverage: list[str] = []
for path in sorted((BASE / "translations").glob("*.json")):
    lang = path.stem
    if lang == "en":
        continue
    missing = sorted(en_keys - leaf_keys(load(path)))
    if not missing:
        coverage.append(f"{lang}: complete ({len(en_keys)})")
        continue
    coverage.append(f"{lang}: {len(en_keys) - len(missing)}/{len(en_keys)}, rest from EN")
    if lang == "pl":
        err.append(f"pl.json: {len(missing)} keys missing vs EN: {missing[:8]}")

languages = sorted(p.stem for p in (BASE / "translations").glob("*.json"))
print(f"entities: {sum(len(v) for v in used.values())} keys in code")
print(f"services: {len(yaml_svc)} (fields {sum(len(v.get('fields') or {}) for v in yaml_svc.values())})")
print(f"languages in translations/: {', '.join(languages)} — en.json is the base, a missing language or key falls back to EN")
for line in coverage:
    print(f"  coverage {line}")
for w in warn:
    print("WARN:", w)
if err:
    print(f"\nERRORS ({len(err)}):")
    for e in err:
        print(" -", e)
    sys.exit(1)
print("\nOK — no errors")
