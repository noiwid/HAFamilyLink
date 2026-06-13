# Changelog

All notable changes to the Google Family Link Auth Add-on will be documented in this file.

## [1.7.0] - 2026-06-12

### Security
- **`/api/cookies` now always requires an API key** — previously the endpoint served the parent's full Google session cookies to anyone on the LAN (including the supervised child's devices), allowing a complete Family Link bypass. A key is auto-generated on first start and persisted in `/share/familylink/api_key` (`./data/api_key` in standalone mode); the `API_KEY` environment variable can override it. The auth-flow endpoints (`/api/auth/*`) remain usable from the web UI without a key unless `API_KEY` is explicitly set.
- API key comparison now uses a constant-time check
- The noVNC link no longer embeds a custom `vnc_password` in the unauthenticated web page (only the documented default is auto-filled)

### Changed
- **HA OS / Supervised**: no action needed — the integration reads the key automatically from the shared directory
- **Docker standalone**: the HA integration URL must now include the key: `http://<host>:8099?api_key=<key>` (update the integration to its matching version first)

### Fixed
- Status polling no longer returns HTTP 500 after a completed session is cleaned up (web UI could previously stay stuck on "waiting")
- Encryption key generation no longer crashes on first start when `/share/familylink` does not exist yet
- Web UI now forwards `?api_key=` to protected endpoints, so setting `API_KEY` no longer breaks the authentication flow

## [1.6.1] - 2026-05-12

### Fixed
- **noVNC welcome banner** — Display a clear welcome message on the Xvfb desktop via `xterm` so users connecting to noVNC before starting the auth flow no longer see a black screen (#108)

### Changed
- Added `xterm` to the base Dockerfile dependencies (both add-on and standalone images)

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
