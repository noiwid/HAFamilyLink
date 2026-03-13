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

# Start VNC server for remote access
echo "Starting VNC server on port 5900..."
x11vnc -display :99 -forever -shared -rfbport 5900 -passwd "${VNC_PASSWORD}" >/dev/null 2>&1 &
echo "✓ VNC server started"
echo ""

echo "=============================================="
echo "Service Ready!"
echo "  - Web UI: http://localhost:8099"
echo "  - VNC:    vnc://localhost:5900"
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
