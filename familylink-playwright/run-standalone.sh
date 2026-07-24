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

# The display stack (Xvfb + fluxbox + x11vnc + websockify) is logged to
# /var/log/familylink so a crash is diagnosable in `docker logs`/that file
# instead of vanishing into /dev/null (issue #136). Each process is also
# re-checked after a short delay: kill -0 right after launch only catches an
# instant failure, and x11vnc's known crash happens later, when a VNC client
# first connects — so we still tail the log on that path.
LOG_DIR="/var/log/familylink"
mkdir -p "${LOG_DIR}"

# Remove a stale X99 socket/lock left by a previous non-graceful stop (e.g.
# `docker restart`). If they survive, `Xvfb :99` silently refuses to bind and
# the whole display stack dies invisibly, leaving only uvicorn up (issue #136).
if [ -e /tmp/.X99-lock ] || [ -e /tmp/.X11-unix/X99 ]; then
    echo "Cleaning stale X99 lock/socket from a previous run..."
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
fi

# x11vnc's -passwd uses DES and silently keeps only the first 8 chars; a longer
# password would then never authenticate. The VNC server is localhost-only and
# reached through websockify, so truncate explicitly and warn rather than let
# the mismatch fail silently (issue #136). TigerVNC's VNC-auth has the same
# 8-char limit, so this applies to both display backends below.
if [ "${#VNC_PASSWORD}" -gt 8 ]; then
    echo "⚠ VNC password longer than 8 chars; VNC DES auth uses only the first 8."
    VNC_PASSWORD="${VNC_PASSWORD:0:8}"
fi

export DISPLAY=:99

# The display server is started in one of two ways (issue #136):
#
#   1. TigerVNC's Xvnc — an X server that speaks the RFB (VNC) protocol
#      natively. fluxbox and Chromium render straight into it; websockify
#      bridges it to noVNC. There is no Xvfb and no x11vnc screen-scraper, which
#      removes the exact component that crashed on client-connect (x11vnc 0.9.16
#      dropping its X connection). This is the preferred path.
#
#   2. Legacy Xvfb + x11vnc — kept as an automatic fallback for environments
#      where Xvnc is unavailable or fails to start, so we degrade instead of
#      losing VNC entirely.
#
# Set FAMILYLINK_VNC_BACKEND=x11vnc to force the legacy path.
VNC_BACKEND="${FAMILYLINK_VNC_BACKEND:-auto}"
DISPLAY_STARTED=""

start_tigervnc() {
    command -v Xvnc >/dev/null 2>&1 || { echo "  Xvnc not installed"; return 1; }

    # Build a TigerVNC password file (VNC-auth) unless empty -> no auth.
    # vncpasswd -f is filter mode: it reads the plaintext password from stdin
    # and writes the encrypted file to stdout, which is deterministic and needs
    # no interactive prompts.
    local sec_args
    if [ -n "${VNC_PASSWORD}" ] && command -v vncpasswd >/dev/null 2>&1; then
        mkdir -p /root/.vnc
        if printf '%s' "${VNC_PASSWORD}" | vncpasswd -f >/root/.vnc/passwd 2>>"${LOG_DIR}/xvnc.log" \
            && [ -s /root/.vnc/passwd ]; then
            chmod 600 /root/.vnc/passwd 2>/dev/null || true
            sec_args=(-SecurityTypes VncAuth -rfbauth /root/.vnc/passwd)
        else
            echo "⚠ vncpasswd failed; starting TigerVNC without a password (localhost only)."
            sec_args=(-SecurityTypes None)
        fi
    else
        sec_args=(-SecurityTypes None)
    fi

    echo "Starting display server (TigerVNC Xvnc on :99)..."
    Xvnc :99 -geometry 1280x1024 -depth 24 -rfbport 5900 -localhost \
        -desktop familylink "${sec_args[@]}" \
        >"${LOG_DIR}/xvnc.log" 2>&1 &
    XVNC_PID=$!
    sleep 2
    if kill -0 "${XVNC_PID}" 2>/dev/null; then
        echo "✓ TigerVNC display server started (log: ${LOG_DIR}/xvnc.log)"
        return 0
    fi
    echo "⚠ TigerVNC failed to start. Last log lines:"
    tail -n 20 "${LOG_DIR}/xvnc.log" 2>/dev/null | sed 's/^/    xvnc| /'
    return 1
}

start_xvfb_x11vnc() {
    # A failed TigerVNC attempt can leave :99 state behind, which would block
    # Xvfb from binding; clear it before falling back.
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
    echo "Starting virtual display (Xvfb)..."
    Xvfb :99 -screen 0 1280x1024x16 -ac -nolisten tcp >"${LOG_DIR}/xvfb.log" 2>&1 &
    XVFB_PID=$!
    sleep 2
    if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
        echo "⚠ Xvfb failed to start — VNC will be unavailable. Last log lines:"
        tail -n 20 "${LOG_DIR}/xvfb.log" 2>/dev/null | sed 's/^/    xvfb| /'
        return 1
    fi
    echo "✓ Virtual display started on :99"

    echo "Starting VNC server (x11vnc, localhost only)..."
    local pw_args
    if [ -n "${VNC_PASSWORD}" ]; then
        pw_args=(-passwd "${VNC_PASSWORD}")
    else
        pw_args=(-nopw)
    fi
    x11vnc -display :99 -forever -shared -rfbport 5900 -localhost "${pw_args[@]}" \
        >"${LOG_DIR}/x11vnc.log" 2>&1 &
    VNC_PID=$!
    sleep 1
    if ! kill -0 "${VNC_PID}" 2>/dev/null; then
        echo "⚠ x11vnc failed to start — noVNC will not be available. Last log lines:"
        tail -n 20 "${LOG_DIR}/x11vnc.log" 2>/dev/null | sed 's/^/    x11vnc| /'
        return 1
    fi
    echo "✓ VNC server started (log: ${LOG_DIR}/x11vnc.log)"
    return 0
}

if [ "${VNC_BACKEND}" = "x11vnc" ]; then
    start_xvfb_x11vnc && DISPLAY_STARTED="x11vnc"
elif [ "${VNC_BACKEND}" = "tigervnc" ]; then
    start_tigervnc && DISPLAY_STARTED="tigervnc"
else
    # auto: prefer TigerVNC, fall back to the legacy stack.
    if start_tigervnc; then
        DISPLAY_STARTED="tigervnc"
    else
        echo "Falling back to legacy Xvfb + x11vnc display stack..."
        start_xvfb_x11vnc && DISPLAY_STARTED="x11vnc"
    fi
fi

if [ -z "${DISPLAY_STARTED}" ]; then
    echo "⚠ No display server could be started — noVNC will not be available."
fi

# Start window manager on whichever display server came up
fluxbox >"${LOG_DIR}/fluxbox.log" 2>&1 &
FLUXBOX_PID=$!
sleep 1
if kill -0 "${FLUXBOX_PID}" 2>/dev/null; then
    echo "✓ Window manager (fluxbox) started"
else
    echo "⚠ fluxbox failed to start (non-critical). Last log lines:"
    tail -n 20 "${LOG_DIR}/fluxbox.log" 2>/dev/null | sed 's/^/    fluxbox| /'
fi

echo "Starting noVNC on port 6080..."
websockify --web=/usr/share/novnc 6080 localhost:5900 >"${LOG_DIR}/websockify.log" 2>&1 &
NOVNC_PID=$!
sleep 1
if kill -0 "${NOVNC_PID}" 2>/dev/null; then
    echo "✓ noVNC started"
else
    echo "⚠ noVNC (websockify) failed to start on port 6080. Last log lines:"
    tail -n 20 "${LOG_DIR}/websockify.log" 2>/dev/null | sed 's/^/    novnc| /'
fi

# Display a welcome banner on the virtual display so noVNC is not black
# before the user triggers the authentication flow (issue #108).
if [ -n "${DISPLAY_STARTED}" ] && [ -x /usr/local/bin/welcome-banner.sh ]; then
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
