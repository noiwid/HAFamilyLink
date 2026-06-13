#!/bin/bash
set -e

# ==============================================================================
# Start Family Link Auth Service (Standalone)
# ==============================================================================

echo "=============================================="
echo "Google Family Link Auth Service (Standalone)"
echo "=============================================="
echo ""

# Read configuration from environment variables
LOG_LEVEL="${LOG_LEVEL:-info}"
AUTH_TIMEOUT="${AUTH_TIMEOUT:-300}"
SESSION_DURATION="${SESSION_DURATION:-86400}"
VNC_PASSWORD="${VNC_PASSWORD:-familylink}"
LANGUAGE="${LANGUAGE:-en-US}"
TIMEZONE="${TIMEZONE:-Europe/Paris}"

echo "Configuration:"
echo "  - Log Level: ${LOG_LEVEL}"
echo "  - Auth Timeout: ${AUTH_TIMEOUT}s"
echo "  - Session Duration: ${SESSION_DURATION}s"
echo "  - VNC Password: [configured]"
echo "  - Language: ${LANGUAGE}"
echo "  - Timezone: ${TIMEZONE}"
echo ""

# Ensure shared directory exists
mkdir -p /share/familylink
chmod 700 /share/familylink
echo "✓ Shared storage ready at /share/familylink"

# The cookie endpoint (/api/cookies) always requires an API key. It is
# auto-generated on first start unless the API_KEY env variable is set.
if [ -n "${API_KEY:-}" ]; then
    echo "✓ Cookie API key: provided via API_KEY environment variable"
else
    echo "ℹ Cookie API key: auto-generated in /share/familylink/api_key (./data/api_key on the host)"
fi
echo "  Configure the HA integration with: http://<this-host>:8099?api_key=<key>"

# Start D-Bus system bus if not available (fixes blank screen on RPi4/ARM64)
if [ ! -S /run/dbus/system_bus_socket ]; then
    echo "Starting D-Bus system bus..."
    mkdir -p /run/dbus
    dbus-daemon --system --fork 2>/dev/null || echo "⚠ D-Bus not available (non-critical)"
fi

# Start Xvfb (virtual display)
# Using 16-bit color depth for better VM compatibility and lower memory usage
echo "Starting virtual display (Xvfb)..."
Xvfb :99 -screen 0 1280x1024x16 -ac -nolisten tcp >/dev/null 2>&1 &
export DISPLAY=:99

# Wait for Xvfb to start
sleep 2
echo "✓ Virtual display started on :99"

# Start window manager
fluxbox >/dev/null 2>&1 &
echo "✓ Window manager (fluxbox) started"

# Start VNC server (localhost only) and noVNC web interface
echo "Starting VNC server (localhost only)..."
x11vnc -display :99 -forever -shared -rfbport 5900 -localhost -passwd "${VNC_PASSWORD}" >/dev/null 2>&1 &
VNC_PID=$!
sleep 1
if kill -0 "${VNC_PID}" 2>/dev/null; then
    echo "✓ VNC server started"
else
    echo "⚠ VNC server failed to start — noVNC will not be available"
fi

echo "Starting noVNC on port 6080..."
websockify --web=/usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &
NOVNC_PID=$!
sleep 1
if kill -0 "${NOVNC_PID}" 2>/dev/null; then
    echo "✓ noVNC started"
else
    echo "⚠ noVNC (websockify) failed to start on port 6080"
fi

# Display a welcome banner on the Xvfb display so noVNC is not black
# before the user triggers the authentication flow (issue #108).
if [ -x /usr/local/bin/welcome-banner.sh ]; then
    /usr/local/bin/welcome-banner.sh || echo "⚠ Welcome banner failed to start (non-critical)"
fi
echo ""

echo "=============================================="
echo "Service Ready!"
echo "  - Web UI: http://localhost:8099"
echo "  - noVNC:  http://localhost:6080/vnc.html"
echo "=============================================="
echo ""

# Start the FastAPI application with uvicorn
cd /app || exit 1
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8099 \
    --log-level "${LOG_LEVEL}" \
    --no-access-log \
    --workers 1
