# Changelog

All notable changes to the Google Family Link Auth Add-on will be documented in this file.

## [1.6.0] - 2025-03

### Added
- **noVNC web-based access** — Replace external VNC client requirement with browser-based access via noVNC on port 6080
- **Auto-detection of language and timezone** — Reads HA settings via Supervisor API when add-on options are left empty
- **Bilingual web UI (FR/EN)** — New `translations.py` module with French and English support, auto-switching based on language setting
- **DNS configuration** — Added Google DNS (8.8.8.8, 8.8.4.4) to docker-compose for Pi-hole compatibility

### Changed
- x11vnc now restricted to localhost only (no external raw VNC access)
- websockify bridges localhost VNC to noVNC on port 6080
- Exposed port changed from 5900 (VNC) to 6080 (noVNC)
- Default language/timezone options changed to empty strings for auto-detection
- Web UI HTML fully templated with i18n support (no more hardcoded French strings)

### Credits
- noVNC migration inspired by [@jnctech's fork](https://github.com/jnctech/HAFamilyLink)

---

## [1.3.0] - 2025-01-25

### Added
- HTTP API endpoint for cookie retrieval (`/api/cookies`)
- Support for Docker standalone installations without shared volumes
- Automatic detection of authentication source (API, local URL, or file fallback)

### Changed
- Integration now tries HTTP API first, then falls back to file storage
- Improved config flow with manual URL input option

### Fixed
- Docker standalone users can now configure the auth server URL manually

---

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
- [x] English language toggle *(done in v1.6.0)*
- [ ] Persistent notification integration
- [ ] Advanced logging options

### Planned for v1.2.0
- [ ] Custom browser user agent
- [ ] Proxy support
- [ ] Session backup/restore
- [ ] Integration status monitoring

---

[1.3.0]: https://github.com/noiwid/HAFamilyLink/releases/tag/v1.3.0
[1.0.0]: https://github.com/noiwid/HAFamilyLink/releases/tag/v1.0.0
