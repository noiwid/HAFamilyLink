# Changelog

All notable changes to the Google Family Link Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## Add-on / auth container [1.8.0] - 2026-07-24

### Fixed
- **noVNC no longer hangs on "Connecting…" forever (issue #136).** The auth container's display stack (Xvfb + fluxbox + x11vnc + websockify) was started with all output redirected to `/dev/null` and no real liveness check, so any failure was completely silent: the container stayed "healthy" on uvicorn/8099 while noVNC never rendered. Two concrete failure modes are addressed, plus the underlying crash:
  - **Silent failures are now visible.** In the standalone container each display process logs to `/var/log/familylink/<proc>.log` instead of `/dev/null`, and its status is re-checked after launch with the last log lines dumped on failure. The add-on entrypoint (already logging to journald) gains the same Xvfb/fluxbox/x11vnc liveness checks.
  - **Stale X99 state is cleaned on start.** A non-graceful stop (e.g. `docker restart`) left `/tmp/.X11-unix/X99` and `/tmp/.X99-lock` behind, which made `Xvfb :99` silently refuse to bind on the next start and took the whole display stack down invisibly — only uvicorn came back, so the container reported healthy while VNC was dead. Both are now removed before the display server starts (and again before the x11vnc fallback).
  - **VNC password length.** x11vnc's `-passwd` (and TigerVNC's VncAuth) uses DES and silently keeps only the first 8 characters, so the 10-char default (`familylink`) never authenticated cleanly. The password is now truncated explicitly with a warning, and the web UI's auto-connect URL embeds the same 8-char value so client and server agree. The server stays localhost-only behind websockify.

### Changed
- **TigerVNC is now the default display backend, with automatic fallback to Xvfb + x11vnc (issue #136).** The primary crash (`x11vnc` 0.9.16 tearing down its own X connection the instant a VNC client connects, confirmed by @wookash via `strace`) is most likely an incompatibility between the 2019 x11vnc build and the bookworm X11 libraries. Rather than chase a compatible x11vnc, the container now prefers **TigerVNC's `Xvnc`** — an X server that speaks the RFB/VNC protocol natively, so there is no separate Xvfb and no x11vnc screen-scraper, removing the exact component that crashed. If `Xvnc` is unavailable or fails to start, the container automatically falls back to the legacy Xvfb + x11vnc stack, so no environment loses VNC. The backend can be forced with `FAMILYLINK_VNC_BACKEND=tigervnc|x11vnc`.

---

## [1.2.12] - 2026-07-16

### Fixed
- **`set_bedtime` with `scope: weekly` no longer fails with HTTP 400 on some accounts** — The weekly write sent a hardcoded slot id from `_DAY_CODES` (`CAEQAQ`…`CAEQBw`). Those ids are account-specific, so on accounts whose bedtime slots use different ids Google rejected every weekly call with `HTTP 400 [3,"Request contains an invalid argument."]` — 7 failures per full-week sync. The client now resolves the slot id from the live schedule (`people/{id}/timeLimit`) before building the payload, falling back to the static codes only when the lookup fails. Reported, diagnosed and patch-validated by @bedar89 (#135).

  A live capture corrected one detail of the original diagnosis: `CAEQ*` and `CAM*` are not two account-specific families where an account has one or the other — they **coexist in the same account, in the same list**. Decoding the protobuf, field 1 is the rule type: **1 = bedtime** (`CAEQ*`), **3 = school time** (`CAMQ*`, with an embedded UUID). A third block reuses the bedtime ids but carries minutes instead of a window — that one is the daily limit. So resolving "the first `CA*` id matching the day" is order-dependent and can put a school-time id in a bedtime payload, turning a loud 400 into a silent wrong-schedule write. A row is now accepted only when the id decodes to rule type 1 **and** the row carries an `[h, m]`–`[h, m]` window, which is immune to row ordering and to the response nesting shifting between API versions. The fetched schedule is cached per account for 60s, since writing a full week is one call per day.

### Changed
- **Schedule parsing extracted into `schedules.py`** — The positional-array parsing that breaks when Google shifts an index was the least testable code in `client/api.py` (reaching it required an authenticated client and a live account). Adapted from the split-out module in [@benkap's fork](https://github.com/benkap/HAFamilyLink). The extracted parsers are stricter than the hand-rolled loop they replace: they reject booleans where an integer day is expected (`isinstance(True, int)` is `True` in Python, so a stray bool passed as Monday), validate the window shape and hour/minute ranges, sort rows by day instead of trusting response order, and surface `enabled` / `state_flag` / `day_name` which the old loop silently dropped. Verified to return byte-identical `day`/`start`/`end` slots to the old parser on a live response, so existing entities are unaffected.

---

## [1.2.11] - 2026-07-09

### Fixed
- **GPS location tracking restored after a Google API change** — Google's `kidsmanagement` location endpoint stopped accepting the string values `"REFRESH"` / `"DO_NOT_REFRESH"` for `locationRefreshMode` and now returns `HTTP 400: Invalid value at 'location_refresh_mode' … "REFRESH"`. Because `async_get_location` returns `None` on any non-200 response, an active location refresh silently froze on the last known position with no error surfaced to the user. The client now sends the numeric enum values (`2` = REFRESH, `1` = DO_NOT_REFRESH). Verified against the live API: the string `"REFRESH"` returns HTTP 400 while `"1"`/`"2"` return HTTP 200 with a fresh fix. Thanks to @miditt (#132).
- **Removed `aiohttp` and `cryptography` from manifest requirements** — Both are already bundled with Home Assistant. Declaring them caused HA to reinstall `cryptography`/`cffi` over the core versions, producing a `cffi` / `_cffi_backend` version mismatch (`this is the 'cffi' package version 2.1.0 … we get version 2.0.0`) that broke several core components on HA 2026.7.1 (Python 3.14). Per the HA docs, custom integrations must not list requirements already included with HA. Thanks to @omad (#131).

### Added
- **Example dashboard** — Added an `examples/` folder with a ready-to-copy, Family-Link-only Lovelace dashboard (anonymised entity IDs, `sections` layout), a screenshot, and setup notes (required HACS cards + theme). Referenced from the README.

---

## [1.2.10] - 2026-07-02

### Fixed
- **`set_bedtime` now updates the recurring weekly schedule (not just a one-off override)** — The service previously posted only a per-day type-9 override (`timeLimitOverrides:batchCreate`), i.e. Family Link's "tonight only" exception. It reported success but the recurring **weekly** schedule shown in Family Link ("Weekly schedule") was never touched, so the change silently didn't stick. `set_bedtime` now defaults to editing the weekly recurring schedule for the target day via `timeLimit:update` (only the modified day is sent; Google merges it, leaving other days untouched — verified on-device). A new `scope` option preserves the old behavior: `scope: weekly` (default) edits the weekly schedule, `scope: today` posts the one-off "today only" override without changing the weekly schedule (#129).
- **Removed deprecated `TrackerEntity` import** — `device_tracker.py` imported `TrackerEntity` from `homeassistant.components.device_tracker.config_entry`, a deprecated alias scheduled for removal in HA Core 2027.6. Now imported from `homeassistant.components.device_tracker` (#130).

---

## [1.2.7-rc5] - 2026-06-09

### Added
- **Cache last known data on transient API errors (503/500/timeouts)** — Google's Family Link API (especially `appsandusage`) regularly returns transient 5xx errors, which previously dropped every sensor to `unavailable` even though the underlying data was unchanged. The coordinator now keeps the last successful fetch in memory and returns it on transient errors, with per-child fallbacks for each endpoint (apps/usage, time limit config, applied limits, screen time). `SessionExpiredError` still propagates so re-authentication is unaffected; the cache is cleared on restart. Thanks to @Naumsede for the contribution (#117).

---

## [1.2.7-rc4] - 2026-06-09

### Fixed
- **Bedtime/school time schedules are now actually parsed (0 schedules → real windows)** — The rc3 index fix (`item[3]`/`item[4]`) was correct but lived inside a loop that never ran: the parser expected `data[0][0]` to be a *list* of schedule rows, but the real Family Link `timeLimit` response has `data[0] = [stateFlag, [<flat list of schedule items>], ts, ts, 1]` — `data[0][0]` is the integer stateFlag, so the `isinstance(data[0][0], list)` guard was always False and both schedule lists came back empty. Confirmed against the live (un-anonymized) API response: every fetch logged `0 schedules` and the bedtime override always fell back to the hardcoded `21:30→07:00` default. Now reads the flat schedule list at `data[0][1]` and splits it by code prefix (`CAEQ*` = bedtime, `CAMQ*` = school time). Today's real bedtime window is now used for the override (#113).
- **School time schedule windows recovered** — The old school-time branch read `data[1][0][2]`, which holds daily-limit *minutes* (`[code, day, stateFlag, minutes, …]`), not `CAMQ` time windows — so it never matched. School time windows live in the same flat list as bedtime (`data[0][1]`) and are now parsed from there.

---

## [1.2.7-rc3] - 2026-05-26

### Fixed
- **Bedtime override now uses today's actual schedule instead of hardcoded 21:30–07:00** — The CAEQ (bedtime) and CAMQ (school time) schedule parsers read start/end from the wrong array indices, skipping the `stateFlag` at index 2. Start was read as the stateFlag integer (always failing the `isinstance(list)` check) and end was read as the actual start time. Both fell through to the hardcoded defaults `[21, 30]→[7, 0]`. Fixed to read `item[3]` (start) and `item[4]` (end), matching the documented protobuf layout (#113)

---

## [1.2.7-rc2] - 2026-05-21

### Fixed
- **Bedtime switch now actually reaches the child device** — Same fix pattern as v1.2.7 for school time, applied to bedtime (#113). `switch.<child>_bedtime` and `familylink.enable_bedtime` / `familylink.disable_bedtime` now do both calls the Family Link web app sends when the user confirms "Apply changes to today as well?": (1) flip the weekly policy via `timeLimit:update`, (2) post a per-day override via `timeLimitOverrides:batchCreate` (action=2 to enable, action=1 to disable) using today's weekly bedtime hours and the matching `CAEQxx` day_code. The previous behavior only did step 1, which left tonight's slot unchanged on the device.
- **Bedtime and school time switches now reflect the effective today state** — `is_on` for both switches now reads `bedtime_enabled_today` / `school_time_enabled_today` from `appliedTimeLimits`, which combines the weekly policy with daily overrides. Previously the switches only read the weekly revisions, so after a "today only" override the switch would snap back to its weekly value on the next coordinator refresh (~30-60s) and the user would think the toggle did nothing (#114).

### Documentation
- `GOOGLE_FAMILY_LINK_API_ANALYSIS.md` — added a "Bedtime daily override pattern" section, updated the endpoints table to flag the bedtime weekly-only toggle as misleading (same trap as school time), and added an "Apply bedtime today" entry documenting the reverse-engineered payload (uses `CAEQxx` day_code instead of school time's `[weekday, rule_uuid]` tuple).

---

## [1.2.7] - 2026-05-16

### Fixed
- **School time switch now actually locks/unlocks the child device** — Previously, `switch.<child>_school_time` and the `familylink.enable_school_time` / `familylink.disable_school_time` services only flipped the weekly policy via `timeLimit:update`. If the current weekday had no slot in the weekly schedule (e.g. weekends with a Mon-Fri schedule), nothing happened on the device. The integration now mirrors what the official Family Link web app does when toggling the "Today" switch: it posts a daily override via `timeLimitOverrides:batchCreate` (action=2 to enable, action=1 to disable) covering "now → 23:59" for today's weekday. Turning the switch off also cleans up any existing schooltime override for today to avoid stacking conflicting entries (#111)

### Documentation
- `GOOGLE_FAMILY_LINK_API_ANALYSIS.md` — added a dedicated "School time daily override pattern" section documenting the reverse-engineered `timeLimitOverrides:batchCreate` payload shape (`type=9` + `[weekday, rule_uuid]` reference) and the DELETE → CREATE sequence the web app uses

---

## [1.2.6-rc2] - 2026-05-12

### Fixed
- **Config flow now exposes "Manual URL configuration" explicitly** — Previously the manual URL form was only reachable when local auto-detection failed, which made it impossible for Docker standalone users to point the integration at a remote auth container if `/share/familylink/` happened to contain stale data from a previous add-on install (#109)
- **Standalone container no longer shows a black noVNC screen** — A welcome banner is now displayed on the Xvfb display via `xterm` so users connecting to noVNC before triggering the auth flow get clear instructions instead of an empty desktop (#108)

### Changed
- `DOCKER_STANDALONE.md` rewritten to document the actual flow (open port 8099 first, then noVNC on port 6080) and the new menu option

---

## [1.2.2] - 2025-03-16

### Fixed
- **Revert `locationRefreshMode` to string values** — v1.2.1 incorrectly changed `locationRefreshMode` from string (`"REFRESH"` / `"DO_NOT_REFRESH"`) to numeric (`1` / `0`), which broke location tracking and battery level for all users. Reverted to the original string values expected by the Google Kids Management API (#89)

---

## [1.2.1] - 2025-03-15

### Fixed
- **`refresh_location` service returning HTTP 400** — *(Reverted in v1.2.2)* Changed `locationRefreshMode` to numeric values, which turned out to be incorrect (#84)

---

## [1.2.0] - 2025-03

### Added
- **noVNC web-based browser access** — No external VNC client needed anymore! The authentication browser is now accessible directly from your web browser at `http://[HOST]:6080/vnc.html` (replaces raw VNC on port 5900)
- **Auto-detection of language and timezone** — The add-on now automatically reads your Home Assistant language and timezone settings via the Supervisor API. Manual override is still available in add-on configuration
- **Bilingual web UI (FR/EN)** — The add-on authentication interface now supports French and English, switching automatically based on your HA language setting
- **DNS configuration for Pi-hole compatibility** — Docker standalone setup now includes Google DNS (8.8.8.8) to avoid DNS resolution issues behind Pi-hole

### Changed
- VNC server (x11vnc) now restricted to localhost only — external access is exclusively via noVNC (port 6080)
- Add-on version bumped to 1.6.0
- Default language/timezone options are now empty (auto-detected from HA)

### Credits
- noVNC integration inspired by [@jnctech's fork](https://github.com/jnctech/HAFamilyLink)

---

## [1.1.1] - 2025-03

### Added
- **`refresh_location` service** — Force-refresh GPS location for a child (#78)
- **Unlimited time mode for apps** — Set `minutes: -1` in `set_app_daily_limit` to grant unlimited access (#79)

### Changed
- Updated documentation for new services

---

## [1.1.0] - 2025-02

### Fixed
- **Session locking and resource management** — Improved robustness with concurrent sessions
- **Entity creation and data display** — Fixed logic bugs in entity setup and validation
- **Null client crash prevention** — Prevent crashes from invalid data and missing keys
- **Security hardening** — Redact credentials from logs, fix auth flow and timezone handling
- **Browser compatibility** — Improved support for RPi4/ARM64 and VMs (#68, #76)
- **SAPISIDHASH staleness** — Fixed stale auth hash, button unique_id, dead code cleanup
- **Resource leaks** — Prevent leaks in browser sessions and cookie cache
- **Silent HTTP failures** — Prevent wrong data from undetected HTTP errors

### Changed
- Configurable language and timezone for auth browser (#75)
- Removed unused exception classes and service constants

---

## [1.0.0] - 2025-01 🎉

### Added
- **Per-app daily time limits** - New `set_app_daily_limit` service (#59)
  - Set daily time limits for specific apps (e.g., 60 minutes for TikTok)
  - Use `minutes: 0` to remove the limit and restore unlimited access
  - Supports targeting specific children via `entity_id` or `child_id`
  - When no child specified, applies to ALL supervised children

- **Multi-child support for app control services** (#57)
  - `block_app` and `unblock_app` now apply to ALL children when no `child_id` specified
  - Added optional `entity_id` parameter for easier child selection via UI
  - Added optional `child_id` parameter for direct targeting

- **New API method**: `async_get_all_supervised_children()` to retrieve all supervised children
- **New API method**: `async_set_app_daily_limit()` for per-app time limit control

### Changed
- App control services (`block_app`, `unblock_app`) now default to applying to all children instead of just the first one
- Improved service descriptions to clarify multi-child behavior

---

## [0.9.8] - 2025-01

### Added
- **Battery Level Sensor** - New `sensor.<child>_battery_level` entity (#54)
  - Displays battery percentage of the device providing location data
  - Dynamic icon based on battery level (full → alert)
  - Attributes: `source_device`, `last_update`
  - Also available as `battery_level` attribute on device tracker entity

### Important Limitations
- **Requires location tracking**: Battery data comes from the location API endpoint
- **One device per child**: Battery level corresponds to the device selected for location tracking in Family Link app (see "Change device" screen), not all devices
- **Charging state**: The API returns what appears to be a charging state value, but it has not been confirmed yet and is disabled until validated

---

## [0.9.7] - 2025-12

### Fixed
- **Regional Google domain cookie prioritization** - Fixed authentication for users with regional Google accounts (#48)
  - Users in Australia, UK, etc. may have SAPISID cookies from both `.google.com` and regional domains (e.g., `.google.com.au`)
  - The integration now correctly prioritizes `.google.com` cookies for SAPISIDHASH generation
  - Also applies to cookie header building, ensuring API compatibility

---

## [0.9.6] - 2025-12

### Added
- **`set_bedtime` service** - Set bedtime start/end times for a specific day (#46)
  - Parameters: `start_time`, `end_time`, `day` (optional, defaults to today), `child_id`
  - UI provides time pickers and dropdown for day selection
  - Example: Set bedtime to 20:45-07:30 for today or any specific day

### Fixed
- **Authentication loop fix** - Resolved issue where integration would continuously prompt for re-authentication (#48)
  - Root cause: Cookie cache (`_cookie_dict`, `_cookie_header`) was not invalidated on session refresh
  - The retry mechanism now properly reloads fresh cookies from the addon
- **SAPISID domain validation** - Now accepts regional Google domains (`.google.com.au`, `.google.co.uk`, etc.)
- **`set_daily_limit` now accepts 0 minutes** - Allows disabling device for the day without fully locking it (#47)
  - Useful for keeping unrestricted apps accessible while blocking screen time

---

## [0.9.5] - 2025-11

### Fixed
- **Bedtime/School Time toggle** - Now uses dynamic rule IDs instead of hardcoded UUIDs (#44)
  - Previously, enable/disable bedtime and school time failed with "invalid argument" error
  - Each Family Link account has unique rule UUIDs that are now fetched dynamically

---

## [0.9.4] - 2025-11-26

### Added
- **GPS Device Tracker** - Track child location via `device_tracker.<child>_family_link`
  - Opt-in configuration (disabled by default for privacy)
  - Shows saved places (Home, School) and full address
  - Attributes: source_device, place_name, address, location_timestamp
- Entity selector support for Family Link services (easier device selection in UI)
- HTTP API support for cookie retrieval (`/api/cookies`) - no shared volumes needed
- Auto-detection of auth source (API → file fallback)
- Manual URL configuration in config flow for Docker standalone
- **French & English translations** - Full i18n support for config flow and entities

### Changed
- Services now show entity picker dropdown instead of requiring manual device ID input

### Fixed
- **Auth notification** - `SessionExpiredError` now properly triggers persistent notification
- Auth notification sent only once (no spam every minute)
- Standalone Docker bashio errors (#28)

### Security
- Added warning: never expose port 8099 to internet (cookies returned in plain JSON)
- GPS tracking opt-in by default (each poll may notify child's device)

---

## [0.9.3] - 2025-11-24

### Fixed
- `set_daily_limit` service now uses dynamic day code based on current day
- Previously hardcoded to Saturday (CAEQBg), causing changes to not apply on other days
- Day codes: CAEQAQ (Mon) → CAEQBw (Sun)

---

## [0.9.2] - 2025-11-20

### Fixed
- Version correction (was incorrectly bumped)
- Stability improvements

---

## [0.9.0] - 2025-11-15

### Added
- `set_daily_limit` service to change daily screen time limit
- Improved API documentation

### Changed
- Better error handling for API calls

---

## [0.8.0] - 2025-01 (Release Candidate)

### Added
- Time bonus management (add/cancel bonuses)
- Enhanced per-device sensors:
  - `sensor.<device>_daily_limit` - Daily limit quota in minutes
  - `sensor.<device>_active_bonus` - Active time bonus in minutes
  - `sensor.<device>_screen_time_remaining` - Remaining screen time
- Reset Bonus button to cancel active bonuses
- +15min, +30min, +60min bonus buttons with auto-refresh

### Changed
- Daily Limit Reached sensor now returns true/false (ignores bonuses)

### Fixed
- Bedtime/school time window parsing (complete rewrite)
- Time calculations: bonus replaces normal time (doesn't add)
- Midnight-crossing support for bedtime windows

### Removed
- Redundant child-level schedule sensors:
  - `sensor.<child>_bedtime_schedule`
  - `sensor.<child>_school_time_schedule`
  - `sensor.<child>_daily_limit`

---

## [0.7.6] - 2025-01

### Added
- Parse bonus `override_id` from API response
- Reset Bonus button implementation

### Fixed
- Bonus detection false positives via `bonus_override_id` parsing
- Used time parsing (position 20 in API response)

---

## [0.7.4] - 2025-01

### Added
- Complete bedtime window parsing from API
- Complete school time window parsing from API
- Binary sensors for active detection:
  - `binary_sensor.<device>_bedtime_active`
  - `binary_sensor.<device>_school_time_active`
  - `binary_sensor.<device>_daily_limit_reached`

### Fixed
- Correct detection when device is in bedtime/school time window
- Midnight-crossing support (e.g., 20:55 → 10:00)

---

## [0.6.5] - 2024-12

### Added
- Bedtime switch (enable/disable per child)
- School Time switch (enable/disable per child)
- Daily Limit switch (enable/disable per child)
- Device lock/unlock functionality
- Screen time monitoring sensors

---

## [0.5.0] - 2024-12

### Added
- Real-time device lock state synchronization
- Lock state fetched from `appliedTimeLimits` API endpoint
- Bi-directional sync with Family Link app

---

## [0.4.x] - 2024-12

### Added
- Device lock/unlock functionality
- Switch entities per supervised device

---

## [0.3.0] - 2024-11

### Added
- App usage sensors
- Screen time sensors:
  - `sensor.<child>_daily_screen_time`
  - `sensor.<child>_screen_time_formatted`
- Top 10 apps tracking

---

## [0.2.x] - 2024-11

### Fixed
- Authentication improvements
- Cookie handling fixes

---

## [0.1.0] - 2024-10

### Added
- Initial release
- Family Link Auth add-on with Playwright
- Basic integration setup
- Cookie-based authentication
