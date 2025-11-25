# Documentation - Google Family Link Auth Add-on

## Introduction

The Google Family Link Auth Add-on provides a browser-based authentication service for the Google Family Link integration. It solves the problem of running Playwright (browser automation) in Home Assistant's restricted Docker environment by providing a separate container with all necessary dependencies.

## How It Works

### Authentication Flow

```
1. User opens add-on web interface
2. Clicks "Start Authentication"
3. Add-on launches Chromium browser with Playwright
4. User logs in to Google in the browser window
5. Add-on monitors for successful authentication
6. Extracts Google cookies from browser session
7. Encrypts and saves cookies to /share/familylink/
8. Closes browser and cleans up resources
9. Integration reads cookies from shared storage
10. User completes setup in Home Assistant
```

### Communication Between Add-on and Integration

The add-on provides **two methods** for the integration to retrieve cookies:

#### 1. HTTP API (v1.3.0+, Recommended for Docker standalone)
- **Endpoint**: `GET /api/cookies`
- **URL**: `http://<addon-ip>:8099/api/cookies`
- Returns encrypted cookies and key directly
- No shared volumes needed

#### 2. Shared File Storage (Default for HA OS/Supervised)
- **Add-on writes**: Encrypted cookies to `/share/familylink/cookies.enc`
- **Integration reads**: Cookies from the same location
- **Encryption**: Shared key in `/share/familylink/.key`

Both approaches are:
- ✅ Simple and reliable
- ✅ Survives restarts
- ✅ Secure (encrypted at rest)

## Installation Guide

### Step 1: Install Add-on

1. Add repository URL to Home Assistant:
   - Supervisor → Add-on Store → ⋮ → Repositories
   - Add: `https://github.com/noiwid/HAFamilyLink`

2. Find "Google Family Link Auth" in store
3. Click Install
4. Wait for build to complete (may take 5-10 minutes)

### Step 2: Configure Add-on

Optional configuration in **Configuration** tab:

```yaml
log_level: info          # Set to 'debug' for troubleshooting
auth_timeout: 300        # 5 minutes for user to complete login
session_duration: 86400  # Cookies valid for 24 hours
```

### Step 3: Start Add-on

1. Go to **Info** tab
2. Click **Start**
3. Enable **Start on boot** (recommended)
4. Enable **Watchdog** (automatic restart on crash)

### Step 4: Authenticate

1. Click **Open Web UI** or navigate to `http://[YOUR_HA]:8099`
2. Click "Démarrer l'authentification"
3. Browser window opens automatically
4. Sign in to Google
5. Complete 2FA if required
6. Wait for success message
7. Close add-on UI

### Step 5: Configure Integration

1. Settings → Devices & Services → Add Integration
2. Search "Google Family Link"
3. Fill in configuration:
   - Name: "Family Link" (or custom name)
   - Other settings as needed
4. Click Submit
5. Integration automatically loads cookies from add-on
6. Setup complete!

## Configuration Reference

### Add-on Configuration

| Option | Type | Range | Default | Description |
|--------|------|-------|---------|-------------|
| `log_level` | list | trace, debug, info, warning, error | info | Logging verbosity |
| `auth_timeout` | int | 60-600 | 300 | Max seconds to wait for authentication |
| `session_duration` | int | 3600-604800 | 86400 | Cookie validity period (seconds) |

### Integration Configuration

Configured through Home Assistant UI:

- **Name**: Friendly name for the integration
- **Cookie File**: Path to cookie storage (managed automatically)
- **Update Interval**: How often to poll for device status (30-3600 seconds)
- **Timeout**: API request timeout (10-120 seconds)

## API Reference

The add-on exposes a REST API on port 8099:

### Endpoints

#### `GET /`
Returns the web interface HTML

#### `GET /api/health`
Health check endpoint

**Response:**
```json
{
  "status": "healthy",
  "service": "familylink-auth",
  "version": "1.0.0"
}
```

#### `POST /api/auth/start`
Start a new authentication session

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started",
  "message": "Authentication session started"
}
```

#### `GET /api/auth/status/{session_id}`
Check authentication status

**Response:**
```json
{
  "status": "authenticating|completed|timeout|error",
  "has_cookies": true,
  "cookie_count": 15,
  "error": null
}
```

#### `GET /api/cookies/check`
Check if cookies exist

**Response:**
```json
{
  "exists": true
}
```

#### `GET /api/cookies`
Retrieve stored cookies (used by integration)

**Response:**
```json
{
  "cookies": [...],
  "status": "success",
  "count": 15
}
```

#### `DELETE /api/cookies`
Delete stored cookies

**Response:**
```json
{
  "status": "success",
  "message": "Cookies deleted"
}
```

## Troubleshooting

### Common Issues

#### Add-on Won't Start

**Symptom**: Add-on shows red/stopped status

**Solutions**:
1. Check logs for specific error
2. Verify system has enough RAM (minimum 512MB free)
3. Ensure port 8099 isn't used by another service
4. Try rebuilding: Stop → Uninstall → Reinstall

#### Browser Window Doesn't Appear

**Symptom**: Authentication starts but no browser window

**Solutions**:
1. Check add-on logs: `[INFO] Navigating to Google Family Link...`
2. Browser opens on add-on's display, not yours (by design)
3. This is normal - the browser runs inside the container
4. Monitor status through web interface instead

#### Authentication Timeout

**Symptom**: "Authentication timeout" error after 5 minutes

**Solutions**:
1. Increase `auth_timeout` in configuration
2. Be quicker with login process
3. Have 2FA codes ready beforehand
4. Check internet connection stability

#### Integration Can't Find Cookies

**Symptom**: Integration setup fails with "No cookies found"

**Solutions**:
1. Verify add-on is running (green status)
2. Complete authentication in add-on first
3. Check `/share/familylink/cookies.enc` exists:
   - Terminal & SSH add-on: `ls -la /share/familylink/`
4. Review add-on logs for errors during authentication
5. Try re-authenticating

#### Cookies Expire Too Quickly

**Symptom**: Need to re-authenticate frequently

**Solutions**:
1. Increase `session_duration` in add-on config
2. Note: Google may invalidate cookies server-side
3. This is normal for security-sensitive accounts
4. Consider setting up re-auth automation

### Debug Mode

Enable debug logging for troubleshooting:

```yaml
log_level: debug
```

Then check logs:
- Supervisor → Google Family Link Auth → Log tab
- Or: `ha addons logs familylink-auth`

Look for:
- `[DEBUG] Starting browser authentication`
- `[DEBUG] Navigating to Google Family Link`
- `[DEBUG] Waiting for authentication...`
- `[INFO] Extracted X Google cookies`
- `[INFO] Saved X cookies to shared storage`

## Security Considerations

### Encryption

All cookies are encrypted using **Fernet** (symmetric encryption with AES-128):

```python
from cryptography.fernet import Fernet

# Generate key (done once)
key = Fernet.generate_key()

# Encrypt cookies
fernet = Fernet(key)
encrypted = fernet.encrypt(json_data.encode())

# Decrypt cookies (in integration)
decrypted = fernet.decrypt(encrypted)
```

### File Permissions

Restrictive permissions protect sensitive data:

```bash
/share/familylink/          # 700 (owner only)
/share/familylink/.key      # 600 (owner read/write only)
/share/familylink/cookies.enc # 600 (owner read/write only)
```

### Network Isolation

- Add-on only exposes port 8099 (web UI)
- No external API endpoints
- Browser communicates only with Google
- No telemetry or analytics

### Best Practices

1. ✅ Use strong Google account password
2. ✅ Enable 2FA on Google account
3. ✅ Don't expose port 8099 to internet
4. ✅ Use HTTPS if accessing remotely (via HA proxy)
5. ✅ Regularly update add-on
6. ✅ Monitor add-on logs for unusual activity

## Advanced Usage

### Manual Cookie Management

Delete cookies manually:

```bash
# Via Terminal & SSH add-on
rm /share/familylink/cookies.enc
```

Or via API:

```bash
curl -X DELETE http://localhost:8099/api/cookies
```

### Automation

Create automation to notify when re-authentication needed:

```yaml
automation:
  - alias: "Family Link Re-auth Needed"
    trigger:
      - platform: state
        entity_id: sensor.familylink_status
        to: "authentication_required"
    action:
      - service: notify.mobile_app
        data:
          message: "Family Link needs re-authentication"
          data:
            url: "http://homeassistant.local:8099"
```

### Multiple Accounts

The add-on currently supports one Google account at a time. For multiple accounts:

1. Authenticate with account A
2. Configure integration
3. Re-authenticate with account B
4. Integration will use account B's cookies
5. Account A integration will stop working

**Workaround**: Run multiple Home Assistant instances or request multi-account feature.

## Performance

### Resource Usage

Typical resource consumption:

- **RAM**: ~200MB idle, ~500MB during authentication
- **CPU**: <5% idle, ~20-30% during authentication
- **Storage**: <100MB total
- **Network**: Only during authentication (~5-10MB)

### Optimization Tips

1. Stop add-on when not authenticating (to save resources)
2. Increase session_duration to reduce authentication frequency
3. Use "Start on boot" only if re-authentication is frequent

## FAQ

**Q: Why a separate add-on instead of direct integration?**
A: Home Assistant's Docker environment restricts browser automation. Playwright requires system dependencies that can't be installed in the main container.

**Q: Is this safe?**
A: Yes, with caveats. Cookies are encrypted, and the add-on uses standard security practices. However, this is an unofficial method that may violate Google's ToS.

**Q: Will my account be banned?**
A: Possibly. Google doesn't officially support this. Use test accounts or accept the risk.

**Q: How long do cookies last?**
A: Typically 24 hours to several weeks, depending on Google's security settings for your account.

**Q: Can I use this with multiple Google accounts?**
A: Currently no. Only one account at a time. Feature request welcome!

**Q: Does this work on Home Assistant Container/Core (Docker)?**
A: Yes! Starting with v0.9.4/v1.3.0, Docker standalone is supported. Run the add-on as a standalone Docker container and configure the integration with the auth server URL. See [Docker Standalone Guide](../DOCKER_STANDALONE.md).

**Q: Can I run this on Raspberry Pi?**
A: Yes, but performance may be slow during authentication due to browser automation overhead. ARM builds are supported.

**Q: What if Google changes their login page?**
A: The add-on may break. Updates will be released to adapt to Google's changes.

---

## Support & Contributing

- **Report Issues**: [GitHub Issues](https://github.com/noiwid/HAFamilyLink/issues)
- **Feature Requests**: [GitHub Discussions](https://github.com/noiwid/HAFamilyLink/discussions)
- **Contributions**: Pull requests welcome!

## Changelog

See [README.md](README.md) for version history.
