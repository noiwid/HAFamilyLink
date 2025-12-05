# Changelog

All notable changes to the Google Family Link Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
- **SAPISID domain validation** - Now accepts both `.google.com` and `google.com` cookie domains
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
