# Service Reference

The integration registers 26 services under the `familylink` domain. They call unofficial, reverse engineered Google endpoints, so any service can stop working without notice if Google changes something.

For installation see [INSTALL.md](INSTALL.md). For the entity catalog see the [README](README.md).

## Targeting

Most services accept three optional targeting fields:

| Field | What it is | Where to find it |
|---|---|---|
| `entity_id` | Any Family Link entity. The integration reads the `device_id` and `child_id` **attributes** of that entity; when the entity has no `child_id` attribute (the child's bedtime, school time and daily limit switches, for example), the child is taken from the Family Link device the entity belongs to | Per-child sensors (e.g. `sensor.<child>_daily_screen_time`) carry `child_id`; the device switch (`switch.<device>`) and every per-device sensor and binary sensor carry both `device_id` and `child_id` |
| `child_id` | The child's Google user ID | `child_id` attribute of any per-child sensor, or `user_id` on `sensor.<child>_child_info` |
| `device_id` | The device token | `device_id` attribute of the device switch (the simplest source) or of any per-device sensor or binary sensor |

Manual `child_id` / `device_id` values take precedence over IDs extracted from `entity_id`. An entity that has no `child_id` attribute and belongs to no Family Link device is treated as no target at all (the app services `block_app`, `unblock_app`, `set_app_daily_limit`, `block_device_for_school` and `unblock_all_apps` raise an error instead).

What happens with **no target** differs per service, which matters in multi-child families:

| No target given | Services |
|---|---|
| Applies to **ALL** supervised children | [`refresh_location`](#familylinkrefresh_location) |
| Fails unless `all_children: true` is passed (then: every supervised child) | [`block_device_for_school`](#familylinkblock_device_for_school), [`unblock_all_apps`](#familylinkunblock_all_apps), [`block_app`](#familylinkblock_app--familylinkunblock_app), [`unblock_app`](#familylinkblock_app--familylinkunblock_app), [`set_app_daily_limit`](#familylinkset_app_daily_limit) |
| Applies to the **first** supervised child only | [`enable_bedtime`](#familylinkenable_bedtime--familylinkdisable_bedtime), [`disable_bedtime`](#familylinkenable_bedtime--familylinkdisable_bedtime), [`set_bedtime`](#familylinkset_bedtime), [`set_school_time`](#familylinkset_school_time), [`set_downtime_unlimited_apps`](#familylinkset_downtime_unlimited_apps), [`enable_school_time`](#familylinkenable_school_time--familylinkdisable_school_time), [`disable_school_time`](#familylinkenable_school_time--familylinkdisable_school_time), [`enable_daily_limit`](#familylinkenable_daily_limit--familylinkdisable_daily_limit), [`disable_daily_limit`](#familylinkenable_daily_limit--familylinkdisable_daily_limit) |
| Fails (a device target is mandatory) | [`add_time_bonus`](#familylinkadd_time_bonus), [`ring_device`](#familylinkring_device) |
| Fails without a device or a child | [`set_daily_limit`](#familylinkset_daily_limit) |
| Fails without a child | [`pause_app`](#familylinkpause_app--familylinkresume_app), [`resume_app`](#familylinkpause_app--familylinkresume_app) |

The device-scoped services (`add_time_bonus`, `ring_device`) raise an error unless a `device_id` is resolved, from the entity's attributes or the manual field. If they get a `device_id` but no `child_id`, the child resolves to the first supervised child. `set_daily_limit` also accepts a `child_id` alone, in which case it applies the limit to every device of that child.

After every successful call the integration refreshes its data immediately, except `ring_device`.

## Who may call a service

Home Assistant checks a user's entity permissions on entity actions (toggling a switch, pressing a button), not on domain services. Since these services accept raw identifiers, the integration applies the same rule itself:

| Caller | Result |
|---|---|
| An automation or a script run by the system (no user in the context) | Allowed, as before |
| An administrator | Allowed, any target |
| A non-administrator calling with an `entity_id` they are allowed to control, and nothing else | Allowed, as if they had toggled that entity |
| A non-administrator calling with a raw `child_id` or `device_id`, with no target, or mixing an `entity_id` with a raw identifier | Refused with an Unauthorized error and a warning in the log |

So a child with a non-admin Home Assistant account cannot grant themselves a bonus through the API, and an entity permission policy (for example one written with [ha-rbac](https://github.com/FezVrasta/ha-rbac)) applies to the services too. A dashboard used by a non-administrator should call services with the `entity_id` of the device or child, never with raw identifiers.

## App management

### familylink.block_device_for_school

Blocks all apps except a whitelist of essentials, simulating a device lock (school mode).

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `whitelist` | list of package names | no | - | Extra packages to keep allowed, merged with the built-in list below |
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID |
| `all_children` | boolean | no | `false` | Apply to every supervised child. Required when no child is given |

Built-in whitelist (always allowed): `com.android.dialer`, `com.android.contacts`, `com.android.mms`, `com.google.android.apps.messaging`, `com.android.settings`, `com.android.deskclock`, `com.google.android.apps.maps`, `com.android.emergency`, `com.android.systemui`, `com.android.launcher3`, `com.google.android.gms`.

Whitelisted apps that were already blocked get unblocked. Per-app calls are spaced 0.1 s apart to avoid rate limiting.

```yaml
action: familylink.block_device_for_school
data:
  entity_id: sensor.emma_daily_screen_time
  whitelist:
    - com.microsoft.teams
```

### familylink.unblock_all_apps

Unblocks every blocked app, ending school mode. Per-app calls are spaced 0.1 s apart.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID |
| `all_children` | boolean | no | `false` | Apply to every supervised child. Required when no child is given |

```yaml
action: familylink.unblock_all_apps
data:
  entity_id: sensor.emma_daily_screen_time
```

### familylink.block_app / familylink.unblock_app

Blocks or unblocks a single app by package name.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `package_name` | string | yes | - | Android package name, e.g. `com.google.android.youtube` |
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID |
| `all_children` | boolean | no | `false` | Apply to every supervised child. Required when no child is given |

```yaml
# Block YouTube for every supervised child
action: familylink.block_app
data:
  package_name: com.google.android.youtube
  all_children: true

# Unblock it for one child only
action: familylink.unblock_app
data:
  package_name: com.google.android.youtube
  entity_id: sensor.emma_daily_screen_time
```

### familylink.set_app_daily_limit

Sets the per-app time policy. Family Link has four app states, selected by the `minutes` value:

| `minutes` | State |
|---|---|
| `-2` | Unlimited time: the app ignores device limits |
| `-1` | App limit off: the app follows device limits |
| `0` | Blocked |
| `1` to `1440` | Daily limit in minutes |

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `package_name` | string | yes | - | Android package name |
| `minutes` | int, -2 to 1440 | yes | - (form prefills 60) | See the state table above |
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID |
| `all_children` | boolean | no | `false` | Apply to every supervised child. Required when no child is given |

```yaml
action: familylink.set_app_daily_limit
data:
  package_name: com.zhiliaoapp.musically
  minutes: 45
  entity_id: sensor.emma_daily_screen_time
```

### familylink.pause_app / familylink.resume_app

`pause_app` pauses apps for one child by setting their daily limit to 1 minute; `resume_app` puts back the setting each app had before (a daily limit, unlimited time, or no limit). Unlike `block_app`, a paused app stays installed and shows as paused. That matters for the default SMS app: a blocked Google Messages loses texts that arrive while blocked, a paused one keeps them.

- An app already used for a minute or more today pauses within seconds. An app not used yet today gets its 1 minute, then pauses.
- App limits count per device, so the pause applies on every device of the child. Google TV ignores app limits; use `block_app` there.
- The setting from before the first pause is stored, survives restarts, and is not replaced by a second pause. A limit changed in the Family Link app while the app is paused is overwritten on resume.
- Blocked apps are skipped: `pause_app` leaves them as they are, and `resume_app` leaves an app blocked since the pause blocked (writing its limit back could unblock it) and keeps its saved setting for a later `resume_app`. Calls run one at a time, so a pause and a resume overlapping cannot leave an app paused with nothing saved.
- Both services require a child and return what they did (`paused`/`skipped`, `resumed`/`not_paused`/`skipped`).

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `packages` | list of strings | yes for `pause_app` | - | Android package names. `resume_app` without it resumes every paused app of the child |
| `entity_id` | entity id | one of these | - | Entity carrying a `child_id` attribute |
| `child_id` | string | one of these | - | Child user ID |

```yaml
# Pause Messages during school hours, then put it back
action: familylink.pause_app
data:
  packages: com.google.android.apps.messaging
  entity_id: sensor.emma_daily_screen_time
---
action: familylink.resume_app
data:
  entity_id: sensor.emma_daily_screen_time
```

## Time limits and bonuses

### familylink.add_time_bonus

Adds bonus screen time to one device. A device target is mandatory. The per-device buttons `button.<device>_15min`, `_30min`, `_60min` and `_reset_bonus` cover the common cases without a service call.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `bonus_minutes` | int, 1 to 1440 | yes | - (form prefills 30) | Minutes to add |
| `entity_id` | entity id | no | - | The device switch (`switch.<device>`), which carries `device_id` and `child_id` |
| `device_id` | string | no | - | Device token, if not using the entity |
| `child_id` | string | no | - | Child user ID; defaults to the first supervised child |

```yaml
action: familylink.add_time_bonus
data:
  entity_id: switch.pixel_7
  bonus_minutes: 30
```

### familylink.set_daily_limit

Sets the daily screen time quota of one device, or of every device of a child when only `child_id` is given. A device or a child target is mandatory. Without `day`, the quota set is today's override on the device(s). With `day`, the weekly quota of that weekday is written, as the weekly limits screen of the app does (captured 2026-09-03); when `day` is today, today's override is posted as well so the change applies at once. An override alone is only honoured by Google for the current day, which is why another weekday always goes through the weekly quota.

The override references today's slot of the weekly daily-limit schedule. That slot id is resolved from the account's live schedule (it is not the same on every account), and the new value is read back from Google after 3 and 8 seconds. The action therefore takes up to about 10 seconds and raises an error when Google accepted the request without applying it, so an automation can react instead of assuming success.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `daily_minutes` | int, 0 to 1440 | yes | - (form prefills 120) | Minutes allowed per day. `0` disables the device for the day without fully locking it |
| `entity_id` | entity id | no | - | The device switch (`switch.<device>`) |
| `device_id` | string | no | - | Device token, if not using the entity |
| `child_id` | string | no | - | Child user ID. With a device target, defaults to the first supervised child. Given alone, targets every device of that child that takes time limits (a Google TV is skipped) |
| `day` | int, 1 to 7 | no | - | Weekday (1 = Monday, 7 = Sunday) whose weekly quota is written, see above. Without it, today's override only |

```yaml
# Today's quota on one device
action: familylink.set_daily_limit
data:
  entity_id: switch.pixel_7
  daily_minutes: 120
```

```yaml
# Saturday's quota, permanently, on every device of the child
action: familylink.set_daily_limit
data:
  child_id: "123456789012345678901"
  daily_minutes: 240
  day: 6
```

### familylink.enable_daily_limit / familylink.disable_daily_limit

Turns the child's daily screen time limit on or off.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID. No target: FIRST supervised child |

```yaml
action: familylink.enable_daily_limit
data:
  entity_id: sensor.emma_daily_screen_time
```

## Bedtime and school time schedules

### familylink.set_bedtime

Sets bedtime start and end times. By default this edits the recurring **weekly** schedule for the chosen day, like Family Link's own weekly schedule editor. Use `scope: today` for a one-off "tonight only" override that leaves the weekly schedule untouched.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `start_time` | string, `H:MM` or `HH:MM` (24 h) | yes | - | Bedtime start, e.g. `20:45` |
| `end_time` | string, `H:MM` or `HH:MM` (24 h) | yes | - | Bedtime end, usually next morning, e.g. `07:30` |
| `day` | int, 1 to 7 (1 = Monday) | no | today | Day of the week to change |
| `scope` | `weekly` or `today` | no | `weekly` | `weekly` edits the recurring schedule; `today` posts a one-off override |
| `entity_id` | entity id | no | - | Any entity of the child |
| `child_id` | string | no | - | Child user ID. No target: FIRST supervised child |

```yaml
# Later bedtime every Friday, permanently
action: familylink.set_bedtime
data:
  entity_id: switch.emma_bedtime
  start_time: "22:00"
  end_time: "09:00"
  day: 5
  scope: weekly
```

### familylink.set_school_time

Sets the school time start and finish for a day. By default this edits the recurring **weekly** school time slot of that day, the same way `set_bedtime` edits bedtime. Use `scope: today` for a one-off window today only, which leaves the weekly schedule untouched and replaces any school time override already posted for today.

The weekly scope only changes an existing slot: the day must already have a school time window in Family Link (create it once in the app; a day switched off in the app keeps its window and can still be edited, but stays off until it is switched on in the app). School time is a same-day window, so the end must be after the start.

A school day with a break is stored by Google as two windows on the same day. `start_time` and `end_time` then move the first window's start and the second window's end, and the break stays. To set both windows, pass `windows` instead: the day's windows in order (the `windows` attribute of the `time.<child>_<weekday>_school_time_start|end` entities shows the current ones). Two windows on a day that has one add the break, one window on a day that has two removes it. Family Link allows one break per day, so a third window is refused.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `start_time` | string, `H:MM`, `HH:MM` or `HH:MM:SS` (24 h) | with `end_time` | - | School time start, e.g. `08:00`. Not with `windows` |
| `end_time` | string, `H:MM`, `HH:MM` or `HH:MM:SS` (24 h) | with `start_time` | - | School time end, same day, e.g. `13:15`. Not with `windows` |
| `windows` | list of one or two `HH:MM-HH:MM` | instead of start and end | - | The day's windows in order, e.g. `["08:00-12:00", "13:30-15:00"]`; two windows on a one-window day add the break, one window on a two-window day removes it. Weekly scope only |
| `day` | int, 1 to 7 (1 = Monday) | no | today | Day of the week to change. With `scope: today` it must be today |
| `scope` | `weekly` or `today` | no | `weekly` | `weekly` edits the recurring schedule; `today` posts a one-off window for today |
| `entity_id` | entity id | no | - | Any entity of the child |
| `child_id` | string | no | - | Child user ID. No target: FIRST supervised child |

The call raises an error when Google rejects the window or the day has no school time slot, so an automation can tell.

```yaml
# Follow today's timetable (e.g. from the WebUntis integration)
action: familylink.set_school_time
data:
  entity_id: switch.emma_school_time
  start_time: "{{ as_timestamp(states('sensor.emma_today_s_school_start')) | timestamp_custom('%H:%M') }}"
  end_time: "{{ as_timestamp(states('sensor.emma_today_s_school_end')) | timestamp_custom('%H:%M') }}"
  day: "{{ now().isoweekday() }}"

# A school day with a lunch break: both windows of Tuesday (adds the break if
# Tuesday had one window, moves it if it had two)
action: familylink.set_school_time
data:
  entity_id: switch.emma_school_time
  day: 2
  windows:
    - "08:00-12:00"
    - "13:30-15:00"

# Back to one window on Tuesday (removes the break)
action: familylink.set_school_time
data:
  entity_id: switch.emma_school_time
  day: 2
  windows:
    - "08:00-15:00"
```

### familylink.enable_bedtime / familylink.disable_bedtime

Turns bedtime restrictions on or off. This flips the weekly toggle **and** posts a same-day override, so the change applies tonight, mirroring what the Family Link app does.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID. No target: FIRST supervised child |

```yaml
action: familylink.disable_bedtime
data:
  entity_id: sensor.emma_daily_screen_time
```

### familylink.enable_school_time / familylink.disable_school_time

Turns school time restrictions on or off.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID. No target: FIRST supervised child |

```yaml
action: familylink.enable_school_time
data:
  entity_id: sensor.emma_daily_screen_time
```

### familylink.set_downtime_unlimited_apps

Allows or blocks the apps with unlimited time during downtime, the *Allow apps with unlimited time during downtime* setting of Family Link. With `allow: false`, the apps set to unlimited time are blocked during downtime too. The setting belongs to the child, so it applies to all of the child's devices. `switch.<child>_unlimited_apps_during_downtime` shows and changes the same setting.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `allow` | boolean | yes | - | `true` keeps the apps with unlimited time usable during downtime, `false` blocks them |
| `entity_id` | entity id | no | - | Any entity of the child |
| `child_id` | string | no | - | Child user ID. No target: FIRST supervised child |

The call raises an error when Google rejects the change, so an automation can tell.

```yaml
# Block the apps with unlimited time during downtime too
action: familylink.set_downtime_unlimited_apps
data:
  entity_id: switch.emma_unlimited_apps_during_downtime
  allow: false
```

## Location and device actions

### familylink.refresh_location

Requests a fresh GPS fix from the child's device instead of the cached position Google normally serves. Uses more battery on the child's device than the regular polling.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID. No target: ALL children |

```yaml
action: familylink.refresh_location
data:
  entity_id: sensor.emma_daily_screen_time
```

### familylink.ring_device

Makes the device ring to help locate it. A device target is mandatory. This is the only service that does not trigger a data refresh. The per-device button `button.<device>_ring` does the same thing.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `entity_id` | entity id | no | - | An entity carrying a `device_id` attribute: use the device switch (`switch.<device>`), or pass `device_id` manually |
| `device_id` | string | no | - | Device token, if not using the entity |
| `child_id` | string | no | - | Child user ID; defaults to the first supervised child |

```yaml
action: familylink.ring_device
data:
  entity_id: switch.pixel_7
```

## Polling

### familylink.set_update_interval

Changes how often the integration polls Google. The new interval applies immediately and lasts until the next reload or restart, after which the value set in the integration options applies again. It is not saved to the options on purpose, so an automation can lengthen the interval at bedtime and shorten it in the morning without changing the configured value.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `seconds` | integer | yes | - | Polling interval in seconds, 30 to 3600 |

```yaml
# Poll every 10 minutes at night
action: familylink.set_update_interval
data:
  seconds: 600
```

## Finding package names

| Source | Where the package name is |
|---|---|
| `sensor.<child>_daily_screen_time` | `apps` attribute: every app used today with its `package` |
| `sensor.<child>_top_app_1` to `_top_app_10` | `package_name` attribute |
| `sensor.<child>_blocked_apps`, `_apps_with_time_limits`, `_apps_without_limits`, `_always_allowed_apps` | `apps` attribute lists name and package |
| Google Play Store | The `id` parameter in the app's store URL, e.g. `play.google.com/store/apps/details?id=com.google.android.youtube` |

If a call fails, check the Home Assistant logs for `familylink` entries, and see [INSTALL.md](INSTALL.md) for authentication troubleshooting.

## Websites (Chrome site lists)

Family Link's "Google Chrome and Web" lists apply to the **child's Google account**, so to every Chrome the child is signed in to (phone, tablet, Chromebook, desktop). Other browsers are not filtered (block them with `block_app`), and a Google TV has no Chrome.

Patterns: a website `www.example.com`, a domain wildcard `*.example.com` or `*.example.*` (only a leading `*.` or trailing `.*`), or a web address `https://example.com/page` (matched exactly). Google stores patterns as given and does not validate them, so the integration does. A pattern is either approved or blocked; adding it as the other type replaces it. A block wins over an approval.

| Service | Fields | Notes |
|---|---|---|
| `familylink.get_sites` | `entity_id` or `child_id` | Response only: `filter_level`, `approved`, `blocked` (every entry, including ones added in the app) |
| `familylink.block_site` / `familylink.allow_site` | `entity_id` or `child_id`, `sites` (list) | Optional response: `covered`, inserts Google skipped because an existing entry already covers them |
| `familylink.remove_site` | `entity_id` or `child_id`, `sites` (list) | Removes from either list, whoever added the entry. Response: `removed`, `not_listed` |
| `familylink.sync_site_list` | `entity_id` or `child_id`, `url`, `max_domains` (default 2000), `stop` | Downloads a domain list (one per line, `#` comments, hosts-file lines tolerated), blocks `*.domain` and `domain` for each, and removes only what the same URL added before and has since dropped. Domains you approved are skipped. `stop: true` removes everything that list added and forgets it. The list is a third party's, so: **administrators only**, the `url` must be `https` and redirects are not followed (give the final address), the download is read up to 1 MiB, and only plain domains are taken (wildcards, web addresses, IP addresses and bare suffixes such as `co.uk` are ignored and counted). A list with no usable domain, or one that would remove more than half of what it added (20 entries at least), is refused and nothing changes; if the list really shrank that much, run `stop: true` and sync again. Changes go out in calls of at most 2,500 entries. Response: `added_count`, `removed_count` and up to 20 of each, `skipped_approved`, `ignored_count` and up to 20 `ignored` |

Sensors per child: `sensor.<child>_blocked_sites` and `sensor.<child>_approved_sites` (count; `sites` and `filter_level` attributes), read every 15 minutes and right after a change made from Home Assistant.

```yaml
# Block a site during homework, from a script
action: familylink.block_site
data:
  entity_id: sensor.alex_daily_screen_time
  sites: ["*.roblox.com", "www.example.com"]

# Keep the blocked list in step with a published list, daily
action: familylink.sync_site_list
data:
  entity_id: sensor.alex_daily_screen_time
  url: https://example.org/blocklist.txt
```

