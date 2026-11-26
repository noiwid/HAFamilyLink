#!/usr/bin/env python3
"""Replace hardcoded _attr_name values with translation_key in every familylink platform."""
from __future__ import annotations

import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "familylink"

# file -> {exact right-hand side of `self._attr_name = ` -> replacement lines (without indent)}
# {} inside translation_key names are f-strings, so the replacement is ready-made Python code.
REPL: dict[str, dict[str, list[str]]] = {
    "sensor.py": {
        'f"{device_name} Daily Screen Time"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "device_daily_screen_time"',
        ],
        'f"{device_name} Screen Time Remaining"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "device_screen_time_remaining"',
        ],
        'f"{device_name} Next Restriction"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "device_next_restriction"',
        ],
        'f"{child_name} Daily Screen Time"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "screen_time"',
        ],
        'f"{child_name} Screen Time Formatted"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "screen_time_formatted"',
        ],
        'f"{child_name} Installed Apps"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "installed_apps"',
        ],
        'f"{child_name} Blocked Apps"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "blocked_apps"',
        ],
        'f"{child_name} {kind.capitalize()} Sites"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = f"websites_{kind}"',
        ],
        'f"{child_name} Play Purchase Approvals"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "play_purchase_approvals"',
        ],
        'f"{child_name} Play Apps & Games Rating"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "play_apps_rating"',
        ],
        'f"{child_name} Apps with Time Limits"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "apps_with_limits"',
        ],
        'f"{child_name} Apps Without Limits"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "apps_without_limits"',
        ],
        'f"{child_name} Always Allowed Apps"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "always_allowed_apps"',
        ],
        'f"{child_name} Top App #{rank}"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "top_app"',
            'self._attr_translation_placeholders = {"rank": str(rank)}',
        ],
        'f"{child_name} Device Count"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "device_count"',
        ],
        'f"{child_name} Child Info"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "child_info"',
        ],
        'f"{device_name} Daily Limit"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "device_daily_limit"',
        ],
        'f"{device_name} Active Bonus"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "device_active_bonus"',
        ],
        'f"{device_name} Battery Level"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "device_battery_level"',
        ],
        'f"{child_name} Battery Level"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "child_battery_level"',
        ],
    },
    "switch.py": {
        'f"{child_name} Bedtime"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "bedtime"',
        ],
        'f"{child_name} School Time"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "school_time"',
        ],
        'f"{child_name} Daily Limit"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "daily_limit"',
        ],
        '"Unlimited apps during downtime"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "downtime_unlimited_apps"',
        ],
        '"Strict mode"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "strict_mode"',
        ],
    },
    "select.py": {
        'f"{child_name} Web Filter"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "web_filter"',
        ],
        'f"{child_name} Allowed Calls & Texts"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "allowed_calls_texts"',
        ],
        'f"{child_name} Play Purchase Approvals"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "play_purchase_approvals"',
        ],
        'f"{child_name} Play Apps & Games Rating"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "play_apps_rating"',
        ],
    },
    "number.py": {
        'f"{DAY_NAMES[day]} limit"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = f"daily_limit_{DAY_NAMES[day].lower()}"',
        ],
    },
    "time.py": {
        'f"{DAY_NAMES[day]} bedtime {label}"': [
            'self._attr_translation_key = f"bedtime_{DAY_NAMES[day].lower()}_{label}"',
        ],
        'f"{DAY_NAMES[day]} school time {label}"': [
            'self._attr_translation_key = f"school_time_{DAY_NAMES[day].lower()}_{label}"',
        ],
    },
    "binary_sensor.py": {
        'f"{device_name} Bedtime Active"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "bedtime_active"',
        ],
        'f"{device_name} School Time Active"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "school_time_active"',
        ],
        'f"{device_name} Daily Limit Reached"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "daily_limit_reached"',
        ],
    },
    "button.py": {
        'f"{device[\'name\']} +{bonus_minutes}min"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "add_bonus"',
            'self._attr_translation_placeholders = {"minutes": str(bonus_minutes)}',
        ],
        'f"{device[\'name\']} Reset Bonus"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "reset_bonus"',
        ],
        'f"{device[\'name\']} Ring"': [
            "self._attr_has_entity_name = True",
            'self._attr_translation_key = "ring"',
        ],
    },
}

ASSIGN = re.compile(r"^(?P<indent>[ \t]*)self\._attr_name = (?P<rhs>.+)$")


def patch_file(name: str, mapping: dict[str, list[str]]) -> tuple[int, list[str]]:
    path = BASE / name
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    done: set[str] = set()
    for line in lines:
        stripped = line.rstrip("\n")
        m = ASSIGN.match(stripped)
        if m and m.group("rhs") in mapping:
            rhs = m.group("rhs")
            indent = m.group("indent")
            for new in mapping[rhs]:
                out.append(f"{indent}{new}\n")
            done.add(rhs)
            continue
        out.append(line)
    missing = set(mapping) - done
    if missing:
        sys.exit(f"ERROR {name}: not found {sorted(missing)}")
    path.write_text("".join(out), encoding="utf-8")
    return len(done), sorted(done)


def main() -> None:
    total = 0
    for name, mapping in REPL.items():
        n, done = patch_file(name, mapping)
        total += n
        print(f"{name}: replaced {n}")
    print(f"total: {total}")
    # sanity: no _attr_name should remain outside switch/device_tracker
    for name in REPL:
        left = [
            l
            for l in (BASE / name).read_text(encoding="utf-8").splitlines()
            if "_attr_name =" in l
        ]
        if left:
            print(f"WARNING {name}: remaining _attr_name -> {left}")


if __name__ == "__main__":
    main()
