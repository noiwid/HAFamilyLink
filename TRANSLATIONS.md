# Translations

This fork adds complete UI translations to the upstream integration
([noiwid/HAFamilyLink](https://github.com/noiwid/HAFamilyLink), MIT, base version 2.9.3).

Entity names, service names/fields and select/state labels no longer come from hardcoded
English strings: entities use `has_entity_name = True` + `_attr_translation_key`, and every
label lives in `translations/<lang>.json`. The displayed language therefore follows the
Home Assistant language setting and falls back to English **per key**.

- `entity_id` of existing entities does **not** change — entities are bound by `unique_id`;
  only the displayed names change.
- Complete files (377 keys each): `en`, `pl`, `de`, `es`, `fr`, `nl`, `he`.
- Any other HA language → `en.json` in full. A partially filled language file → per-key
  fallback to English, so raw API values such as `all_content` are never shown.
- Translation files are cached inside the HA process, so a **restart** is required after
  changing them.

## What Home Assistant translates itself, and what needs files here

| layer | HA mechanism | needs translation files |
|---|---|---|
| entity name | `has_entity_name` + `translation_key` | **yes** → `entity.<platform>.<key>.name` |
| entity state (`select`, `sensor`) | `translation_key` + `state` | **yes** → `entity.<platform>.<key>.state.<value>` |
| service name / description / fields | `services` | **yes** → `services.<service>.name/description/fields.<field>` |
| `select` options | `state`, keyed by the raw API value | **yes** |

That is why entities carry `has_entity_name = True` + `_attr_translation_key`, and why the
repo ships `strings.json` + `translations/*.json`. Weekday suffixes are abbreviated per
language (English `Mon, Tue, …`; Polish `pn, wt, śr, czw, pt, sob, nie`).

## How Home Assistant picks the language

The language comes from the HA setting (`language`). Core loads `en.json` as the base and
overlays the active language **key by key** (`homeassistant/helpers/translation.py`:
`recursive_flatten`, then `merged.update(own)`), so a missing key yields English text
rather than a raw translation key.

## Adding or completing a language

```bash
python3 tools/gen_translations.py                # regenerates strings.json + translations/en.json + pl.json
python3 tools/validate.py                        # per-language key coverage; missing PL keys are an error
python3 tools/merge_lang.py <lang> flat.json     # merge a flat {key: text} map into translations/<lang>.json
```

`merge_lang.py` refuses to write when keys are missing, unexpected, or when `{placeholders}`
do not match the English source, so a broken translation cannot land in the repo.

Where the source texts live (data, not code):

- `tools/translation_source.json` — every entity/state text as `{"en": ..., "pl": ...}`,
  keyed by `translation_key`; this is what `gen_translations.py` reads.
- `tools/pl_services.json` — Polish service names/descriptions/fields; the English side
  comes straight from `services.yaml`, so the two cannot drift apart.

Adding a new language needs no Python change: drop in a complete `translations/<lang>.json`
(or a partial one — the rest falls back to English) and restart Home Assistant.
