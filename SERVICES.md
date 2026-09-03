# Service Reference

The integration registers 16 services under the `familylink` domain. They call unofficial, reverse engineered Google endpoints, so any service can stop working without notice if Google changes something.

For installation see [INSTALL.md](INSTALL.md). For the entity catalog see the [README](README.md).

## Targeting

Most services accept three optional targeting fields:

| Field | What it is | Where to find it |
|---|---|---|
| `entity_id` | Any Family Link entity. The integration reads the `device_id` and `child_id` **attributes** of that entity, not the entity itself | Per-child sensors (e.g. `sensor.<child>_daily_screen_time`) carry `child_id`; the device switch (`switch.<device>`) and every per-device sensor and binary sensor carry both `device_id` and `child_id` |
| `child_id` | The child's Google user ID | `child_id` attribute of any per-child sensor, or `user_id` on `sensor.<child>_child_info` |
| `device_id` | The device token | `device_id` attribute of the device switch (the simplest source) or of any per-device sensor or binary sensor |

Manual `child_id` / `device_id` values take precedence over IDs extracted from `entity_id`. An entity that lacks the `child_id` attribute is treated as no target at all.

What happens with **no target** differs per service, which matters in multi-child families:

| No target given | Services |
|---|---|
| Applies to **ALL** supervised children | [`block_device_for_school`](#familylinkblock_device_for_school), [`unblock_all_apps`](#familylinkunblock_all_apps), [`block_app`](#familylinkblock_app--familylinkunblock_app), [`unblock_app`](#familylinkblock_app--familylinkunblock_app), [`set_app_daily_limit`](#familylinkset_app_daily_limit), [`refresh_location`](#familylinkrefresh_location) |
| Applies to the **first** supervised child only | [`enable_bedtime`](#familylinkenable_bedtime--familylinkdisable_bedtime), [`disable_bedtime`](#familylinkenable_bedtime--familylinkdisable_bedtime), [`set_bedtime`](#familylinkset_bedtime), [`enable_school_time`](#familylinkenable_school_time--familylinkdisable_school_time), [`disable_school_time`](#familylinkenable_school_time--familylinkdisable_school_time), [`enable_daily_limit`](#familylinkenable_daily_limit--familylinkdisable_daily_limit), [`disable_daily_limit`](#familylinkenable_daily_limit--familylinkdisable_daily_limit) |
| Fails (a device target is mandatory) | [`add_time_bonus`](#familylinkadd_time_bonus), [`ring_device`](#familylinkring_device) |
| Fails without a device or a child | [`set_daily_limit`](#familylinkset_daily_limit) |

The device-scoped services (`add_time_bonus`, `ring_device`) raise an error unless a `device_id` is resolved, from the entity's attributes or the manual field. If they get a `device_id` but no `child_id`, the child resolves to the first supervised child. `set_daily_limit` also accepts a `child_id` alone, in which case it applies the limit to every device of that child.

After every successful call the integration refreshes its data immediately, except `ring_device`.

## App management

### familylink.block_device_for_school

Blocks all apps except a whitelist of essentials, simulating a device lock (school mode).

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `whitelist` | list of package names | no | - | Extra packages to keep allowed, merged with the built-in list below |
| `entity_id` | entity id | no | - | Entity carrying a `child_id` attribute |
| `child_id` | string | no | - | Child user ID. No target: ALL children |

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
| `child_id` | string | no | - | Child user ID. No target: ALL children |

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
| `child_id` | string | no | - | Child user ID. No target: ALL children |

```yaml
# Block YouTube for every supervised child
action: familylink.block_app
data:
  package_name: com.google.android.youtube

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
| `child_id` | string | no | - | Child user ID. No target: ALL children |

```yaml
action: familylink.set_app_daily_limit
data:
  package_name: com.zhiliaoapp.musically
  minutes: 45
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

Sets the daily screen time quota of one device, or of every device of a child when only `child_id` is given. A device or a child target is mandatory. By default the quota is today's; give `day` to set another weekday's quota, as the weekly limits screen of the app does (the `number.<child>_<weekday>_limit` entities do the same thing).

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `daily_minutes` | int, 0 to 1440 | yes | - (form prefills 120) | Minutes allowed per day. `0` disables the device for the day without fully locking it |
| `entity_id` | entity id | no | - | The device switch (`switch.<device>`) |
| `device_id` | string | no | - | Device token, if not using the entity |
| `child_id` | string | no | - | Child user ID. With a device target, defaults to the first supervised child. Given alone, targets every device of that child |
| `day` | int, 1 to 7 | no | today | Weekday the quota applies to (1 = Monday, 7 = Sunday) |

```yaml
action: familylink.set_daily_limit
data:
  entity_id: switch.pixel_7
  daily_minutes: 120
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
| `child_id` | string | no | - | Child user ID. No target: FIRST supervised child. There is no `entity_id` field |

```yaml
# Later bedtime every Friday, permanently
action: familylink.set_bedtime
data:
  start_time: "22:00"
  end_time: "09:00"
  day: 5
  scope: weekly
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

## Finding package names

| Source | Where the package name is |
|---|---|
| `sensor.<child>_daily_screen_time` | `apps` attribute: every app used today with its `package` |
| `sensor.<child>_top_app_1` to `_top_app_10` | `package_name` attribute |
| `sensor.<child>_blocked_apps`, `_apps_with_time_limits`, `_apps_without_limits`, `_always_allowed_apps` | `apps` attribute lists name and package |
| Google Play Store | The `id` parameter in the app's store URL, e.g. `play.google.com/store/apps/details?id=com.google.android.youtube` |

If a call fails, check the Home Assistant logs for `familylink` entries, and see [INSTALL.md](INSTALL.md) for authentication troubleshooting.
