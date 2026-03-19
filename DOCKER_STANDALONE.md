# Docker Standalone Guide

This guide explains how to run the Family Link Auth service as a standalone Docker container, for users running **Home Assistant Core** or **Home Assistant Container** (i.e. without Supervisor).

## Prerequisites

- Docker and Docker Compose installed on your system
- Home Assistant Core or Container running and accessible on your network
- A Google account with Family Link configured

## Quick Start

### Option 1: Docker Compose (Recommended)

1. Create a directory for the service:

```bash
mkdir familylink-auth && cd familylink-auth
```

2. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  familylink-auth:
    image: ghcr.io/noiwid/familylink-auth:standalone
    container_name: familylink-auth
    ports:
      - "8099:8099"  # API
      - "6080:6080"  # noVNC web interface
    volumes:
      - ./data:/share/familylink:rw
    shm_size: '2gb'
    environment:
      - LOG_LEVEL=info
      - AUTH_TIMEOUT=300
      - SESSION_DURATION=86400
      - VNC_PASSWORD=familylink
      - LANGUAGE=en-US
      - TIMEZONE=Europe/Paris
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

3. Start the container:

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

## Supported Architectures

Both `linux/amd64` and `linux/arm64` are supported. Docker will automatically pull the correct image for your platform.

## Configuration

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `info` | Logging level (`debug`, `info`, `warning`, `error`) |
| `AUTH_TIMEOUT` | `300` | Authentication timeout in seconds |
| `SESSION_DURATION` | `86400` | Session duration in seconds (default 24h) |
| `VNC_PASSWORD` | `familylink` | Password for the noVNC web interface |
| `LANGUAGE` | `en-US` | Browser language for Google login pages |
| `TIMEZONE` | `Europe/Paris` | Container timezone |

### Ports

| Port | Description |
|---|---|
| `8099` | API endpoint (used by the HA integration) |
| `6080` | noVNC web interface (used for Google login) |

### DNS Configuration

The `dns` entries (`8.8.8.8`, `8.8.4.4`) ensure the container can resolve Google domains correctly. This is especially important if you use Pi-hole or another local DNS that might interfere with Google services.

## Authentication

1. Open the noVNC interface at `http://<your-docker-host>:6080`
2. Enter the VNC password (default: `familylink`)
3. Complete the Google login in the browser window
4. Once authenticated, cookies are saved and the API becomes available

## Connecting to Home Assistant

1. Install the **Family Link** integration in Home Assistant (via HACS or manually)
2. Go to **Settings > Devices & Services > Add Integration > Family Link**
3. Select **"Manual URL configuration"**
4. Enter the auth server URL: `http://<your-docker-host>:8099`
5. The integration will connect to the standalone container and retrieve authentication cookies

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

## Troubleshooting

### Container won't start
- Ensure `shm_size` is set to at least `2gb` (Chromium needs shared memory)
- Check logs: `docker logs familylink-auth`

### Cannot access noVNC
- Verify port `6080` is not blocked by a firewall
- Try accessing `http://<your-docker-host>:6080` in your browser

### Integration cannot connect
- Ensure the container is running: `docker ps | grep familylink`
- Check the health endpoint: `curl http://<your-docker-host>:8099/api/health`
- Verify Home Assistant can reach the Docker host on port `8099`

### DNS issues (Pi-hole, AdGuard, etc.)
- The `dns` configuration in the compose file bypasses local DNS for the container
- If you still have issues, try adding `network_mode: host` (but you'll lose port mapping)

## Image Tags

| Tag | Description |
|---|---|
| `standalone` | Latest standalone image |
| `<version>-standalone` | Specific version (e.g. `1.2.2-standalone`) |
| `latest` | Latest add-on image (for HA OS/Supervised only) |
| `<version>` | Specific add-on version |
