# Home Assistant Add-on: Google Family Link Auth

## About

This add-on performs the interactive Google login for the [Google Family Link integration](https://github.com/noiwid/HAFamilyLink). It launches a real Chromium window (Playwright) inside the container and streams it to your web browser through noVNC, so you sign in and complete 2FA exactly as you would on a desktop. Home Assistant's own container cannot run a browser, which is why this step lives in a separate add-on.

After a successful login, the add-on extracts the Google session cookies, encrypts them, and stores them under `/share/familylink/`. The integration then retrieves them automatically through the add-on's API (see [How the integration gets the cookies](#how-the-integration-gets-the-cookies)). One Google account at a time is supported.

> **Warning**: this project relies on unofficial, reverse-engineered Google endpoints and an automated login. There is no official API: Google can break it at any time, and usage may conflict with Google's Terms of Service. Use at your own risk.

## Installation

1. Go to **Settings > Add-ons > Add-on Store**, open the three-dot menu, choose **Repositories**, and add `https://github.com/noiwid/HAFamilyLink`.
2. Install **Google Family Link Auth**. The prebuilt image is downloaded from GHCR, so the install only takes a moment.
3. Optionally adjust the options in the **Configuration** tab (see [Configuration](#configuration)).
4. Start the add-on. Enabling **Start on boot** and **Watchdog** is recommended.

## How to use

> Two ports must be reachable from your browser: **8099** (web UI) and **6080** (noVNC). If you reach Home Assistant through a reverse proxy or an external domain, use the local IP instead (for example `http://192.168.1.x:8099`).

1. Click **Open Web UI**, or browse to `http://<HA local IP>:8099`.
2. Click **Start Authentication**. Chromium starts inside the container, never on your computer.
3. Open the noVNC link shown on that page, or browse to `http://<HA local IP>:6080/vnc.html`.
4. Enter the VNC password: the `vnc_password` option if you set one, otherwise the password generated at start and printed in the add-on **Log** tab (it changes at every start).
5. Sign in to Google in the noVNC window and complete 2FA. Wait for the success message showing how many cookies were saved, then close the noVNC tab.
6. Set up the integration in Home Assistant, following [INSTALL.md](https://github.com/noiwid/HAFamilyLink/blob/main/INSTALL.md). On Home Assistant OS the integration discovers the add-on and its API key automatically.

To re-authenticate later (expired session), repeat steps 1 to 5. The integration picks up the new cookies automatically.

## Configuration

Example add-on configuration:

```yaml
log_level: info
auth_timeout: 300
language: ""
timezone: ""
vnc_password: familylink
```

| Option | Type | Default | Description |
|---|---|---|---|
| `log_level` | list: `trace`, `debug`, `info`, `warning`, `error` | `info` | Logging level of the web service and startup scripts. |
| `auth_timeout` | int, 60 to 600 | `300` | Seconds you have to finish the Google login before the session times out. |
| `session_duration` | int, 3600 to 604800 | `86400` | Has no effect, kept for backward compatibility. Cookie lifetime is decided by Google. |
| `language` | string | `""` | Browser locale and web UI language. Empty: auto-detected from Home Assistant, fallback `en-US`. The web UI itself is translated in English and French; other locales fall back to English. |
| `timezone` | string | `""` | Browser timezone. Empty: auto-detected from Home Assistant, fallback `Europe/Paris`. |
| `vnc_password` | password | empty | noVNC password. Empty (or the old default `familylink`): a random password is generated at every start and printed in the add-on log. VNC authentication uses at most 8 characters: longer values are truncated to the first 8, with a warning in the log. |

### Ports

| Port | Exposed | Purpose |
|---|---|---|
| 8099 | yes | Web UI and REST API. **Never expose it to the internet**: `/api/cookies` returns Google session cookies. |
| 6080 | yes | noVNC browser view, protected by the VNC password only. Unmap it in **Configuration > Network** when you are not authenticating. |
| 5900 | no | VNC server, bound to localhost inside the container. |

## Security

The browser view behind noVNC shows a live Google session of the parent account. Whoever can open it can lift every restriction on the child's device. Keep this in mind:

- **The VNC password is the only protection of port 6080.** Until version 1.9.0 the add-on shipped with a documented default password, so anyone on the home network could open the view; since 1.9.0 a random password is generated at every start when none is configured, and the web UI never carries it.
- **Unmap port 6080** (and 8099 if the integration runs on the same Home Assistant) in **Configuration > Network** when you are not authenticating. You only need them during a login.
- **Stop the add-on after the login.** The integration reads the encrypted cookie file from `/share/familylink` on its own, so the add-on can stay stopped until the session expires. Disable **Start on boot** if you prefer.
- **Never expose ports 8099 or 6080 to the internet**, through a reverse proxy, Nabu Casa or a port forward: `/api/cookies` hands out a Google session.
- **Use a dedicated Google parent account** for this integration. The stored cookies are Google account cookies, not Family Link cookies: a leaked session reaches the whole account.
- Home Assistant backups include `/share/familylink`, and so a live session. Treat them accordingly.

A broader hardening of the add-on (authenticated browser view, service token in a header, session expiry, log redaction) is being ported from [Haulund-ATP's fork](https://github.com/Haulund-ATP/HAFamilyLink).

## How the integration gets the cookies

- Cookies are stored Fernet-encrypted in `/share/familylink/cookies.enc`, with the key in `/share/familylink/.key` (both mode 0600).
- On first start in add-on mode, an API key is generated and saved to `/share/familylink/api_key` (0600). The integration reads that file automatically and calls `GET /api/cookies` with it: nothing to configure.
- If the API is unreachable, the integration falls back to reading the encrypted file directly from `/share`.
- In the standalone container no key is auto-generated: set the `API_KEY` environment variable yourself, otherwise `/api/cookies` is unprotected. See [DOCKER_STANDALONE.md](https://github.com/noiwid/HAFamilyLink/blob/main/DOCKER_STANDALONE.md).

### API endpoints (port 8099)

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /` | none | Web UI. |
| `GET /api/health` | none | Health check. |
| `POST /api/auth/start` | key, only if the `API_KEY` env var is set | Start a login session (one at a time). |
| `GET /api/auth/status/{session_id}` | key, only if the `API_KEY` env var is set | Poll a session: `authenticating`, `completed`, `timeout`, or `error`. |
| `GET /api/cookies/check` | none | Whether stored cookies exist. |
| `GET /api/cookies` | cookie API key | Return the decrypted cookies. |
| `DELETE /api/cookies` | cookie API key | Delete the stored cookies. |

The key is accepted as an `X-API-Key` header or an `?api_key=` query parameter.

## Troubleshooting

### Where the logs are

- Add-on: **Settings > Add-ons > Google Family Link Auth > Log**. From the CLI: `ha addons logs <repository-hash>_familylink-playwright` (installed add-ons carry a repository hash prefix in their slug).
- Standalone container: `docker logs`; display-stack logs are also written to `/var/log/familylink/` inside the container.

Set `log_level: debug` for more detail. A successful run logs, among others: `Starting authentication session: <id>`, `Navigating to Google Family Link...`, `Monitoring authentication for session <id>`, `Extracted N Google cookies`, `Saved N cookies to shared storage`.

### No browser window appears on your computer

Expected: Chromium runs inside the container. Open the noVNC page (port 6080) to see and control it.

### noVNC does not connect, or the VNC password is refused

With no `vnc_password` configured, the password changes at every start: read the current one in the add-on **Log** tab (line "VNC password for this start").

- Check that ports 8099 and 6080 are both reachable from your browser; behind a reverse proxy, use the local IP.
- If the password is refused, check the `vnc_password` notes in the [Configuration](#configuration) table.
- Update to the latest add-on version: several display-stack bugs (crashes when a client connects, silent failures) have been fixed over time, see the [changelog](https://github.com/noiwid/HAFamilyLink/blob/main/familylink-playwright/CHANGELOG.md).
- Restart the add-on and watch the log: each display process is health-checked at startup, so a failure is visible there.

### Black screen in noVNC

Before authentication starts, the display shows a welcome banner with instructions. If the screen stays black after clicking **Start Authentication**, check the log for display-stack errors.

### Authentication timeout

The login was not finished within `auth_timeout` seconds. Raise the option (up to 600) and have your 2FA device ready before starting.

### Integration cannot find cookies

1. Make sure the add-on is running and authentication completed (success message with the cookie count).
2. Check that `/share/familylink/cookies.enc` exists.
3. A corrupted cookie file is deleted automatically and reported as missing cookies: re-authenticate.

## Support

- Bugs and questions: [GitHub issues](https://github.com/noiwid/HAFamilyLink/issues)
- Version history: the add-on's **Changelog** tab, or [CHANGELOG.md](https://github.com/noiwid/HAFamilyLink/blob/main/familylink-playwright/CHANGELOG.md) and [GitHub releases](https://github.com/noiwid/HAFamilyLink/releases)
