# Changelog

All notable changes to the Google Family Link Auth Add-on will be documented in this file.

## [1.0.0] - 2025-01-07

### Added
- Initial release of the add-on
- Browser-based authentication with Playwright
- FastAPI web server with user-friendly interface
- Encrypted cookie storage using Fernet (AES-128)
- Automatic session monitoring and cleanup
- Health check endpoint
- French language interface
- Comprehensive documentation
- Support for amd64 and aarch64 architectures

### Security
- Encrypted cookie storage at rest
- Restrictive file permissions (0o600)
- Isolated browser sessions
- Automatic cleanup of sensitive data

### Technical
- Based on hassio-addons/base:14.0.2
- Python 3.11 with FastAPI and Playwright
- System Chromium browser integration
- Shared storage communication with integration

---

## Future Releases

### Planned for v1.1.0
- [ ] Automatic cookie refresh
- [ ] Multi-account support
- [ ] English language toggle
- [ ] Persistent notification integration
- [ ] Advanced logging options

### Planned for v1.2.0
- [ ] Custom browser user agent
- [ ] Proxy support
- [ ] Session backup/restore
- [ ] Integration status monitoring

---

[1.0.0]: https://github.com/noiwid/HAFamilyLink/releases/tag/v1.0.0
