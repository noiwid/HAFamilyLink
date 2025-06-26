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

### Core Components

The integration follows a modular architecture with clear separation of concerns:

- **Authentication Manager**: Handles secure browser-based login and session management
- **Device Manager**: Manages device discovery, state tracking, and control operations
- **Cookie Manager**: Securely stores and refreshes authentication cookies
- **HTTP Client**: Handles all communication with Family Link endpoints
- **Configuration Flow**: User-friendly setup and device selection interface

### Security Model

- **No Credential Storage**: Passwords never stored in Home Assistant
- **Session-Based**: Secure cookie management with encryption at rest
- **Isolated Browser**: Sandboxed Playwright sessions for authentication
- **Automatic Cleanup**: Secure session termination on errors

## 📋 Development Plan

### Phase 1: Core Infrastructure (MVP)

**1.1 Project Structure & Foundation**
- [x] Repository setup with proper Python packaging
- [x] Home Assistant integration manifest and structure
- [ ] Logging framework with appropriate levels
- [ ] Configuration schema validation
- [ ] Error classes and exception handling

**1.2 Authentication System**
- [ ] Playwright browser automation for Google login
- [ ] 2FA flow handling (SMS, authenticator, push notifications)
- [ ] Session cookie extraction and validation
- [ ] Secure cookie storage with encryption
- [ ] Authentication state management

**1.3 Device Discovery & Control**
- [ ] Family Link web scraping for device enumeration
- [ ] Device metadata extraction (name, type, status)
- [ ] HTTP client for device control endpoints
- [ ] Lock/unlock command implementation
- [ ] Device state polling and caching

### Phase 2: Home Assistant Integration

**2.1 Configuration Flow**
- [ ] User-friendly setup wizard
- [ ] Browser authentication trigger
- [ ] Device selection and naming
- [ ] Error handling and user feedback
- [ ] Integration options and preferences

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

```python
# Core dependencies
playwright>=1.40.0           # Browser automation
aiohttp>=3.8.0              # Async HTTP client
cryptography>=3.4.8        # Cookie encryption
homeassistant>=2023.10.0    # Home Assistant core

# Development dependencies
pytest>=7.0.0               # Testing framework
pytest-asyncio>=0.21.0      # Async testing
black>=23.0.0               # Code formatting
mypy>=1.0.0                 # Type checking
```

### Directory Structure

```
custom_components/familylink/
├── __init__.py              # Integration entry point
├── manifest.json           # Integration metadata
├── config_flow.py          # Configuration UI
├── const.py                # Constants and configuration
├── coordinator.py          # Data update coordination
├── switch.py               # Switch entity implementation
├── exceptions.py           # Custom exception classes
├── auth/
│   ├── __init__.py
│   ├── browser.py          # Playwright browser management
│   ├── session.py          # Session and cookie handling
│   └── encryption.py       # Cookie encryption utilities
├── client/
│   ├── __init__.py
│   ├── api.py              # Family Link API client
│   ├── scraper.py          # Web scraping utilities
│   └── models.py           # Data models and schemas
├── utils/
│   ├── __init__.py
│   ├── helpers.py          # Common utility functions
│   └── validators.py       # Input validation
└── tests/
    ├── __init__.py
    ├── test_auth.py        # Authentication tests
    ├── test_client.py      # API client tests
    └── test_config_flow.py # Configuration flow tests
```

## 🔒 Security Considerations

- **Cookie Encryption**: All session data encrypted using Home Assistant's secret key
- **Memory Management**: Sensitive data cleared from memory after use
- **Session Isolation**: Browser sessions run in isolated containers
- **TLS Enforcement**: All communications over HTTPS

## 📦 Installation & Setup

### HACS Installation (Recommended)

1. Add this repository to HACS custom repositories
2. Install "Google Family Link" integration
3. Restart Home Assistant
4. Add integration via Settings → Devices & Services

### Configuration

1. **Add Integration**: Search for "Google Family Link" in integrations
2. **Browser Authentication**: Complete Google login in popup browser
3. **Device Selection**: Choose devices to control
4. **Finalise Setup**: Confirm configuration and test devices

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

### Development Setup

```bash
# Clone repository
git clone https://github.com/yourusername/ha-familylink.git
cd ha-familylink

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
- [ ] Core authentication system (In Progress)
- [ ] Device discovery and control
- [ ] Home Assistant integration

### Milestones

- **v0.1.0**: Basic authentication and device discovery
- **v0.2.0**: Home Assistant integration and switch entities
- **v0.3.0**: Session management and error recovery
- **v1.0.0**: HACS release with full feature set

## ⚠️ Known Limitations

1. **No Official API**: Relies on web scraping (may break with Google updates)
2. **Browser Dependency**: Requires Playwright browser installation
3. **Performance**: Web scraping is slower than API calls

## 📄 Licence

This project is licensed under the MIT Licence - see the [LICENSE](LICENSE) file for details.

---

**⚠️ Important**: This integration is unofficial and may violate Google's Terms of Service. Use responsibly with test accounts only. 