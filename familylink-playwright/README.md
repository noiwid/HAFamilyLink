# Google Family Link Auth Add-on

![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)

A Home Assistant add-on that provides browser-based authentication for the Google Family Link integration.

## About

This add-on runs a web server with Playwright browser automation to handle Google authentication for the Family Link integration. Since Playwright cannot run directly in Home Assistant's Docker environment, this separate add-on provides the necessary infrastructure.

## Features

- 🔐 **Secure Browser Authentication**: Uses Playwright with Chromium for Google login
- 🖥️ **noVNC Web Access**: Browser runs in container, accessible via noVNC in your web browser (port 6080)
- 🔒 **Encrypted Cookie Storage**: All cookies are encrypted before storage
- 🌐 **User-Friendly Web Interface**: Simple web UI for authentication (port 8099)
- 🔄 **Automatic Cookie Management**: Stores cookies in shared storage for the integration
- 📊 **Status Monitoring**: Real-time authentication status updates

## Installation

### Prerequisites

- Home Assistant OS or Supervised installation
- The Google Family Link custom integration installed (via HACS)

### Steps

1. **Add Repository**:
   - Go to **Supervisor** → **Add-on Store**
   - Click the ⋮ menu → **Repositories**
   - Add: `https://github.com/noiwid/HAFamilyLink`

2. **Install Add-on**:
   - Find "Google Family Link Auth" in the add-on store
   - Click **Install**
   - Wait for installation to complete

3. **Configure** (Optional):
   - Go to the **Configuration** tab
   - Adjust settings if needed:
     - `log_level`: Logging verbosity (trace, debug, info, warning, error)
     - `auth_timeout`: Max time to wait for authentication (60-600 seconds)
     - `session_duration`: How long cookies remain valid (3600-604800 seconds)

4. **Start Add-on**:
   - Go to the **Info** tab
   - Click **Start**
   - Enable **Start on boot** and **Watchdog** (recommended)

5. **Open Web Interface**:
   - Click **Open Web UI** or navigate to `http://[YOUR_HA_IP]:8099`

## Usage

### First-Time Setup

1. **Start the Add-on**:
   - Ensure the add-on is running (green in Supervisor)

2. **Open the Web Interface**:
   - Click "Open Web UI" in the add-on info page
   - Or navigate to port 8099 in your browser

3. **Authenticate**:
   - Click "Démarrer l'authentification" (Start Authentication)
   - **Important**: The browser opens **inside the Docker container**, not on your computer
   - **To see and interact with the browser**, connect via noVNC in your web browser:
     - Open `http://[YOUR_HA_IP]:6080/vnc.html`
     - **Password**: `familylink`
     - Click **Connect**
     - No VNC client software is needed - it runs directly in your browser!
   - Once connected via noVNC, sign in with your Google account
   - Complete 2FA if prompted
   - Wait for the success message

4. **Configure Integration**:
   - Go to **Settings** → **Devices & Services**
   - Click **Add Integration**
   - Search for "Google Family Link"
   - Follow the setup wizard
   - The integration will automatically detect the cookies from the add-on

### Re-authentication

If your session expires or you need to re-authenticate:

1. Open the add-on web interface
2. Click "Démarrer l'authentification" again
3. Complete the Google login
4. The integration will automatically pick up the new cookies

## Configuration

### Add-on Options

```yaml
log_level: info
auth_timeout: 300
session_duration: 86400
```

| Option | Default | Description |
|--------|---------|-------------|
| `log_level` | `info` | Logging level (trace, debug, info, warning, error) |
| `auth_timeout` | `300` | Maximum time (seconds) to wait for user to complete login |
| `session_duration` | `86400` | How long (seconds) cookies remain valid (24 hours default) |

## Architecture

```
┌──────────────────────────────────────────────┐
│         Home Assistant Add-on                │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  FastAPI Web Server (Port 8099)       │ │
│  │  - Authentication UI                   │ │
│  │  - Status endpoints                    │ │
│  └────────────────┬───────────────────────┘ │
│                   │                          │
│  ┌────────────────▼───────────────────────┐ │
│  │  Playwright Browser Manager           │ │
│  │  - Launches Chromium                   │ │
│  │  - Monitors authentication             │ │
│  │  - Extracts cookies                    │ │
│  └────────────────┬───────────────────────┘ │
│                   │                          │
└───────────────────┼──────────────────────────┘
                    │
                    ▼
         /share/familylink/cookies.enc
                    │
                    │ (Encrypted cookies)
                    ▼
┌──────────────────────────────────────────────┐
│    Google Family Link Integration            │
│    (custom_components/familylink)            │
└──────────────────────────────────────────────┘
```

## Technical Details

### Cookie Retrieval Methods

The add-on provides **two methods** for the integration to retrieve cookies:

#### 1. HTTP API (v1.3.0+, Recommended for Docker standalone)
- **Endpoint**: `GET /api/cookies`
- **URL**: `http://<addon-ip>:8099/api/cookies`
- No shared volumes needed

#### 2. Shared Storage (Default for HA OS/Supervised)
- **Location**: `/share/familylink/`
- **Cookie File**: `cookies.enc` (encrypted with Fernet)
- **Key File**: `.key` (encryption key)

### Security

- ✅ Cookies encrypted at rest using Fernet (AES-128)
- ✅ Restrictive file permissions (0o600)
- ✅ Automatic session cleanup
- ✅ Browser isolation in container
- ✅ No external network dependencies

> ⚠️ **Security Warning**: **NEVER expose port 8099 to the internet!** The `/api/cookies` endpoint returns authentication cookies in plain JSON. This port should only be accessible on your local network. If you need remote access, use a VPN or SSH tunnel.

### Browser Automation

The add-on uses Playwright with Chromium running on a virtual display (Xvfb):

1. **Xvfb** creates a virtual display (`:99`) inside the container
2. **Chromium** launches on this virtual display via Playwright
3. **noVNC** provides web-based access to the virtual display (port 6080)
4. User connects via web browser to interact with the browser
5. After successful login:
   - Playwright extracts Google authentication cookies
   - Cookies are encrypted and stored in `/share/familylink/cookies.enc`
   - Browser resources are cleaned up

**Why noVNC is needed**: The browser runs headless inside the Docker container. noVNC allows you to see and interact with it remotely through your web browser.

## Troubleshooting

### Add-on Won't Start

- Check logs: **Supervisor** → **Google Family Link Auth** → **Log**
- Verify port 8099 is not in use by another add-on
- Ensure sufficient system resources (RAM, CPU)

### Browser Window Doesn't Open (on your computer)

**This is expected behavior!** The browser doesn't open on your local machine - it opens inside the Docker container.

**Solution**: Connect via noVNC in your web browser to see and interact with the browser:

1. **Open**: `http://[YOUR_HA_IP]:6080/vnc.html` (or `http://localhost:6080/vnc.html` if running locally)
2. **Password**: `familylink`
3. Click **Connect** - no VNC client software is needed!

**If noVNC connection fails**:
- Check add-on logs: `Supervisor` → `Google Family Link Auth` → `Log`
- Verify port 6080 is exposed and accessible
- Try restarting the add-on

### Integration Can't Find Cookies

- Verify add-on is running
- Check that authentication completed successfully in add-on UI
- Look for cookies in `/share/familylink/cookies.enc`
- Try re-authenticating through the add-on

### Authentication Timeout

- Increase `auth_timeout` in add-on configuration
- Ensure stable internet connection
- Check that Google account doesn't have unusual security restrictions

## Support

- **Issues**: [GitHub Issues](https://github.com/noiwid/HAFamilyLink/issues)
- **Discussions**: [GitHub Discussions](https://github.com/noiwid/HAFamilyLink/discussions)

## Changelog

### v1.0.0 (2025-01-07)

- Initial release
- Browser-based authentication with Playwright
- FastAPI web interface
- Encrypted cookie storage
- Integration with Family Link custom component

## License

MIT License - see LICENSE file for details

---

**⚠️ Important Disclaimer**

This add-on uses unofficial methods to interact with Google Family Link. Use at your own risk. This may violate Google's Terms of Service and could result in account restrictions.
