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

## 🚀 Quick Start

### Option 1: Using Docker Compose (Recommended)

1. **Download the docker-compose file:**

```bash
curl -o docker-compose.yml https://raw.githubusercontent.com/noiwid/HAFamilyLink/main/familylink-playwright/docker-compose.standalone.yml
```

2. **Create data directory:**

```bash
mkdir -p ./familylink-data
```

3. **Start the container:**

```bash
docker-compose up -d
```

4. **Access the web interface:**
   - Open: http://localhost:8099
   - Or use your server's IP: http://YOUR_IP:8099

5. **Authenticate with Google:**
   - Click "Start Authentication"
   - If the window doesn't open, connect via VNC (see below)

6. **Access via VNC (if needed):**
   - VNC Server: `vnc://localhost:5900`
   - Password: `familylink`
   - Recommended VNC clients:
     - **macOS**: Built-in Screen Sharing or RealVNC Viewer
     - **Windows**: TightVNC Viewer, RealVNC Viewer
     - **Linux**: Remmina, TigerVNC Viewer

### Option 2: Using Docker Run

```bash
docker run -d \
  --name familylink-auth \
  -p 8099:8099 \
  -p 5900:5900 \
  -v $(pwd)/familylink-data:/share/familylink \
  -e LOG_LEVEL=info \
  -e AUTH_TIMEOUT=300 \
  -e SESSION_DURATION=86400 \
  --restart unless-stopped \
  ghcr.io/noiwid/familylink-auth:latest
```

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

### 1. Cookie Path Configuration

The addon stores cookies in `/share/familylink/cookies.json`. You need to make this accessible to your Home Assistant instance.

#### For Home Assistant Container:

Mount the same volume in your Home Assistant container:

```yaml
# docker-compose.yml for Home Assistant
services:
  homeassistant:
    # ... other config ...
    volumes:
      # ... other volumes ...
      - ./familylink-data:/share/familylink:ro  # Read-only access
```

#### For Home Assistant Core:

Create a symbolic link or copy the cookies file to a location accessible by Home Assistant:

```bash
# Option A: Symbolic link
ln -s /path/to/familylink-data/cookies.json /config/familylink-cookies.json

# Option B: Automated copy (with a cron job)
cp /path/to/familylink-data/cookies.json /config/familylink-cookies.json
```

### 2. Integration Configuration

When setting up the Family Link integration in Home Assistant:

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Google Family Link"
3. When prompted for cookies:
   - **For Container**: Use `/share/familylink/cookies.json`
   - **For Core**: Use the path to your copied/linked cookies file

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
   - Cookies contain authentication credentials
   - Ensure proper file permissions: `chmod 600 cookies.json`
   - Never commit cookies to version control

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

### Container Won't Start

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

```bash
# Verify cookies file exists
ls -la /path/to/familylink-data/cookies.json

# Check file permissions
chmod 644 /path/to/familylink-data/cookies.json

# Verify JSON format
cat /path/to/familylink-data/cookies.json | python3 -m json.tool
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
