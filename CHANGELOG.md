# Changelog

All notable changes to the Google Family Link Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.2.1] - 2025-03-15

### Fixed
- **`refresh_location` service returning HTTP 400** — The Google Kids Management API expects numeric protobuf enum values for `locationRefreshMode` (`1` = refresh, `0` = do not refresh). The previous string values (`"REFRESH"`, `"DO_NOT_REFRESH"`) caused `INVALID_ARGUMENT` errors (#84)

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
