# Create the modified Markdown content with emojis and save it as a downloadable file

Installation Guide 🚀

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

**VNC Client (REQUIRED)** 🖥️  
- Windows/Mac/Linux: [TightVNC](https://www.tightvnc.com/), [RealVNC](https://www.realvnc.com/), or any VNC viewer  
- iOS: VNC Viewer (App Store)  
- Android: VNC Viewer (Google Play)  
- Why? Required to access the browser during Google authentication 🔐

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

The add-on handles Google authentication using Playwright browser automation.

### 1.1 Add the Repository 📁

1. Open Home Assistant  
2. Navigate to **Settings** > **Add-ons** > **Add-on Store**  
3. Click the **...** menu (top right) > **Repositories**  
4. Add this URL:  
