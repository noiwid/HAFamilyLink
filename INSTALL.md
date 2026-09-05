# Installation Guide

Complete setup guide for the Google Family Link integration for Home Assistant.

> **Warning**: this project relies on unofficial, reverse-engineered Google endpoints. There is no official API: Google can change or break it at any time, and usage may conflict with Google's Terms of Service. Use at your own risk.

## How it works

The integration relies on a separate **auth service** (a Home Assistant add-on, or a standalone Docker container) that performs the interactive Google login and hands the session cookies over; the full architecture is described in the [README](README.md#how-it-works).

Pick the route that matches your Home Assistant installation:

| Your Home Assistant | Auth service | Follow |
|---|---|---|
| Home Assistant OS or Supervised | The add-on from this repository | [Route A](#route-a-home-assistant-os-or-supervised) |
| Home Assistant Container or Core | Standalone Docker container | [Route B](#route-b-home-assistant-container-or-core) |

Both routes then continue with the same [integration install](#install-the-integration) and [configuration flow](#configuration-flow).

## Prerequisites

- A Google account with Family Link configured and at least one supervised child.
- Route A: a Home Assistant installation with the add-on store (OS or Supervised).
- Route B: Docker (ideally with Docker Compose) on any machine Home Assistant can reach.
- HACS (optional but recommended) for easy install and updates of the integration.

## Route A: Home Assistant OS or Supervised

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnoiwid%2FHAFamilyLink)

1. Go to **Settings > Add-ons > Add-on Store**, open the three-dot menu, choose **Repositories**, and add `https://github.com/noiwid/HAFamilyLink`.
2. Install **Google Family Link Auth**. The image is built locally, so the install takes several minutes.
3. Start the add-on. Enabling **Start on boot** and **Watchdog** is recommended.
4. Log in to Google through the add-on: click **Open Web UI** (port 8099), click **Start Authentication**, then open the noVNC page (port 6080) and finish the Google login and 2FA in the browser window it shows. The full walkthrough, the options reference, and add-on troubleshooting are in the [add-on documentation](familylink-playwright/DOCS.md).
5. That is all on the auth side: the integration auto-detects the add-on and its API key. Continue with [Install the integration](#install-the-integration).

## Route B: Home Assistant Container or Core

1. Run the standalone auth container: [DOCKER_STANDALONE.md](DOCKER_STANDALONE.md) covers the Docker Compose file, environment variables, volumes, ports, and the `API_KEY` protection.
2. Authenticate through its web UI (`http://<docker-host>:8099`), using the same two-port flow as the add-on (start the authentication on port 8099, finish the Google login via noVNC on port 6080).
3. Note the URL you will give the integration: `http://<docker-host>:8099`. If you set the container's `API_KEY` environment variable, enter its value in the integration's separate masked API-key field.
4. Continue with [Install the integration](#install-the-integration). In the configuration flow, choose **Manual URL configuration (Docker standalone)** and enter that URL.

## Install the integration

### Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=noiwid&repository=HAFamilyLink&category=integration)

1. In HACS, open the three-dot menu and choose **Custom repositories**.
2. Add repository `https://github.com/noiwid/HAFamilyLink` with category **Integration**.
3. Search for **Google Family Link** and download the latest version.
4. Restart Home Assistant.

### Manual

1. Download `familylink.zip` from the [latest release](https://github.com/noiwid/HAFamilyLink/releases), or copy the `custom_components/familylink` folder from the repository.
2. Extract or copy it into your Home Assistant `config/custom_components/` directory, so that `config/custom_components/familylink/manifest.json` exists. Copy the folder in full: it contains subpackages (`auth/`, `client/`, `translations/`, `utils/`) and non-Python files (`services.yaml`, `strings.json`) that the integration needs; a partial copy will not load.
3. Restart Home Assistant.

## Configuration flow

Go to **Settings > Devices & Services > Add Integration** and search for **Google Family Link**.

### Step 1: connection method

The first screen is a menu with two options:

| Option | When to use it |
|---|---|
| **Auto-detect (add-on or local file)** | Route A. The integration finds the auth service on its own, trying in order: the add-on resolved through the Supervisor, then `http://localhost:8099`, then the encrypted cookie file `/share/familylink/cookies.enc`. |
| **Manual URL configuration (Docker standalone)** | Route B. You enter the container URL yourself. |

If auto-detect finds nothing, the flow falls back to the manual URL form.

### Step 2 (manual URL only): authentication server URL and API key

Enter the auth server URL, for example `http://192.168.1.100:8099`. If the standalone container has `API_KEY` configured, enter that value in the separate masked API-key field; otherwise leave the field empty.

Existing version-1 entries containing a query key are migrated automatically. The stored URL and unique ID become key-free, and diagnostics redact the separate key. Home Assistant config-entry storage and backups still contain the credential, so continue treating them as sensitive.

The flow verifies the URL with `GET /api/health`, then tries to fetch the cookies. If an error appears, see [Troubleshooting (setup)](#troubleshooting-setup) below.

### Step 3: settings

| Field | Default | Range | Notes |
|---|---|---|---|
| Integration Name | `Google Family Link` | | Display name of the config entry. |
| Update Interval (seconds) | `60` | 30 to 3600 | How often data is fetched from Google. |
| Request Timeout (seconds) | `30` | 10 to 120 | Timeout of each API request. |
| Enable GPS location tracking | off | | Adds a device tracker and a battery sensor per child. Each location poll may send a notification to the child's device, so it is disabled by default for privacy. |

The first data fetch runs during setup, so entities appear as soon as the flow completes. Entities are created per child (for example `sensor.<child>_daily_screen_time`) and per device (for example `switch.<device>`); the full entity and service catalog is in the [README](README.md).

### Changing settings later

**Configure** exposes update interval, timeout, and GPS options. To replace the authentication server or key, use the integration's **Reconfigure** action. With the same URL, leave the key blank to keep its existing value. When changing URL, enter the new server's key or explicitly select **Clear API key** for an unprotected standalone server. Saving reloads the integration.

## Re-authentication

Google sessions expire eventually. When that happens:

1. The integration automatically fetches fresh cookies from the auth service and retries once.
2. If that also fails, it creates a persistent notification in Home Assistant asking you to re-authenticate (only one notification, not one per failed poll).
3. Open the auth web UI (add-on **Open Web UI**, or `http://<docker-host>:8099`), click **Start Authentication**, and finish the Google login through noVNC again.
4. Nothing to reload on the integration side: fresh cookies are picked up automatically on the next poll, and the notification logic resets after the next successful fetch.

## Troubleshooting (setup)

Auth-service issues (noVNC not connecting, black screen, login timeout, VNC password) are covered in the [add-on documentation](familylink-playwright/DOCS.md#troubleshooting) and, for the container, in [DOCKER_STANDALONE.md](DOCKER_STANDALONE.md#troubleshooting).

### "Google Family Link" not found when adding the integration

- Check that `config/custom_components/familylink/manifest.json` exists at exactly that path.
- Restart Home Assistant after installing (required for new custom components), then clear the browser cache.
- Check **Settings > System > Logs** for import errors at startup.

### "Cannot connect" in the configuration flow

- Verify the auth service is running and healthy: `curl http://<host>:8099/api/health`.
- Verify Home Assistant can reach that host and port (Docker network, VLANs, firewall).

### "The server requires an API key" (HTTP 403)

- Route B: enter the value of the container's `API_KEY` environment variable in the separate API-key field. Leave it blank only when `API_KEY` is not configured.
- Route A: the key is read automatically from `/share/familylink/api_key`; a 403 usually means the URL was entered manually without the key. Prefer auto-detect on Route A.

### "No cookies found"

- Complete the Google login through the auth web UI first, and wait for the success message showing how many cookies were saved.
- Route A: check that `/share/familylink/cookies.enc` exists.

### Integration loads but shows no or partial data

- You need at least one supervised child, and the child needs at least one device.
- The first fetch runs during setup and data then refreshes every 60 seconds by default; check the logs (filter `familylink`) for API errors.
- Top-app sensors stay unavailable until the child has used apps today.

## Uninstalling

1. **Settings > Devices & Services > Google Family Link**, three-dot menu, **Delete**.
2. Remove the integration files: via HACS (**Remove**) or by deleting `config/custom_components/familylink/`, then restart Home Assistant.
3. Route A: uninstall the add-on and optionally remove the repository from the add-on store. Route B: stop and remove the container (`docker compose down`).
4. Optionally delete the stored cookies: `/share/familylink/` (Route A) or the container's `./data` directory (Route B).

## Getting help

Search the [existing issues](https://github.com/noiwid/HAFamilyLink/issues) or open a new one. Include your Home Assistant version, the integration and auth container versions, and the relevant log lines (**Settings > System > Logs**, filter `familylink`).
