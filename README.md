# Google Family Link Home Assistant Integration (Beta)

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]][license]
[![HACS][hacs-shield]][hacs]


An Home Assistant integration for monitoring and controlling Google Family Link devices. Track screen time, manage apps, and lock/unlock your child's devices directly from Home Assistant.

## 🚨 Important Disclaimer

This integration uses unofficial, reverse-engineered Google Family Link API endpoints. **Use at your own risk**. This may violate Google's Terms of Service and could result in account suspension. This project is not affiliated with, endorsed by, or connected to Google LLC.

## ✨ Features

### 📱 Device Control
- **Lock/Unlock Devices** - Control device access with switches in Home Assistant
- **Real-time Synchronization** - Lock state automatically syncs with Google Family Link
- **Multi-device Support** - Manage multiple supervised devices
- **Bi-directional Control** - Changes made in Family Link app reflect in Home Assistant

### 📊 Screen Time Monitoring
- **Daily Screen Time** - Track total daily usage in minutes or formatted time (HH:MM:SS)
- **Top 10 Apps** - Monitor most-used apps with detailed usage statistics
- **App Breakdown** - Per-application usage breakdown with hours, minutes, seconds
- **Real-time Updates** - Automatic polling every 5 minutes (customizable)

### 📲 App Management
- **Installed Apps Count** - Total number of apps on supervised devices
- **Blocked Apps** - List and count of blocked/hidden apps
- **Apps with Time Limits** - Track apps with usage restrictions
- **App Details** - Package names, titles, and limit information

### 👶 Child Information
- **Profile Details** - Child's name, email, birthday, age band
- **Device Information** - Device model, name, capabilities, last activity
- **Family Members** - List of all family members with roles

## 📋 Available Entities

### Sensors

#### Screen Time
- `sensor.family_link_daily_screen_time` - Daily screen time in **minutes** (numeric, ideal for graphs and automations)
- `sensor.family_link_screen_time_formatted` - Daily screen time in **HH:MM:SS** format (text, ideal for display)

#### Apps
- `sensor.family_link_installed_apps` - Number of installed apps
- `sensor.family_link_blocked_apps` - Number and list of blocked apps
- `sensor.family_link_apps_with_time_limits` - Apps with usage restrictions
- `sensor.family_link_top_app_1` through `sensor.family_link_top_app_10` - Top 10 most-used apps

#### Devices & Family
- `sensor.family_link_device_count` - Number of supervised devices
- `sensor.family_link_child_info` - Supervised child's profile information

### Switches
- `switch.<device_name>` - Lock/unlock device
  - **ON** = Device unlocked (child can use phone) 📱
  - **OFF** = Device locked (phone is locked) 🔒

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
- **Entities** - Sensors and switches for monitoring and control

### Why Two Components?

Home Assistant's Docker environment restricts browser automation. The add-on runs in a separate container with Chromium and Playwright, while the integration handles data fetching and device control.

## 📦 Installation

See the detailed [Installation Guide](INSTALL.md) for step-by-step instructions.

### Quick Start

1. **Install Family Link Auth Add-on**
[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnoiwid%2FHAFamilyLink)
   - Add repository to Home Assistant
   - Install and start the add-on
   - Authenticate via Web UI
     
3. **Install Integration**
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Noiwid&repository=HAFamilyLink&category=integration)
   - Via HACS (recommended) or manually
   - Configure through Home Assistant UI
   - Cookies automatically loaded from add-on

4. **Enjoy!**
   - Monitor screen time
   - Control device locks
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

Device lock states are fetched from Google's `appliedTimeLimits` API endpoint. Changes made from the Family Link app or website are reflected in Home Assistant within the next update cycle.

## 🔧 API Endpoints Used

This integration uses reverse-engineered Google Family Link API endpoints:

| Endpoint | Purpose |
|----------|---------|
| `/families/mine/members` | Family member information |
| `/people/{userId}/apps` | Installed apps list |
| `/people/{userId}/appsandusage` | App usage data |
| `/people/{userId}/timeLimitOverrides:batchCreate` | Lock/unlock devices |
| `/people/{userId}/appliedTimeLimits` | Current lock states |

## 🐛 Troubleshooting

### 401 Authentication Errors

**Symptoms**: Logs show "401 Unauthorized" errors

**Solutions**:
1. Verify Family Link Auth add-on is running
2. Check cookies file exists: `/share/familylink/cookies.json`
3. Restart add-on to refresh authentication
4. Reload integration in Home Assistant

### Lock State Not Updating

**Symptoms**: Device lock state doesn't reflect actual state

**Solutions**:
1. Check logs for API errors
2. Verify device is online and connected
3. Wait for next update cycle (default: 5 minutes)
4. Manually lock/unlock from Family Link app to test sync

### Top Apps Unavailable

**Symptoms**: Top app sensors show as "unavailable"

**Cause**: No app usage data for current date

**Solution**: Wait until the child uses apps today. Sensors will populate automatically.

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

### Screen Time Alert

```yaml
automation:
  - alias: "Alert on excessive screen time"
    trigger:
      - platform: numeric_state
        entity_id: sensor.family_link_daily_screen_time
        above: 180  # 3 hours in minutes
    action:
      - service: notify.mobile_app
        data:
          message: "Child has used phone for over 3 hours today"
```

## 📈 Version History

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
