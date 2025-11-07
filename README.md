# Google Family Link Home Assistant Integration

![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)

A robust Home Assistant integration for controlling Google Family Link devices through automation. This integration provides secure, browser-based authentication and reliable device control without storing sensitive credentials.

## 🚨 Important Disclaimer

This integration uses unofficial methods to interact with Google Family Link's web interface. **Use at your own risk** with test accounts only. This may violate Google's Terms of Service and could result in account suspension.

## ✨ Features

- **🔐 Secure Authentication**: Browser-based login with full 2FA support (no password storage)
- **📱 Device Control**: Lock/unlock children's devices as Home Assistant switches
- **🔄 Auto-Refresh**: Intelligent session management with automatic cookie renewal
- **🏠 Native Integration**: Full Home Assistant configuration flow and device registry
- **📊 Status Monitoring**: Real-time device status and connectivity monitoring
- **🛡️ Error Recovery**: Robust error handling with graceful degradation
- **🔧 Easy Setup**: User-friendly configuration via Home Assistant UI

## 🎯 Project Goals

Create a production-ready Home Assistant integration that:

1. **Seamlessly integrates** with Home Assistant's ecosystem
2. **Securely manages** authentication without credential storage
3. **Reliably controls** Family Link devices through automation
4. **Gracefully handles** errors, timeouts, and session expiration
5. **Provides clear feedback** to users about device status and issues
6. **Maintains compatibility** with Home Assistant updates and HACS

## 🏗️ Architecture Overview

### Two-Component Architecture

This project consists of two components that work together:

#### 1. Home Assistant Add-on (`familylink-addon/`)
Provides browser-based authentication using Playwright:
- **Web Interface**: User-friendly UI for Google authentication
- **Browser Automation**: Playwright-controlled Chromium for login
- **Cookie Management**: Encrypted storage of authentication cookies
- **Shared Storage**: Communicates with integration via `/share` directory

#### 2. Home Assistant Integration (`custom_components/familylink/`)
Provides device control and automation:
- **Config Flow**: User-friendly setup wizard
- **Cookie Client**: Reads cookies from add-on's shared storage
- **API Client**: Communicates with Google Family Link services
- **Device Entities**: Switch entities for device control
- **Coordinator**: Manages data updates and state

### Why Two Components?

Home Assistant's Docker environment restricts browser automation. The add-on runs in a separate container with all necessary dependencies (Chromium, Playwright), while the integration handles device control in the main HA environment.

### Communication Flow

```
┌─────────────────────────┐
│  Add-on Container       │
│  - Playwright           │
│  - Chromium browser     │
│  - FastAPI web server   │
└──────────┬──────────────┘
           │ Writes encrypted cookies
           ▼
┌──────────────────────────┐
│  /share/familylink/      │
│  - cookies.enc (AES-128) │
│  - .key (encryption key) │
└──────────┬───────────────┘
           │ Reads cookies
           ▼
┌──────────────────────────┐
│  Integration             │
│  - Addon Cookie Client   │
│  - API Client            │
│  - Device Control        │
└──────────────────────────┘
```

### Security Model

- **No Credential Storage**: Passwords never stored in Home Assistant
- **Encrypted Cookies**: Fernet (AES-128) encryption at rest
- **Isolated Browser**: Playwright runs in separate container
- **File Permissions**: Restrictive permissions (0o600) on sensitive files
- **Automatic Cleanup**: Secure session termination after authentication

## 📋 Development Plan

### Phase 1: Core Infrastructure (MVP)

**1.1 Project Structure & Foundation**
- [x] Repository setup with proper Python packaging
- [x] Home Assistant integration manifest and structure
- [ ] Logging framework with appropriate levels
- [ ] Configuration schema validation
- [ ] Error classes and exception handling

**1.2 Authentication System**
- [x] Playwright browser automation for Google login (in add-on)
- [x] 2FA flow handling (SMS, authenticator, push notifications)
- [x] Session cookie extraction and validation
- [x] Secure cookie storage with encryption
- [x] Authentication state management via add-on

**1.3 Device Discovery & Control**
- [ ] Family Link web scraping for device enumeration
- [ ] Device metadata extraction (name, type, status)
- [ ] HTTP client for device control endpoints
- [ ] Lock/unlock command implementation
- [ ] Device state polling and caching

### Phase 2: Home Assistant Integration

**2.1 Configuration Flow**
- [x] User-friendly setup wizard
- [x] Add-on authentication flow
- [x] Cookie integration from add-on
- [x] Error handling and user feedback
- [ ] Device selection and naming (pending API implementation)

**2.2 Entity Implementation**
- [ ] Switch entities for device control
- [ ] Device registry integration
- [ ] State management and updates
- [ ] Proper entity naming and unique IDs
- [ ] Icon and attribute assignment

### Phase 3: Reliability & Polish

**3.1 Session Management**
- [ ] Automatic cookie refresh logic
- [ ] Session expiration detection
- [ ] Re-authentication workflow
- [ ] Graceful fallback mechanisms

**3.2 Error Handling & Recovery**
- [ ] Comprehensive error classification
- [ ] Automatic retry mechanisms
- [ ] Circuit breaker pattern for failed requests
- [ ] User-friendly error messages

## 🛠️ Technical Implementation

### Dependencies

#### Add-on
```python
fastapi==0.109.0           # Web server
uvicorn==0.27.0            # ASGI server
playwright==1.41.0         # Browser automation
cryptography==42.0.0       # Cookie encryption
```

#### Integration
```python
aiohttp>=3.8.0             # Async HTTP client
cryptography>=3.4.8        # Cookie decryption
homeassistant>=2023.10.0   # Home Assistant core
```

**Note**: Playwright is only in the add-on, not in the integration!

### Directory Structure

```
HAFamilyLink/
├── familylink-addon/              # Home Assistant Add-on
│   ├── config.json                # Add-on configuration
│   ├── Dockerfile                 # Container definition
│   ├── requirements.txt           # Python dependencies
│   ├── app/                       # FastAPI application
│   │   ├── main.py               # Web server
│   │   ├── config.py             # Configuration
│   │   ├── auth/                 # Authentication module
│   │   │   └── browser.py        # Playwright manager
│   │   └── storage/              # Storage module
│   │       └── file_storage.py   # Cookie encryption
│   └── rootfs/                   # Container filesystem
│       ├── etc/services.d/       # S6 service definitions
│       └── usr/local/bin/        # Startup scripts
│
└── custom_components/familylink/  # Home Assistant Integration
    ├── __init__.py                # Integration entry point
    ├── manifest.json              # Integration metadata
    ├── config_flow.py             # Configuration UI
    ├── const.py                   # Constants
    ├── coordinator.py             # Data coordinator
    ├── switch.py                  # Switch entities
    ├── exceptions.py              # Custom exceptions
    ├── auth/
    │   ├── addon_client.py        # Read cookies from add-on
    │   └── session.py             # Session management
    ├── client/
    │   ├── api.py                 # Family Link API client
    │   └── models.py              # Data models
    └── utils/
        └── __init__.py
```

## 🔒 Security Considerations

- **Cookie Encryption**: All session data encrypted using Home Assistant's secret key
- **Memory Management**: Sensitive data cleared from memory after use
- **Session Isolation**: Browser sessions run in isolated containers
- **TLS Enforcement**: All communications over HTTPS

## 📦 Installation & Setup

### Prerequisites

- Home Assistant OS or Supervised (add-ons not available in Container or Core)
- Minimum 1GB RAM (for browser automation)
- Internet connection

### Step 1: Install the Add-on

1. **Add Repository**:
   - Go to **Supervisor** → **Add-on Store**
   - Click ⋮ menu → **Repositories**
   - Add: `https://github.com/noiwid/HAFamilyLink`

2. **Install Add-on**:
   - Find "Google Family Link Auth" in the store
   - Click **Install** (may take 5-10 minutes)
   - Click **Start**
   - Enable "Start on boot"

3. **Authenticate**:
   - Click **Open Web UI**
   - Click "Démarrer l'authentification"
   - Sign in to Google in the browser window
   - Wait for success message

### Step 2: Install the Integration

1. **Via HACS** (Recommended):
   - HACS → Integrations → ⋮ → Custom repositories
   - Add: `https://github.com/noiwid/HAFamilyLink`
   - Category: Integration
   - Search "Google Family Link" and install

2. **Or Manual Installation**:
   - Copy `custom_components/familylink` to your HA config directory
   - Restart Home Assistant

### Step 3: Configure Integration

1. **Add Integration**:
   - Settings → Devices & Services → Add Integration
   - Search "Google Family Link"

2. **Complete Setup**:
   - Enter integration name
   - Adjust optional settings
   - Click Submit
   - Integration automatically loads cookies from add-on

3. **Done!** Your Family Link devices should appear as switches

### Re-authentication

When cookies expire:
1. Open add-on web UI (`http://[YOUR_HA]:8099`)
2. Click "Démarrer l'authentification"
3. Complete Google login
4. Integration automatically picks up new cookies

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

### Development Setup

```bash
# Clone repository
git clone https://github.com/noiwid/HAFamilyLink.git
cd HAFamilyLink

# Setup development environment
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
playwright install

# Run tests
python -m pytest tests/
```

### Code Standards

- **Python Style**: Black formatting, PEP 8 compliance
- **Type Hints**: Full type annotation coverage
- **Documentation**: Comprehensive docstrings
- **Testing**: Unit tests for all new functionality

## 📊 Project Status

### Current Progress

- [x] Project planning and architecture design
- [x] Repository structure and packaging
- [x] Core authentication system (via add-on)
- [x] Add-on with Playwright and FastAPI
- [x] Integration cookie client
- [ ] Device discovery and control (pending API reverse engineering)
- [x] Home Assistant integration framework

### Milestones

- **v0.1.0**: Basic authentication and device discovery
- **v0.2.0**: Home Assistant integration and switch entities
- **v0.3.0**: Session management and error recovery
- **v1.0.0**: HACS release with full feature set

## ⚠️ Known Limitations

1. **No Official API**: Relies on web scraping (may break with Google updates)
2. **Add-on Required**: Requires Home Assistant OS or Supervised (not Container/Core)
3. **Single Account**: Only supports one Google account at a time
4. **Resource Usage**: Browser automation requires ~500MB RAM during authentication
5. **Performance**: Web scraping is slower than official API calls

## 📄 Licence

This project is licensed under the MIT Licence - see the [LICENSE](LICENSE) file for details.

---

**⚠️ Important**: This integration is unofficial and may violate Google's Terms of Service. Use responsibly with test accounts only. 