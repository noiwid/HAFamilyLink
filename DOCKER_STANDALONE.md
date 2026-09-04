# Docker Standalone Guide

How to run the Family Link auth service as a standalone Docker container, for **Home Assistant Container** or **Home Assistant Core** (no Supervisor, so no add-on store). The integration side of the setup (install, configuration flow) is covered in [INSTALL.md](INSTALL.md), Route B.

> **Warning**: this project relies on unofficial, reverse-engineered Google endpoints. There is no official API: Google can change or break it at any time. Use at your own risk.

## Prerequisites

- Docker (and ideally Docker Compose) on a machine your Home Assistant can reach.
- A Google account with Family Link configured.

## Quick start

### Option 1: Docker Compose (recommended)

Create a directory for the service, and inside it a `docker-compose.yml`:

```yaml
version: '3.8'

services:
  familylink-auth:
    image: ghcr.io/noiwid/familylink-auth:standalone
    container_name: familylink-auth
    ports:
      - "8099:8099"  # Web UI + API
      - "6080:6080"  # noVNC web interface
    volumes:
      - ./data:/share/familylink:rw
    shm_size: '2gb'  # Chromium needs more than Docker's 64MB default
    environment:
      - LOG_LEVEL=info
      - AUTH_TIMEOUT=300
      - SESSION_DURATION=86400
      - VNC_PASSWORD=familylink
      - LANGUAGE=en-US
      - TIMEZONE=Europe/Paris
      # Recommended: protect /api/cookies (see "API key" below)
      # - API_KEY=change-me
    dns:
      - 8.8.8.8
      - 8.8.4.4
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8099/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

Then start it:

```bash
docker compose up -d
```

### Option 2: Docker Run

```bash
docker run -d \
  --name familylink-auth \
  --shm-size=2gb \
  -p 8099:8099 \
  -p 6080:6080 \
  -v $(pwd)/data:/share/familylink:rw \
  -e LOG_LEVEL=info \
  -e AUTH_TIMEOUT=300 \
  -e SESSION_DURATION=86400 \
  -e VNC_PASSWORD=familylink \
  -e LANGUAGE=en-US \
  -e TIMEZONE=Europe/Paris \
  --dns 8.8.8.8 \
  --dns 8.8.4.4 \
  --restart unless-stopped \
  ghcr.io/noiwid/familylink-auth:standalone
```

Add `-e API_KEY=<your-key>` to protect the cookie endpoint (see [API key](#api-key-securing-the-cookie-endpoint)).

Both `linux/amd64` and `linux/arm64` are supported; Docker pulls the right image automatically.

## Configuration

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `info` | Logging level (`debug`, `info`, `warning`, `error`) |
| `AUTH_TIMEOUT` | `300` | Seconds you have to finish the Google login before the session times out |
| `SESSION_DURATION` | `86400` | No effect, kept for backward compatibility (cookie lifetime is decided by Google) |
| `VNC_PASSWORD` | `familylink` | Password for the noVNC web interface. VNC authentication uses at most 8 characters: longer values are truncated to the first 8, with a warning in the log. Empty disables the password |
| `LANGUAGE` | `en-US` | Browser locale for the Google login pages |
| `TIMEZONE` | `Europe/Paris` | Container and browser timezone |
| `API_KEY` | unset | Key protecting `GET /api/cookies`. When unset, the endpoint is **open** in standalone mode (a warning is logged at startup). See [API key](#api-key-securing-the-cookie-endpoint) |
| `FAMILYLINK_VNC_BACKEND` | `auto` | Display backend (image v1.8.0+): `auto` (TigerVNC, with automatic fallback to Xvfb + x11vnc), `tigervnc`, or `x11vnc` |

### Volumes

| Host path | Container path | Contents |
|---|---|---|
| `./data` | `/share/familylink` | `cookies.enc` (Fernet-encrypted Google session cookies) and `.key` (the encryption key) |

Keep this volume across container recreations so you do not have to log in to Google again after every update. Treat the directory as sensitive: together, the two files are a full Google session.

### Ports

| Port | Purpose |
|---|---|
| `8099` | Web UI and REST API (the Home Assistant integration reads `/api/cookies` here). **Never expose it to the internet** |
| `6080` | noVNC web interface, where the Google login happens. Protected by the VNC password only: keep it on a trusted network, or bind it to `127.0.0.1:6080:6080` and reach it through an SSH tunnel |

The VNC server itself (port 5900) is bound to localhost inside the container and is not exposed.

### DNS

The `dns` entries (`8.8.8.8`, `8.8.4.4`) make the container resolve Google domains directly. This matters if you run Pi-hole, AdGuard, or another local DNS that might interfere with Google services.

## Authentication

The flow uses **two ports**, in this order:

1. Open the web UI: `http://<docker-host>:8099`.
2. Click **Start Authentication**. A Chromium browser launches inside the container.
3. Open noVNC in another tab: `http://<docker-host>:6080/vnc.html`, and enter the VNC password: the `VNC_PASSWORD` environment variable if you set one, otherwise the password generated at start and printed in the container log (`docker logs familylink-auth`, line "VNC password for this start").
4. Complete the Google login and 2FA in the Chromium window shown through noVNC.
5. Wait for the success message showing how many cookies were saved, then close the noVNC tab.

To re-authenticate after the session expires, repeat the same steps; the integration picks up the new cookies automatically (see [Re-authentication](INSTALL.md#re-authentication)).

## API key (securing the cookie endpoint)

`GET /api/cookies` returns your full Google session, so anyone who can reach port 8099 could read it.

- **In standalone mode the endpoint is open by default.** The container and Home Assistant do not share a volume, so an auto-generated key could not be handed over automatically; the container logs a warning at startup instead. (On Home Assistant OS add-on installs, a key is auto-generated and shared through `/share/familylink/api_key`: nothing to configure there.)
- To lock it down, set the `API_KEY` environment variable (uncomment the line in the compose file) and recreate the container.
- Then point the integration at `http://<docker-host>:8099?api_key=<your-key>` in the configuration flow's **Manual URL** step (see [INSTALL.md](INSTALL.md#configuration-flow)). The key is accepted as an `X-API-Key` header or an `?api_key=` query parameter.
- API key or not, keep port 8099 inside your trusted network.

## Connecting to Home Assistant

Install the integration and run the configuration flow as described in [INSTALL.md, Route B](INSTALL.md#route-b-home-assistant-container-or-core), entering the container URL from the [API key](#api-key-securing-the-cookie-endpoint) section above.

## Updating

### Docker Compose

```bash
docker compose pull
docker compose up -d
```

### Docker Run

```bash
docker pull ghcr.io/noiwid/familylink-auth:standalone
docker stop familylink-auth
docker rm familylink-auth
# Re-run the docker run command above
```

Your Google login survives updates as long as the `./data` volume is kept. Version history is in the [auth service changelog](familylink-playwright/CHANGELOG.md).

## Troubleshooting

### Container won't start

- Make sure `shm_size` is at least `2gb` (Chromium needs the shared memory).
- Check the logs: `docker logs familylink-auth`.

### Cannot access noVNC

- Verify port `6080` is not blocked by a firewall, and try `http://<docker-host>:6080` directly.
- If the VNC password is refused, check the `VNC_PASSWORD` notes in the [environment variables](#environment-variables) table.
- For display-stack failures, check `docker logs familylink-auth` and the files in `/var/log/familylink/` inside the container (`docker exec familylink-auth ls /var/log/familylink`).

### Integration cannot connect

- Ensure the container is running: `docker ps | grep familylink`.
- Check the health endpoint: `curl http://<docker-host>:8099/api/health`.
- An HTTP 403 on the cookies endpoint means `API_KEY` is set but the integration URL lacks `?api_key=<key>`.
- Verify Home Assistant can reach the Docker host on port `8099`.

### DNS issues (Pi-hole, AdGuard, etc.)

- The `dns` entries in the compose file bypass local DNS for the container.
- If problems persist, try `network_mode: host` (you lose port mapping).

## Image tags

| Tag | Description |
|---|---|
| `standalone` | Latest standalone image |
| `<version>-standalone` | Standalone image as of repository release `v<version>`, e.g. `1.2.13-standalone` |
| `latest` | Latest add-on image (for HA OS/Supervised only) |
| `<version>` | Add-on image as of repository release `v<version>` |

Versioned tags follow the repository's release tag (the integration version), not the add-on version shown in the add-on store.
