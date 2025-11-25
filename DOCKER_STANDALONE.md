# Docker Standalone Deployment Guide

This guide explains how to use the Family Link Auth addon **without Home Assistant Supervisor** (for Home Assistant Core or Container installations).

## 🎯 Overview

The Family Link Auth addon can run as a standalone Docker container, making it compatible with:
- **Home Assistant Container** (Docker-based installation)
- **Home Assistant Core** (Python venv installation)
- **Non-Home Assistant setups** (for authentication purposes)

## 📋 Prerequisites

- Docker installed on your system
- Docker Compose (optional, but recommended)
- Network access from your Home Assistant instance to the addon container

## ⚠️ Important Note

The standalone deployment uses a **different Dockerfile** (`Dockerfile.standalone`) than the Home Assistant Supervisor addon. This is because:
- The addon version uses Home Assistant's `bashio` tools which don't work outside Supervisor
- The standalone version uses a clean Debian base and standard bash scripts
- **If you see errors about `bashio` or `s6-rc`, you're using the wrong image!**

## 🚀 Quick Start

### Option 1: Using Pre-built Image (Easiest - Recommended for v0.9.2+)

1. **Download the docker-compose file:**

```bash
mkdir familylink-auth && cd familylink-auth
curl -O https://raw.githubusercontent.com/noiwid/HAFamilyLink/main/familylink-playwright/docker-compose.standalone.yml
```

2. **Create data directory:**

```bash
mkdir -p ./data
```

3. **Start the container:**

```bash
docker-compose -f docker-compose.standalone.yml up -d
```

This will pull the pre-built `ghcr.io/noiwid/familylink-auth:standalone` image which is built specifically for standalone Docker (no bashio).

### Option 2: Build Locally (For latest development version)

1. **Clone the repository:**

```bash
git clone https://github.com/noiwid/HAFamilyLink.git
cd HAFamilyLink/familylink-playwright
```

2. **Edit docker-compose.standalone.yml** to use local build:

```yaml
# Comment out the image line:
# image: ghcr.io/noiwid/familylink-auth:standalone

# Uncomment the build lines:
build:
  context: .
  dockerfile: Dockerfile.standalone
```

3. **Create data directory and build:**

```bash
mkdir -p ./data
docker-compose -f docker-compose.standalone.yml up -d --build
```

4. **Access the web interface:**
   - Open: http://localhost:8099
   - Or use your server's IP: http://YOUR_IP:8099

5. **Authenticate with Google:**
   - Click "Start Authentication"
   - **Important**: The browser opens inside the Docker container, not on your computer
   - **You must connect via VNC** to see and interact with the browser

6. **Access via VNC (Required):**
   - VNC Server: `vnc://localhost:5900` (or `vnc://YOUR_SERVER_IP:5900`)
   - Password: `familylink`
   - Recommended VNC clients:
     - **macOS**: Built-in Screen Sharing (Finder → Go → Connect to Server) or RealVNC Viewer
     - **Windows**: TightVNC Viewer, RealVNC Viewer
     - **Linux**: Remmina, TigerVNC Viewer
   - Once connected, you'll see the Chromium browser with Google login page

### Option 3: Using Docker Run (Without Docker Compose)

```bash
# Create data directory
mkdir -p ./familylink-data

# Run the standalone container
docker run -d \
  --name familylink-auth \
  -p 8099:8099 \
  -p 5900:5900 \
  -v $(pwd)/familylink-data:/share/familylink \
  -e LOG_LEVEL=info \
  -e AUTH_TIMEOUT=300 \
  -e SESSION_DURATION=86400 \
  --restart unless-stopped \
  ghcr.io/noiwid/familylink-auth:standalone
```

**Important**: Use the `:standalone` tag, not `:latest` (which is for Home Assistant Supervisor).

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `info` | Logging level (`trace`, `debug`, `info`, `warning`, `error`) |
| `AUTH_TIMEOUT` | `300` | Authentication timeout in seconds (60-600) |
| `SESSION_DURATION` | `86400` | Cookie session duration in seconds (3600-604800) |
| `VNC_PASSWORD` | `familylink` | Password for VNC access |

### Volume Mounts

- `/share/familylink` - Stores authentication cookies and configuration
  - **Important**: This directory must be accessible by your Home Assistant instance

### Ports

- **8099/tcp** - Web interface for Google authentication
- **5900/tcp** - VNC server for browser access

## 📱 Integrating with Home Assistant

### 1. Cookie Retrieval (v0.9.4+)

Starting with v0.9.4, the integration supports **two methods** to retrieve cookies from the auth addon:

#### Option A: HTTP API (Recommended) ⭐

The addon exposes an HTTP API at `/api/cookies` that the integration can use directly. **No shared volumes needed!**

This is the simplest setup:
1. Make sure the addon is running and accessible from Home Assistant
2. The integration will automatically detect and use `http://localhost:8099/api/cookies`

**For Docker standalone**, the addon runs on a different container, so you need to configure the URL:
- During integration setup, if auto-detection fails, you'll be prompted to enter the auth server URL
- Enter: `http://<ADDON_HOST_IP>:8099` (e.g., `http://192.168.1.100:8099`)

#### Option B: Shared Volume (Fallback)

If the HTTP API is not available, the integration falls back to reading cookies from files.

The addon stores **encrypted** cookies in `/share/familylink/cookies.enc` and the encryption key in `/share/familylink/.key`.

**For Home Assistant Container:**

Mount the familylink data directory into your Home Assistant container:

```yaml
# docker-compose.yml for Home Assistant
services:
  homeassistant:
    # ... other config ...
    volumes:
      # ... other volumes ...
      - ./familylink-data:/share/familylink:ro  # Read-only access
```

**For Home Assistant Core:**

Create the directory and link/copy the files:

```bash
# Create the directory structure
sudo mkdir -p /share/familylink

# Symbolic link (recommended)
sudo ln -s /path/to/familylink-data/cookies.enc /share/familylink/cookies.enc
sudo ln -s /path/to/familylink-data/.key /share/familylink/.key
```

### 2. Integration Configuration

When setting up the Family Link integration in Home Assistant:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Google Family Link"
3. Complete the setup wizard:
   - The integration first tries to fetch cookies via HTTP API
   - If that fails, it falls back to reading from `/share/familylink/`
   - If nothing is detected, you'll be prompted to enter the auth server URL manually

## 🐳 Building Your Own Image

If you want to build the Docker image yourself:

### Build for Your Architecture

```bash
cd familylink-playwright
docker build -t familylink-auth:local .
```

### Build Multi-Architecture Image

Using the provided build script:

```bash
cd familylink-playwright
chmod +x build-docker.sh
./build-docker.sh
```

Or manually with buildx:

```bash
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t yourusername/familylink-auth:latest \
  --push \
  .
```

## 🔒 Security Considerations

1. **Cookie Security**
   - Cookies contain authentication credentials (stored encrypted in `cookies.enc`)
   - Ensure proper file permissions: `chmod 644 cookies.enc` and `chmod 644 .key`
   - Never commit cookies or encryption keys to version control
   - The `.key` file is required to decrypt cookies - keep it secure

2. **Network Security**
   - If exposing port 8099 externally, use a reverse proxy with SSL
   - Consider using a VPN for VNC access
   - Restrict access to trusted IPs

3. **VNC Password**
   - Change the default VNC password in production:
     ```yaml
     environment:
       - VNC_PASSWORD=your_secure_password
     ```

## 🛠️ Troubleshooting

### "bashio: unbound variable" or "s6-rc failed" Errors

**Symptom**: Container fails to start with errors like:
```
/usr/lib/bashio/log.sh: line 107: info: unbound variable
s6-rc: warning: unable to start service base-addon-banner: command exited 1
```

**Cause**: You're using the Home Assistant Supervisor addon image (`ghcr.io/noiwid/familylink-auth:latest`) instead of the standalone image.

**Solution**: Build the standalone image locally:

```bash
cd familylink-playwright
docker-compose -f docker-compose.standalone.yml up -d --build
```

This uses `Dockerfile.standalone` which doesn't require Home Assistant Supervisor or bashio.

### Container Won't Start (Other Reasons)

```bash
# Check logs
docker logs familylink-auth

# Check if ports are already in use
netstat -tulpn | grep -E '8099|5900'
```

### Authentication Window Not Opening

1. Connect via VNC: `vnc://localhost:5900`
2. You should see the browser automation window
3. Complete the Google authentication process manually if needed

### Cookies Not Found by Integration

**Symptom**: Integration setup fails with "No cookies found" or "Failed to load cookies from add-on"

**Diagnostic Steps**:

```bash
# 1. Check if the addon API is accessible
curl http://<ADDON_IP>:8099/api/cookies
# Should return JSON with encrypted cookies

# 2. If using file fallback, verify files exist
ls -la /path/to/familylink-data/cookies.enc
ls -la /path/to/familylink-data/.key
```

**Solution (v0.9.4+)**:

The easiest fix is to configure the auth server URL manually during integration setup:
1. Remove the existing integration (if any)
2. Add the integration again
3. When prompted (or if auto-detection fails), enter the auth server URL: `http://<ADDON_IP>:8099`

**Alternative: File-based fallback**

If you prefer using shared volumes:

```bash
# For Container: Add volume mount to docker-compose.yml
# Add this to your homeassistant service volumes:
#   - ./familylink-data:/share/familylink:ro

# Then recreate the container:
docker-compose up -d homeassistant
```

### Container Health Check Failing

```bash
# Check health status
docker inspect familylink-auth | grep -A 10 Health

# Manual health check
curl http://localhost:8099/api/health
```

## 🔄 Updating the Container

### Using Docker Compose

```bash
docker-compose pull
docker-compose up -d
```

### Using Docker Run

```bash
docker pull ghcr.io/noiwid/familylink-auth:latest
docker stop familylink-auth
docker rm familylink-auth
# Then run the docker run command again
```

## 📊 Monitoring

### View Logs

```bash
# Follow logs in real-time
docker logs -f familylink-auth

# View last 100 lines
docker logs --tail 100 familylink-auth
```

### Container Stats

```bash
docker stats familylink-auth
```

## 🌐 Advanced: Reverse Proxy Setup

### Nginx Example

```nginx
server {
    listen 443 ssl;
    server_name familylink.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8099;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Traefik Example

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.familylink.rule=Host(`familylink.example.com`)"
  - "traefik.http.routers.familylink.entrypoints=websecure"
  - "traefik.http.routers.familylink.tls.certresolver=letsencrypt"
  - "traefik.http.services.familylink.loadbalancer.server.port=8099"
```

## 📝 Complete Docker Compose Example

Here's a complete example integrating with Home Assistant Container:

```yaml
version: '3.8'

services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    network_mode: host
    volumes:
      - ./homeassistant:/config
      - /etc/localtime:/etc/localtime:ro
      - familylink-data:/share/familylink:ro
    restart: unless-stopped

  familylink-auth:
    image: ghcr.io/noiwid/familylink-auth:latest
    container_name: familylink-auth
    ports:
      - "8099:8099"
      - "5900:5900"
    volumes:
      - familylink-data:/share/familylink:rw
    environment:
      - LOG_LEVEL=info
      - AUTH_TIMEOUT=300
      - SESSION_DURATION=86400
      - VNC_PASSWORD=your_secure_password
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8099/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

volumes:
  familylink-data:
```

## ❓ FAQ

**Q: Do I need to keep the container running all the time?**
A: No, you only need it running during initial authentication and when cookies need to be refreshed (typically every few weeks).

**Q: Can I use this with Home Assistant OS?**
A: No, Home Assistant OS supports Supervisor add-ons natively. This guide is for Core/Container installations only.

**Q: How do I know when cookies need to be refreshed?**
A: The Home Assistant integration will show authentication errors. You can then restart the container and re-authenticate.

**Q: Can I run this on a different machine than Home Assistant?**
A: Yes, as long as Home Assistant can access the cookies file (via network share, manual copy, etc.).

**Q: Is arm64/aarch64 supported?**
A: Yes, the image supports both amd64 (x86_64) and arm64 (Raspberry Pi, etc.).

## 🤝 Support

For issues or questions:
- GitHub Issues: https://github.com/noiwid/HAFamilyLink/issues
- Forum Discussion: https://forum.hacf.fr/t/integration-google-family-link/69872

## 📄 License

See the main [LICENSE](LICENSE) file in the repository.
