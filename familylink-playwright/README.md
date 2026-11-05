# Google Family Link Auth

The auth service for the [Google Family Link integration](../README.md). Home Assistant's own container cannot run a browser, so this service performs the interactive Google login in a real Chromium window (Playwright, streamed to your browser through noVNC) and serves the resulting session cookies to the integration.

It runs in two forms. On Home Assistant OS or Supervised, install it as a **Home Assistant add-on** by adding this repository to the app store. Everywhere else (Home Assistant Container or Core, any Docker host), run it as a **standalone Docker container** using the `ghcr.io/noiwid/familylink-auth:standalone` image.

> **Warning**: this project relies on unofficial, reverse-engineered Google endpoints and an automated login. Google can break it at any time, and usage may conflict with Google's Terms of Service. Use at your own risk.

## Documentation

| Document | Covers |
|---|---|
| [DOCS.md](DOCS.md) | Add-on guide: install, login flow, options, ports, cookie handoff, troubleshooting |
| [DOCKER_STANDALONE.md](../DOCKER_STANDALONE.md) | Running the standalone container: docker compose, environment variables, API key |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## License

MIT License, see [LICENSE](../LICENSE).
