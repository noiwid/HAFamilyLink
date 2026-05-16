
# Installation Guide 🚀

Google Family Link Integration for Home Assistant 👨‍👩‍👧‍👦

---

## Table of Contents 📚

1. [Prerequisites](#prerequisites)
2. [Step 1: Install Add-on](#step-1-install-add-on)
3. [Step 2: Install Integration](#step-2-install-integration)
4. [Step 3: Configure](#step-3-configure)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites ✅

**Home Assistant OS or Supervised** 🧩  
- This integration requires Home Assistant add-ons  
- Not compatible with Home Assistant Container or Core (without Supervisor)

**Minimum System Requirements** 📦  
- 1GB RAM (for Playwright browser automation)  
- 500MB free disk space  
- Stable internet connection 🌐

**Google Family Link Account** 👨‍👩‍👧  
- Active Family Link account with at least one supervised child  
- Parent account credentials (with 2FA if enabled) 🔑

**HACS Installed** (Recommended) 🛠️  
- [Home Assistant Community Store](https://hacs.xyz/)  
- Makes installation and updates easier

---

## Step 1: Install the Family Link Auth Add-on 🔧

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fnoiwid%2FHAFamilyLink)

The add-on handles Google authentication using Playwright browser automation.

### 1.1 Add the Repository 📁

1. Open Home Assistant  
2. Navigate to **Settings** > **Add-ons** > **Add-on Store**  
3. Click the **...** menu (top right) > **Repositories**  
4. Add this URL:  
   ```
   https://github.com/noiwid/HAFamilyLink
   ```
5. Click **Add** > **Close**

### 1.2 Install the Add-on ⏬

1. In the Add-on Store, search for **"Google Family Link Auth"**  
2. Click on the add-on  
3. Click **Install**  
   - This may take 5-10 minutes (downloads Chromium browser) ⏱️  
   - Wait for "Installation completed" message

### 1.3 Configure the Add-on ⚙️

1. After installation, **do NOT start it yet**  
2. Click on the **Configuration** tab  
3. Review the default settings:  
   ```yaml
   port: 8099
   log_level: info
   # Cookies are stored as /share/familylink/cookies.enc (encrypted)
   ```
4. Change settings if needed (usually defaults are fine)  
5. Click **Save** 💾

### 1.4 Start the Add-on ▶️

1. Go to the **Info** tab  
2. Enable **"Start on boot"** (recommended)  
3. Enable **"Watchdog"** (automatically restarts if it crashes) 🐶  
4. Click **Start**  
5. Wait for the add-on to start (check logs for "Application startup complete") 📜

### 1.5 Authenticate with Google 🔐

**Step 1: Open the add-on web interface**
- Click "Open Web UI" (or navigate to `http://[YOUR_HA_IP]:8099`)
- You should see the Family Link Auth interface

**Step 2: Start Authentication**
- Click "Démarrer l'authentification" (Start Authentication)
- The Chromium browser launches inside the add-on container

**Step 3: Connect via noVNC (web-based)**
- Open your web browser and navigate to `http://[YOUR_HA_IP]:6080/vnc.html`
- **Password**: `familylink`
- Click **Connect**
- No VNC client software is needed - it runs directly in your browser! 🌐

**Step 4: Complete Google Login in the noVNC browser window**
- Enter your Google account email > Click **Next**
- Enter your password > Click **Next**
- Complete 2FA if prompted (SMS code, authenticator app, push notification, etc.)
- Grant permissions if asked
- **Keep the browser tab open** until you see the Family Link dashboard 🧭

**Step 5: Verify Success**
- The web interface (port 8099) will show "Authentication successful" ✅
- The add-on extracts cookies and saves them to `/share/familylink/cookies.enc` (encrypted) 🍪
- You can now close the noVNC browser tab

**Important Notes:** ⚠️
- The authentication session timeout is 5 minutes (configurable in add-on settings)
- If authentication fails, restart the add-on and try again 🔁
- The noVNC password is `familylink` by default

### 1.6 Verify Authentication 🧪

Check the add-on logs (**Log** tab):  
```
INFO: Navigating to https://families.google.com/families
INFO: Successfully extracted 26 cookies
INFO: Cookies saved to /share/familylink/cookies.enc (encrypted)
```
If you see "Successfully extracted X cookies", authentication is complete! 🎉

---

## Step 2: Install the Integration 📥

You can install the integration via HACS (recommended) or manually.

### Option A: Install via HACS (Recommended) ⭐

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Noiwid&repository=HAFamilyLink&category=Integration+)

1. Open Home Assistant  
2. Navigate to **HACS** > **Integrations**  
3. Click **...** (top right) > **Custom repositories**  
4. Add repository:  
   - **Repository**: `https://github.com/noiwid/HAFamilyLink`  
   - **Category**: `Integration`  
5. Click **Add**  
6. Close the custom repositories dialog  
7. Click **+ Explore & Download Repositories**  
8. Search for **"Google Family Link"**  
9. Click on the integration > **Download**  
10. Select the latest version > **Download**  
11. **Restart Home Assistant**  
    - Settings > System > Restart 🔄

### Option B: Manual Installation 📦

1. Download the [latest release](https://github.com/noiwid/HAFamilyLink/releases) from GitHub  
2. Extract the ZIP file  
3. Copy the `custom_components/familylink` folder to your Home Assistant `config/custom_components/` directory  

   Final structure:  
   ```
   config/
     custom_components/
       familylink/
         __init__.py
         manifest.json
         config_flow.py
         coordinator.py
         sensor.py
         switch.py
         const.py
         client/
           api.py
         auth/
           addon_client.py
   ```

4. **Restart Home Assistant** 🔄

---

## Step 3: Configure the Integration 🧰

### 3.1 Add the Integration ➕

1. Navigate to **Settings** > **Devices & Services**  
2. Click **+ Add Integration** (bottom right)  
3. Search for **"Google Family Link"**  
4. Click on the integration

### 3.2 Complete the Configuration Flow ✅

1. **Welcome Screen**  
   - Read the information  
   - Click **Submit**

2. **Integration Name** (optional) ✍️
   - Enter a custom name or leave default: "Google Family Link"
   - Optionally adjust update interval and timeout settings
   - **GPS Location Tracking** (optional): Enable to track your child's location
     - ⚠️ Warning: Each location poll may send a notification to the child's device
     - Disabled by default for privacy
   - **Note**: No cookie file path is required - cookies are loaded automatically
   - Click **Submit**

3. **Cookie Loading** 🍪
   - The integration will automatically load cookies from `/share/familylink/cookies.enc`
   - This happens in the background - no visible progress
   - **If successful**: The setup completes and you can click **Finish**
   - **If it fails**: You'll see an error message like "No cookies found" or "Failed to authenticate"

4. **Success!** 🎉
   - If setup completed without errors, click **Finish**
   - The integration is now configured

### 3.3 Verify Integration Setup 🔎

1. Go to **Settings** > **Devices & Services**
2. Find **"Google Family Link"** in the list
3. You should see:
   - Integration badge (blue/green) 🟦🟩
   - Number of devices
   - Number of entities

### 3.4 Check Logs (Optional) 📋

To verify cookies were loaded successfully, check the Home Assistant logs:

1. Go to **Settings** > **System** > **Logs**
2. Search for: `familylink`
3. Look for messages like:
   ```
   Successfully loaded X cookies from add-on
   Successfully set up Family Link integration
   ```

**Note**: These detailed messages appear in logs, not in the UI during setup.

---

## Verification 🔍

### Check Entities 🧾

1. Navigate to **Settings** > **Devices & Services** > **Google Family Link**  
2. Click on the integration to see all entities  
3. You should see:

   **Device Trackers (if GPS enabled):** 📍
   - `device_tracker.<child_name>` (one per child)

   **Sensors:** 📟
   - `sensor.family_link_daily_screen_time`
   - `sensor.family_link_screen_time_formatted`
   - `sensor.family_link_installed_apps`
   - `sensor.family_link_blocked_apps`
   - `sensor.family_link_apps_with_time_limits`
   - `sensor.family_link_top_app_1` through `sensor.family_link_top_app_10`
   - `sensor.family_link_device_count`
   - `sensor.family_link_child_info`

   **Switches:** 🎚️
   - `switch.<device_name>` (for each supervised device)

### Test Device Control 🧪

1. Go to **Developer Tools** > **States**  
2. Find `switch.<your_device_name>`  
3. Click the switch to test lock/unlock:  
   - **ON** = Device unlocked 🔓  
   - **OFF** = Device locked 🔒  
4. Verify the phone locks/unlocks  
5. Check the Family Link app to confirm state matches 📲

### Check Logs 🧾

1. Navigate to **Settings** > **System** > **Logs**  
2. Filter for "familylink"  
3. Look for:  
   ```
   Successfully loaded X cookies from add-on
   Fetched X apps, X devices, X usage sessions
   Fetched lock states for X devices
   Successfully updated all Family Link data
   ```

4. **No errors** means everything is working! ✅

---

## Troubleshooting 🐛

### Integration Not Found 🔎

**Problem:** Can't find "Google Family Link" when adding integration  

**Solution:**  
1. Verify files are in `config/custom_components/familylink/`  
2. Restart Home Assistant  
3. Clear browser cache (Ctrl+F5) 🧼  
4. Check logs for errors during startup

### Cookies Not Loading 🍪

**Problem:** Setup fails with error "No cookies found" or "invalid_auth" in the UI

**Where you see it:**
- **During setup**: Error message appears in the configuration dialog
- **In logs**: "Failed to load cookies from add-on" or "No cookies found"

**Solution:**
1. Verify add-on is running and has been used to authenticate at least once
2. Check `/share/familylink/cookies.enc` and `.key` exist:
   ```bash
   ls -la /share/familylink/
   # You should see: cookies.enc and .key (both files required)
   ```
3. Verify file permissions allow Home Assistant to read them:
   ```bash
   chmod 644 /share/familylink/cookies.enc
   chmod 644 /share/familylink/.key
   ```
4. Restart add-on
5. Re-authenticate via add-on Web UI (port 8099)
6. Try adding the integration again

### 401 Authentication Errors 🔐

**Problem:** Logs show "401 Unauthorized" errors  

**Solution:**  
1. Cookies may have expired ⏳  
2. Open add-on Web UI (`http://[YOUR_HA_IP]:8099`)  
3. Click "Démarrer l'authentification"  
4. Complete Google login again  
5. Wait for success message  
6. Reload integration in Home Assistant

### No Entities Created 🫥

**Problem:** Integration loads but no sensors/switches appear  

**Solution:**  
1. Check logs for API errors  
2. Verify you have at least one supervised child  
3. Check that child has an active device 📱  
4. Wait 5 minutes for first data update ⏱️  
5. Reload integration

### Switch Not Working 📴

**Problem:** Can't lock/unlock device from Home Assistant  

**Solution:**  
1. Verify device is online and connected  
2. Check Family Link app shows device  
3. Try locking from Family Link app first (to test)  
4. Check logs for "Device control failed" errors  
5. Reload integration

### Top Apps Always Unavailable 📉

**Problem:** Top app sensors never show data  

**Cause:** No usage data for current date  

**Solution:**  
1. Wait until child uses apps today  
2. Sensors auto-populate when data becomes available  
3. Check tomorrow after device has been used

---

## Re-authentication 🔄

Cookies expire periodically. To re-authenticate:

1. Open add-on Web UI: `http://[YOUR_HA_IP]:8099`  
2. Click **"Démarrer l'authentification"**  
3. Complete Google login flow  
4. Wait for success message  
5. Integration auto-loads new cookies (no reload needed) ✅

---

## Uninstalling 🧹

### Remove Integration ❌

1. Settings > Devices & Services > Google Family Link  
2. Click **...** > **Delete**  
3. Confirm deletion

### Remove Add-on ❌

1. Settings > Add-ons > Google Family Link Auth  
2. Click **Uninstall**  
3. Optionally remove repository from Add-on Store

### Clean Up Files 🧽

```bash
# Remove integration files
rm -rf /config/custom_components/familylink

# Remove cookies
rm -rf /share/familylink
```

---

## Getting Help 🤝

If you encounter issues:

1. **Check Logs**: Settings > System > Logs > Filter "familylink"  
2. **Search Issues**: [GitHub Issues](https://github.com/noiwid/HAFamilyLink/issues)  
3. **Report Bug**: [Create New Issue](https://github.com/noiwid/HAFamilyLink/issues/new)  
4. **Discussions**: [GitHub Discussions](https://github.com/noiwid/HAFamilyLink/discussions)

When reporting issues, please include:  
- Home Assistant version 🔢  
- Integration version 🧩  
- Add-on version 📦  
- Relevant log entries 🧾  
- Steps to reproduce 🔁  

---

## Next Steps ▶️

After installation:

1. **Create Automations** - See [README.md](README.md#example-automations)  
2. **Customize Entities** - Rename, change icons, set friendly names ✨  
3. **Add to Dashboard** - Create cards for monitoring 📊  
4. **Set Update Interval** - Customize polling frequency ⏱️  
5. **Explore Features** - Try all sensors and switches 🧭

Enjoy monitoring and controlling your child's devices with Home Assistant! 🎯
