# <img src="https://brands.home-assistant.io/familylink/icon.png" alt="Google Family Link" width="30" > Google Family Link Home Assistant Integration

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]][license]
[![HACS][hacs-shield]][hacs]

A comprehensive Home Assistant integration for monitoring and controlling Google Family Link devices. Track screen time, manage time limits, control bedtime/school schedules, and manage time bonuses directly from Home Assistant.

## 🚨 Important Disclaimer

This integration uses unofficial, reverse-engineered Google Family Link API endpoints. **Use at your own risk**. This may violate Google's Terms of Service and could result in account suspension. This project is not affiliated with, endorsed by, or connected to Google LLC.

## ✨ Features

### 📱 Device Control
- **Lock/Unlock Devices** - Control device access with switches in Home Assistant
- **Real-time Synchronization** - Lock state automatically syncs with Google Family Link
- **Multi-device Support** - Manage multiple supervised devices
- **Bi-directional Control** - Changes made in Family Link app reflect in Home Assistant

### ⏰ Time Management
- **Bedtime Control** - Enable/disable bedtime (downtime) restrictions
- **Set Bedtime Schedule** - Modify bedtime start/end times for any day (or today by default)
- **School Time Control** - Enable/disable school time restrictions
- **Daily Limit Control** - Enable/disable daily screen time limits (0-1440 minutes)
- **Set Daily Limit** - Change daily screen time limit duration per device
- **Time Bonuses** - Add extra time (15min, 30min, 60min) or cancel active bonuses
- **Smart Detection** - Automatically detects when device is in bedtime/school time window
- **Schedule Visibility** - View bedtime and school time schedules in sensor attributes

### 📊 Screen Time Monitoring
- **Daily Screen Time** - Track total daily usage per child
- **Screen Time Remaining** - See remaining time per device (accounts for bonuses and used time)
- **Daily Limit Tracking** - Monitor daily limit quota per device
- **Active Bonus Display** - See active time bonuses per device
- **Top 10 Apps** - Monitor most-used apps with detailed usage statistics
- **App Breakdown** - Per-application usage breakdown

### 📲 App Management
- **Installed Apps Count** - Total number of apps on supervised devices
- **Blocked Apps** - List and count of blocked/hidden apps
- **Apps with Time Limits** - Track apps with usage restrictions
- **App Details** - Package names, titles, and limit information

### 📍 GPS Location Tracking (Optional)
- **Device Tracker** - Track your child's location via `device_tracker` entity
- **Place Detection** - Automatically shows when child is at a saved place (Home, School, etc.)
- **Address Display** - Full address of current location
- **Source Device** - Shows which device provided the location
- **Battery Level** - Monitor battery percentage of the location source device
- **Privacy First** - Disabled by default, opt-in via configuration
- **⚠️ Warning** - Each location poll may notify the child's device

### 👶 Child Information
- **Profile Details** - Child's name, email, birthday, age band
- **Device Information** - Device model, name, capabilities, last activity
- **Family Members** - List of all family members with roles

## 📋 Available Entities

### Per-Child Entities

#### Device Tracker (GPS Location - Optional)
- `device_tracker.<child>` - Child's GPS location
  - **State**: `home`, `not_home`, or zone name
  - **Attributes**:
    - `source_device` - Device name providing the location
    - `place_name` - Saved place name (e.g., "Home", "School")
    - `address` - Full address of the location
    - `location_timestamp` - When the location was captured
    - `battery_level` - Battery percentage of source device
  - **Note**: Requires enabling "GPS location tracking" in integration config

#### Battery Sensor (GPS Location - Optional)
- `sensor.<child>_battery_level` - Battery level of location source device
  - **State**: Battery percentage (0-100%)
  - **Device Class**: `battery`
  - **Attributes**:
    - `source_device` - Device name providing the battery data
    - `last_update` - Timestamp of last update
  - **Note**: Requires enabling "GPS location tracking" in integration config
  - **⚠️ Limitation**: Shows battery of the device selected for location tracking in Family Link app, not all devices

#### Switches (Global Controls)
- `switch.<child>_bedtime` - Enable/disable bedtime restrictions
- `switch.<child>_school_time` - Enable/disable school time restrictions
- `switch.<child>_daily_limit` - Enable/disable daily screen time limit

### Per-Device Entities

#### Sensors
- `sensor.<device>_screen_time_remaining` - Remaining screen time in minutes
- `sensor.<device>_next_restriction` - Next upcoming restriction (bedtime/school time)
- `sensor.<device>_daily_limit` - Daily limit quota in minutes
- `sensor.<device>_active_bonus` - Active time bonus in minutes

#### Binary Sensors
- `binary_sensor.<device>_bedtime_active` - Currently in bedtime window
  - Attributes: `bedtime_start`, `bedtime_end` (ISO timestamps)
- `binary_sensor.<device>_school_time_active` - Currently in school time window
  - Attributes: `schooltime_start`, `schooltime_end` (ISO timestamps)
- `binary_sensor.<device>_daily_limit_reached` - Daily limit reached (true/false, ignores bonuses)

#### Switches
- `switch.<device>` - Lock/unlock device
  - **ON** = Device unlocked (child can use device) 📱
  - **OFF** = Device locked (device is locked) 🔒

#### Buttons
- `button.<device>_15min` - Add 15 minutes bonus
- `button.<device>_30min` - Add 30 minutes bonus
- `button.<device>_60min` - Add 60 minutes bonus
- `button.<device>_reset_bonus` - Cancel active bonus (only available when bonus is active)

### Legacy Sensors (Child Level)
- `sensor.<child>_daily_screen_time` - Daily screen time in **minutes**
- `sensor.<child>_screen_time_formatted` - Daily screen time in **HH:MM:SS** format
- `sensor.<child>_installed_apps` - Number of installed apps
- `sensor.<child>_blocked_apps` - Number and list of blocked apps
- `sensor.<child>_apps_with_time_limits` - Apps with usage restrictions
- `sensor.<child>_top_app_1` through `sensor.<child>_top_app_10` - Top 10 most-used apps
- `sensor.<child>_device_count` - Number of supervised devices
- `sensor.<child>_child_info` - Supervised child's profile information

## 🎯 What's New in v1.0.0

### 🔠 Per-App Daily Time Limits (#59)

New `set_app_daily_limit` service to control screen time per application:

```yaml
# Set TikTok to 60 minutes/day for ALL children
service: familylink.set_app_daily_limit
data:
  package_name: com.zhiliaoapp.musically
  minutes: 60

# Remove the limit (restore unlimited)
service: familylink.set_app_daily_limit
data:
  package_name: com.zhiliaoapp.musically
  minutes: 0
```

### 👨‍👩‍👧‍👦 Multi-Child Support (#57)

App control services now apply to **ALL children** by default:
- `block_app`, `unblock_app`, and `set_app_daily_limit` affect all supervised children when no specific child is selected
- Use `entity_id` or `child_id` to target a specific child

```yaml
# Block YouTube for a specific child only
service: familylink.block_app
data:
  package_name: com.youtube.android
  entity_id: sensor.emma_screen_time
```

### API Changes
- New `async_get_all_supervised_children()` method
- New `async_set_app_daily_limit()` method


## 🏗️ Architecture

This project consists of two components that work together:

### 1. Family Link Auth Add-on (`familylink-playwright/`)
Provides secure, browser-based authentication:
- **Playwright Automation** - Headless Chromium for Google login
- **2FA Support** - Handles SMS, authenticator, and push notifications
- **Cookie Extraction** - Securely stores authentication cookies
- **Auto-refresh** - Keeps authentication fresh

### 2. Home Assistant Integration (`custom_components/familylink/`)
Provides monitoring and control:
- **Config Flow** - User-friendly setup wizard
- **API Client** - Communicates with Google Family Link API
- **Coordinator** - Manages data updates and caching
- **Entities** - Sensors, binary sensors, switches, and buttons

### Why Two Components?

Home Assistant's Docker environment restricts browser automation. The add-on runs in a separate container with Chromium and Playwright, while the integration handles data fetching and device control.

## 📦 Installation

See the detailed [Installation Guide](INSTALL.md) for step-by-step instructions.

> **📌 Note for Home Assistant Core/Container Users**
>
> If you're running Home Assistant **without Supervisor** (Core or Container installation), you'll need to run the authentication add-on as a standalone Docker container. See the [Docker Standalone Guide](DOCKER_STANDALONE.md) for detailed instructions.

### Quick Start (Home Assistant OS / Supervised)

1. **Install Family Link Auth Add-on**

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnoiwid%2FHAFamilyLink)
   - Add repository to Home Assistant 
   - Install and start the add-on
   - Authenticate via Web UI (requires VNC client - see [Installation Guide](INSTALL.md))


2. **Install Integration**

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Noiwid&repository=HAFamilyLink&category=integration)
   - Via HACS (recommended) or manually
   - Configure through Home Assistant UI
   - Cookies automatically loaded from add-on

3. **Enjoy!**
   - Monitor screen time
   - Control time limits
   - Manage bonuses
   - Create automations

## ⚙️ Configuration

### Update Interval

The default update interval is 5 minutes (300 seconds). You can customize this in `configuration.yaml`:

```yaml
# configuration.yaml (optional)
familylink:
  scan_interval: 300  # seconds
```

### Lock State Synchronization

Device states are fetched from Google's `appliedTimeLimits` API endpoint. Changes made from the Family Link app or website are reflected in Home Assistant within the next update cycle.

## 🔧 API Endpoints Used

This integration uses reverse-engineered Google Family Link API endpoints:

| Endpoint | Purpose |
|----------|---------|
| `/families/mine/members` | Family member information |
| `/families/mine/location/{userId}` | Child GPS location |
| `/people/{userId}/apps` | Installed apps list |
| `/people/{userId}/appsandusage` | App usage data |
| `/people/{userId}/timeLimitOverrides:batchCreate` | Lock/unlock devices, add time bonuses |
| `/people/{userId}/timeLimitOverride/{id}?$httpMethod=DELETE` | Cancel time bonuses |
| `/people/{userId}/appliedTimeLimits` | Current time limits and lock states |
| `/people/{userId}/timeLimit` | Time limit rules and schedules |
| `/people/{userId}/timeLimit:update` | Enable/disable bedtime, school time, daily limit |

## 🐛 Troubleshooting

### 401 Authentication Errors

**Symptoms**: Logs show "401 Unauthorized" errors

**Solutions**:
1. Verify Family Link Auth add-on is running
2. Check API is accessible: `curl http://localhost:8099/api/cookies` (or your addon IP)
3. For file fallback: Check `/share/familylink/cookies.enc` and `.key` exist
4. Restart add-on to refresh authentication
5. Reload integration in Home Assistant

### Lock State Not Updating

**Symptoms**: Device lock state doesn't reflect actual state

**Solutions**:
1. Check logs for API errors
2. Verify device is online and connected
3. Wait for next update cycle (default: 5 minutes)
4. Manually lock/unlock from Family Link app to test sync

### Bedtime/School Time Not Detected

**Symptoms**: Binary sensors always show "off"

**Solutions**:
1. Verify schedules are configured in Family Link app
2. Check sensor attributes for `bedtime_start` and `bedtime_end` timestamps
3. Ensure schedules are enabled for current day of week
4. Check Home Assistant timezone matches your actual timezone

### Sensors Show "Not Configured" or "Unavailable"

**Symptoms**: Some sensors don't show data

**Cause**:
- Child-level schedule sensors removed in v0.8.0 (use device-level binary sensors instead)
- No app usage data for current date

**Solution**:
- Manually delete old entities from UI
- Wait until child uses apps today for usage data

### Cookies Expired

**Symptoms**: "Session expired" errors in logs

**Solution**:
1. Open add-on Web UI (port 8099)
2. Click "Démarrer l'authentification"
3. Complete Google login
4. Integration automatically picks up new cookies

## 📊 Example Automations

### Bedtime Lock

```yaml
automation:
  - alias: "Lock phone at bedtime"
    trigger:
      - platform: time
        at: "21:00:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.child_phone
```

### Enable Bedtime Mode on Weeknights

```yaml
automation:
  - alias: "Enable bedtime on weeknights"
    trigger:
      - platform: time
        at: "20:00:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.firstname_lastname_bedtime
```

### Screen Time Alert

```yaml
automation:
  - alias: "Alert on excessive screen time"
    trigger:
      - platform: numeric_state
        entity_id: sensor.galaxy_tab_firstname_screen_time_remaining
        below: 30  # Less than 30 minutes remaining
    action:
      - service: notify.mobile_app
        data:
          message: "Only {{ states('sensor.galaxy_tab_firstname_screen_time_remaining') }} minutes remaining!"
```

### Add Bonus Time on Homework Completion

```yaml
automation:
  - alias: "Bonus time for homework"
    trigger:
      - platform: state
        entity_id: input_boolean.homework_done
        to: "on"
    action:
      - service: button.press
        target:
          entity_id: button.galaxy_tab_firstname_30min
      - service: notify.mobile_app
        data:
          message: "Good job! Added 30 minutes bonus time."
```

### Daily Limit Reached Notification

```yaml
automation:
  - alias: "Notify when daily limit reached"
    trigger:
      - platform: state
        entity_id: binary_sensor.galaxy_tab_firstname_daily_limit_reached
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "{{ trigger.to_state.attributes.device_name }} has reached its daily limit"
```

### Location-Based Automation (GPS Tracking)

```yaml
automation:
  - alias: "Notify when child leaves school"
    trigger:
      - platform: state
        entity_id: device_tracker.firstname
        from: "School"
    action:
      - service: notify.mobile_app_parent
        data:
          message: "{{ trigger.to_state.name }} has left school"

  - alias: "Notify when child arrives home"
    trigger:
      - platform: state
        entity_id: device_tracker.firstname
        to: "home"
    action:
      - service: notify.mobile_app_parent
        data:
          message: "{{ trigger.to_state.name }} is home!"
```

## 📈 Version History

- **v1.0.0** (2026-01) - Per-App Time Limits & Multi-Child Support 🎉
  - **New service `set_app_daily_limit`** - Set daily time limits per app (e.g., 60 min for TikTok)
  - **Multi-child support** - `block_app`, `unblock_app`, `set_app_daily_limit` apply to ALL children by default
  - Optional `entity_id` and `child_id` parameters for targeting specific children
 
- **v0.9.8** (2026-01) - Battery Level Support
  - **Battery Level Sensor** - Monitor battery % of location source device
  - Requires location tracking to be enabled
  - Shows battery of the device selected for location in Family Link app

- **v0.9.7** (2025-12) - Regional Google Domains Auth Fix
  - Fixed authentication loop with regional Google domains (.google.com.au, .google.co.uk, etc.)

- **v0.9.6** (2025-12) - Set Bedtime Service
  - New `familylink.set_bedtime` service to modify bedtime schedules dynamically
  - Fixed authentication issues
  - `set_daily_limit` now accepts 0 minutes to disable device

- **v0.9.5** (2025-11) - Bedtime/School Time Toggle Fix
  - Fixed bedtime/school time toggle (was using hardcoded UUIDs)
  - Now dynamically fetches rule IDs from timeLimit API

- **v0.9.4** (2025-11) - GPS Location & Docker Standalone
  - **GPS Device Tracker** - Track child location via `device_tracker` entity
    - Opt-in configuration (disabled by default for privacy)
    - Shows saved places (Home, School) and full address
  - **Docker Standalone Mode** - Run without Home Assistant Supervisor
    - HTTP API for cookie retrieval
    - Separate Docker images for addon vs standalone
  - **Entity Selectors** - Services now show entity pickers in UI
  - **French & English translations** - Full i18n support
  - **Auth Notification Fix** - Properly triggers when session expires (no spam)
  - **Bug Fixes** - Fixed set_daily_limit dynamic day codes, bashio errors

- **v0.9.3** (2025-11) - Set Daily Limit Fix
  - Fixed `set_daily_limit` applying to wrong day of week

- **v0.9.2** (2025-11) - Standalone Docker Fix
  - Fixed bashio errors in standalone Docker deployment
  - Created separate Docker images for HA OS/Supervised vs pure Docker

- **v0.9.1** (2025-11) - Auth Expiration Notification
  - Persistent notification when Google authentication expires
  - Re-authentication instructions included
  - "No app usage data" moved from warning to debug log

- **v0.8.0** (2025-01) - Release Candidate
  - Time bonus management (add/cancel bonuses)
  - Enhanced per-device sensors (daily limit, active bonus, screen time remaining)
  - Fixed bedtime/school time window parsing
  - Fixed time calculations (bonus replaces time, not adds)
  - Daily Limit Reached sensor returns true/false
  - Removed redundant child-level schedule sensors

- **v0.7.6** (2025-01) - Bonus cancellation and fixes
  - Parse bonus override_id from API
  - Reset Bonus button implementation
  - Fixed bonus detection false positives
  - Fixed used time parsing (position 20)

- **v0.7.4** (2025-01) - Bedtime/School Time parsing
  - Complete bedtime window parsing
  - Complete school time window parsing
  - Midnight-crossing support
  - Binary sensors for active detection

- **v0.6.5** (2024-12) - Stable base version
  - Bedtime, School Time, Daily Limit switches
  - Device lock/unlock functionality
  - Screen time monitoring

- **v0.5.0** - Real-time device lock state synchronization
- **v0.4.x** - Device lock/unlock functionality
- **v0.3.0** - App usage and screen time sensors
- **v0.2.x** - Authentication fixes and improvements
- **v0.1.0** - Initial release

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Make your changes with clear commit messages
4. Test thoroughly
5. Submit a pull request

### Development Setup

```bash
git clone https://github.com/noiwid/HAFamilyLink.git
cd HAFamilyLink
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- Developed by [@noiwid](https://github.com/noiwid)
- Based on the original work by [@tducret](https://github.com/tducret/familylink) (Python package documenting Family Link API endpoints)
- Inspired by [@Vortitron's HAFamilyLink](https://github.com/Vortitron/HAFamilyLink) repository
- Home Assistant community for integration examples and best practices
- Reverse engineering insights from browser DevTools analysis

## 📞 Support

- [Report Issues](https://github.com/noiwid/HAFamilyLink/issues)
- [Feature Requests](https://github.com/noiwid/HAFamilyLink/issues/new)
- [Discussions](https://github.com/noiwid/HAFamilyLink/discussions)

## ⚠️ Legal

This is an unofficial integration and is not affiliated with, endorsed by, or connected to Google LLC. All product names, logos, and brands are property of their respective owners. Use at your own risk.

[releases-shield]: https://img.shields.io/github/release/noiwid/HAFamilyLink.svg
[releases]: https://github.com/noiwid/HAFamilyLink/releases
[license-shield]: https://img.shields.io/github/license/noiwid/HAFamilyLink.svg
[license]: LICENSE
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://github.com/hacs/integration
