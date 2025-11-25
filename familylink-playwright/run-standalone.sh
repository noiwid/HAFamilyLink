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

echo "Configuration:"
echo "  - Log Level: ${LOG_LEVEL}"
echo "  - Auth Timeout: ${AUTH_TIMEOUT}s"
echo "  - Session Duration: ${SESSION_DURATION}s"
echo "  - VNC Password: ${VNC_PASSWORD}"
echo ""

# Ensure shared directory exists
mkdir -p /share/familylink
chmod 755 /share/familylink
echo "✓ Shared storage ready at /share/familylink"

# Start Xvfb (virtual display)
echo "Starting virtual display (Xvfb)..."
Xvfb :99 -screen 0 1280x1024x24 >/dev/null 2>&1 &
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
echo "✓ VNC server started (password: ${VNC_PASSWORD})"
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
