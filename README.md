# <img src="https://brands.home-assistant.io/familylink/icon.png" alt="Google Family Link" width="30"> Google Family Link for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![HACS][hacsbadge]][hacs]
[![License][license-shield]][license]

Monitor and control Google Family Link from Home Assistant: screen time, device lock, bedtime and school time schedules, daily limits, communication restrictions, app blocking, time bonuses, and optional GPS location. Multiple children and multiple devices are supported out of the box.

> **Disclaimer.** This integration uses unofficial, reverse-engineered Google Family Link endpoints. There is no official API: Google can change or break things at any time, and using this integration may violate Google's Terms of Service and could result in account suspension. **Use at your own risk.** This project is not affiliated with, endorsed by, or connected to Google LLC.

![Family Link dashboard](https://raw.githubusercontent.com/noiwid/HAFamilyLink/main/examples/dashboard.png)

> An example Lovelace dashboard built from this integration. The YAML and setup instructions are in [`examples/`](examples/).

## How it works

The project ships two components that work together. The **integration** (`custom_components/familylink/`) polls Google's Family Link endpoints (every 60 seconds by default) and exposes entities and services. The **auth service** (`familylink-playwright/`) is a separate container running Chromium via Playwright: it performs the interactive Google login (2FA included) and hands the resulting session cookies to the integration, because Home Assistant's own container cannot run a browser. On Home Assistant OS / Supervised it installs as an add-on; everywhere else it runs as a [standalone Docker container](DOCKER_STANDALONE.md). When the Google session expires, you log in again in the auth service's web UI and the integration picks up the fresh cookies automatically.

The endpoints and payload shapes the integration relies on are documented in [GOOGLE_FAMILY_LINK_API_ANALYSIS.md](GOOGLE_FAMILY_LINK_API_ANALYSIS.md).

## Features

| Area | What you can do |
|------|-----------------|
| Device control | Lock and unlock devices, ring a device to locate it, see exactly why a device is currently blocked |
| Time management | Toggle bedtime, school time and daily limits, edit the weekly bedtime schedule or post a today-only override, add 15/30/60 minute bonuses |
| Screen time monitoring | Daily screen time per child, remaining time per device (bonuses included), top 10 apps, per-app usage breakdown |
| App management | Block or unblock apps, per-app daily limits (blocked, limited, unrestricted or "unlimited time"), one-call school mode that blocks everything except an essentials whitelist |
| Location (opt-in) | GPS device tracker with saved places and address, battery level of the source device, on-demand refresh |
| Robustness | Cached data on transient API errors, automatic session refresh, persistent notification when re-authentication is needed |

Translations: English, French, Hebrew.

## Quick start

The auth service must be running before you configure the integration.

1. **Set up authentication.**
   - *Home Assistant OS / Supervised:* add this repository as an add-on repository, install and start the **Google Family Link Auth** add-on, then complete the Google login through its web UI.

     [![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnoiwid%2FHAFamilyLink)
   - *Home Assistant Core / Container (no Supervisor):* run the standalone auth container instead. See [DOCKER_STANDALONE.md](DOCKER_STANDALONE.md).

2. **Install the integration** via HACS (recommended) or manually.

   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=noiwid&repository=HAFamilyLink&category=integration)

3. **Add it:** Settings > Devices & Services > Add Integration > search for "Family Link". Auto-detect finds the add-on by itself; standalone users choose manual URL configuration and enter the container's URL.

The full walkthrough (prerequisites, both auth routes, configuration options, re-authentication) is in **[INSTALL.md](INSTALL.md)**.

## Entities

Each child appears as a hub device named `<child> (Family Link)`, with every physical device attached to it. `<child>` and `<device>` below stand for the slugified child and device names.

| Entity | Scope | Shows / does |
|--------|-------|--------------|
| `sensor.<child>_daily_screen_time` | Child | Today's screen time in minutes, per-app breakdown in attributes |
| `sensor.<child>_screen_time_formatted` | Child | The same value as `HH:MM:SS` text |
| `sensor.<child>_installed_apps`, `_blocked_apps`, `_apps_with_time_limits`, `_apps_without_limits`, `_always_allowed_apps` | Child | App counts, with the matching app lists in attributes |
| `sensor.<child>_top_app_1` to `_top_app_10` | Child | Today's most-used apps, usage in minutes |
| `sensor.<child>_device_count` | Child | Number of supervised devices |
| `sensor.<child>_child_info` | Child | Profile: name, email, birthday, age band |
| `sensor.<child>_battery_level` | Child (GPS opt-in) | Battery of the device providing the location |
| `device_tracker.<child>_family_link` | Child (GPS opt-in) | GPS location: zone, saved place, address, battery |
| `switch.<child>_bedtime`, `_school_time`, `_daily_limit` | Child | Toggle restrictions. State reflects today's effective setting (weekly rule merged with same-day overrides); the school time switch also exposes `school_time_enabled_weekly` and `school_time_scheduled_today` attributes |
| `select.<child>_allowed_calls_texts` | Child | Choose who can call and text the child: anyone, only contacts you add, or contacts you add and limited groups |
| `sensor.<device>_screen_time_remaining` | Device | Remaining minutes today, accounting for bonuses and used time |
| `sensor.<device>_next_restriction` | Device | Next upcoming restriction as text, window timestamps in attributes |
| `sensor.<device>_daily_limit` | Device | Configured daily quota in minutes |
| `sensor.<device>_active_bonus` | Device | Active bonus minutes (0 when none) |
| `binary_sensor.<device>_bedtime_active`, `_school_time_active` | Device | Currently inside the bedtime / school time window |
| `binary_sensor.<device>_daily_limit_reached` | Device | Daily limit used up (ignores bonus time) |
| `switch.<device>` | Device | Device usability: ON means usable, OFF means manually locked, bedtime active, or daily limit reached. An active bonus overrides bedtime and daily-limit restrictions, but not a manual lock. The `restriction_reason` attribute tells you why |
| `button.<device>_15min`, `_30min`, `_60min`, `_reset_bonus` | Device | Add or cancel a time bonus |
| `button.<device>_ring` | Device | Ring the device to locate it |

GPS entities are only created when location tracking is enabled in the integration options (off by default; each location poll may notify the child's device).

## Services

| Service | Purpose |
|---------|---------|
| `familylink.block_app` / `familylink.unblock_app` | Block or unblock a single app by package name |
| `familylink.set_app_daily_limit` | Per-app daily limit: minutes, blocked, limit off, or unlimited time |
| `familylink.block_device_for_school` | Block every app except an essentials whitelist (dialer, messages, settings, maps, ...) plus your own additions |
| `familylink.unblock_all_apps` | Unblock every hidden app |
| `familylink.add_time_bonus` | Add 1 to 1440 bonus minutes to a device |
| `familylink.set_daily_limit` | Set a device's daily quota (0 disables the device for the day) |
| `familylink.enable_daily_limit` / `familylink.disable_daily_limit` | Toggle the daily screen time limit |
| `familylink.enable_bedtime` / `familylink.disable_bedtime` | Toggle bedtime, effective tonight (weekly toggle plus a same-day override) |
| `familylink.set_bedtime` | Edit the recurring weekly bedtime for a day, or post a today-only override (`scope: today`) |
| `familylink.enable_school_time` / `familylink.disable_school_time` | Toggle school time |
| `familylink.refresh_location` | Force a fresh GPS fix (uses more battery than the regular polling) |
| `familylink.ring_device` | Make a device ring so it can be found |

Targeting: every service accepts an optional `entity_id` or explicit `child_id` / `device_id`. Without a target, the app and location services apply to **all** supervised children, while the time services fall back to the **first** supervised child. Full field reference, defaults and examples: **[SERVICES.md](SERVICES.md)**.

## Troubleshooting

Setup and authentication problems (no entities, 403 on the cookie endpoint, session expired) are covered in [INSTALL.md](INSTALL.md); add-on specifics (web UI, VNC) in [familylink-playwright/DOCS.md](familylink-playwright/DOCS.md), including its [Security](familylink-playwright/DOCS.md#security) section: the browser view shows a live Google session, unmap port 6080 and stop the add-on when you are not authenticating.

## Changelog

All notable changes are tracked in [CHANGELOG.md](CHANGELOG.md) and published on [GitHub Releases](https://github.com/noiwid/HAFamilyLink/releases).

## Contributing

Contributions are welcome: fork the repository, create a feature branch, make your changes with clear commit messages, test against a live Home Assistant (there is no test suite; the integration is loaded by Home Assistant at runtime), and open a pull request.

This integration is free and maintained in my spare time. If it helped you or saved you time, you can buy me a beer:

[![Buy Me A Beer](https://img.shields.io/badge/Buy%20me%20a%20beer-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/noiwid)

## Credits

- Developed by [@noiwid](https://github.com/noiwid)
- Based on the original work by [@tducret](https://github.com/tducret/familylink) (Python package documenting Family Link API endpoints)
- Inspired by [@Vortitron's HAFamilyLink](https://github.com/Vortitron/HAFamilyLink) repository
- noVNC integration inspired by [@jnctech's fork](https://github.com/jnctech/HAFamilyLink)
- Home Assistant community for integration examples and best practices
- Reverse engineering insights from browser DevTools analysis

## Support

- [Report issues](https://github.com/noiwid/HAFamilyLink/issues)
- [Feature requests](https://github.com/noiwid/HAFamilyLink/issues/new)
- [Discussions](https://github.com/noiwid/HAFamilyLink/discussions)

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

This is an unofficial integration, not affiliated with, endorsed by, or connected to Google LLC. All product names, logos, and brands are property of their respective owners.

[releases-shield]: https://img.shields.io/github/release/noiwid/HAFamilyLink.svg?style=for-the-badge
[releases]: https://github.com/noiwid/HAFamilyLink/releases
[license-shield]: https://img.shields.io/github/license/noiwid/HAFamilyLink.svg?style=for-the-badge
[license]: LICENSE
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
