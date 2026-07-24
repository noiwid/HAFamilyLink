#!/usr/bin/with-contenv bashio
# ==============================================================================
# Start Family Link Auth Service
# ==============================================================================

bashio::log.info "Starting Google Family Link Auth Service..."

# Read configuration from Home Assistant
LOG_LEVEL=$(bashio::config 'log_level' 'info')
AUTH_TIMEOUT=$(bashio::config 'auth_timeout' '300')
SESSION_DURATION=$(bashio::config 'session_duration' '86400')
LANGUAGE=$(bashio::config 'language' '')
TIMEZONE=$(bashio::config 'timezone' '')

# Auto-detect from Home Assistant if not manually configured
if [ -z "${LANGUAGE}" ] || [ "${LANGUAGE}" == "null" ]; then
    bashio::log.info "Language not configured, auto-detecting from Home Assistant..."
    HA_LANGUAGE=$(bashio::api.supervisor GET /core/api/config false '$.language' 2>/dev/null) || HA_LANGUAGE=""
    if [ -n "${HA_LANGUAGE}" ] && [ "${HA_LANGUAGE}" != "null" ]; then
        # Map HA short language code to full locale
        case "${HA_LANGUAGE}" in
            fr) LANGUAGE="fr-FR" ;;
            en) LANGUAGE="en-US" ;;
            de) LANGUAGE="de-DE" ;;
            es) LANGUAGE="es-ES" ;;
            it) LANGUAGE="it-IT" ;;
            nl) LANGUAGE="nl-NL" ;;
            pt) LANGUAGE="pt-PT" ;;
            *) LANGUAGE="${HA_LANGUAGE}" ;;
        esac
        bashio::log.info "Auto-detected language from HA: ${LANGUAGE}"
    else
        LANGUAGE="en-US"
        bashio::log.warning "Could not auto-detect language, defaulting to en-US"
    fi
fi

if [ -z "${TIMEZONE}" ] || [ "${TIMEZONE}" == "null" ]; then
    bashio::log.info "Timezone not configured, auto-detecting from Home Assistant..."
    HA_TIMEZONE=$(bashio::info.timezone 2>/dev/null) || HA_TIMEZONE=""
    if [ -n "${HA_TIMEZONE}" ] && [ "${HA_TIMEZONE}" != "null" ]; then
        TIMEZONE="${HA_TIMEZONE}"
        bashio::log.info "Auto-detected timezone from HA: ${TIMEZONE}"
    else
        TIMEZONE="Europe/Paris"
        bashio::log.warning "Could not auto-detect timezone, defaulting to Europe/Paris"
    fi
fi

# Export environment variables
export LOG_LEVEL="${LOG_LEVEL}"
export AUTH_TIMEOUT="${AUTH_TIMEOUT}"
export SESSION_DURATION="${SESSION_DURATION}"
export LANGUAGE="${LANGUAGE}"
export TIMEZONE="${TIMEZONE}"
# Mark this as a Supervisor-managed add-on run so the app enforces the
# cookie API key (the HA integration reads it from the shared /share dir).
export ADDON_MODE=1

bashio::log.info "Configuration loaded:"
bashio::log.info "  - Log Level: ${LOG_LEVEL}"
bashio::log.info "  - Auth Timeout: ${AUTH_TIMEOUT}s"
bashio::log.info "  - Session Duration: ${SESSION_DURATION}s"
bashio::log.info "  - Language: ${LANGUAGE}"
bashio::log.info "  - Timezone: ${TIMEZONE}"

# Ensure shared directory exists
mkdir -p /share/familylink
chmod 700 /share/familylink

bashio::log.info "Shared storage ready at /share/familylink"

# Start D-Bus system bus if not available (fixes blank screen on RPi4/ARM64)
if [ ! -S /run/dbus/system_bus_socket ]; then
    bashio::log.info "Starting D-Bus system bus..."
    mkdir -p /run/dbus
    dbus-daemon --system --fork 2>/dev/null || bashio::log.warning "D-Bus not available (non-critical)"
fi

# Remove a stale X99 socket/lock left by a previous non-graceful stop (e.g. an
# add-on restart). If they survive, `Xvfb :99` silently refuses to bind and the
# whole display stack dies invisibly, leaving only uvicorn up (issue #136).
if [ -e /tmp/.X99-lock ] || [ -e /tmp/.X11-unix/X99 ]; then
    bashio::log.info "Cleaning stale X99 lock/socket from a previous run..."
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
fi

export DISPLAY=:99

# VNC-auth (both x11vnc's -passwd and TigerVNC's VncAuth) uses DES and silently
# keeps only the first 8 chars; a longer password would then never
# authenticate. The server is localhost-only and reached through websockify, so
# truncate explicitly and warn rather than let the mismatch fail silently
# (issue #136).
VNC_PASSWORD=$(bashio::config 'vnc_password' 'familylink')
if [ "${#VNC_PASSWORD}" -gt 8 ]; then
    bashio::log.warning "VNC password longer than 8 chars; VNC DES auth uses only the first 8"
    VNC_PASSWORD="${VNC_PASSWORD:0:8}"
fi
# Expose to the FastAPI app so the web UI can adapt the noVNC link/hint
export VNC_PASSWORD="${VNC_PASSWORD}"

# The display server is started in one of two ways (issue #136):
#
#   1. TigerVNC's Xvnc — an X server that speaks the RFB (VNC) protocol
#      natively, so there is no Xvfb and no x11vnc screen-scraper. This removes
#      the exact component that crashed on client-connect (x11vnc 0.9.16
#      dropping its X connection). Preferred.
#   2. Legacy Xvfb + x11vnc — kept as an automatic fallback so we degrade
#      instead of losing VNC entirely where Xvnc is unavailable.
#
# Set FAMILYLINK_VNC_BACKEND=x11vnc (or tigervnc) to force a backend.
VNC_BACKEND="${FAMILYLINK_VNC_BACKEND:-auto}"
DISPLAY_STARTED=""

start_tigervnc() {
    command -v Xvnc >/dev/null 2>&1 || { bashio::log.info "Xvnc not installed"; return 1; }

    # vncpasswd -f is filter mode: reads the plaintext password from stdin and
    # writes the encrypted file to stdout, so no interactive prompts are needed.
    local sec_args
    if [ -n "${VNC_PASSWORD}" ] && command -v vncpasswd >/dev/null 2>&1; then
        mkdir -p /root/.vnc
        if printf '%s' "${VNC_PASSWORD}" | vncpasswd -f >/root/.vnc/passwd 2>/dev/null \
            && [ -s /root/.vnc/passwd ]; then
            chmod 600 /root/.vnc/passwd 2>/dev/null || true
            sec_args=(-SecurityTypes VncAuth -rfbauth /root/.vnc/passwd)
        else
            bashio::log.warning "vncpasswd failed; starting TigerVNC without a password (localhost only)"
            sec_args=(-SecurityTypes None)
        fi
    else
        sec_args=(-SecurityTypes None)
    fi

    bashio::log.info "Starting display server (TigerVNC Xvnc on :99)..."
    Xvnc :99 -geometry 1280x1024 -depth 24 -rfbport 5900 -localhost \
        -desktop familylink "${sec_args[@]}" &
    XVNC_PID=$!
    sleep 2
    if kill -0 "${XVNC_PID}" 2>/dev/null; then
        bashio::log.info "TigerVNC display server started"
        return 0
    fi
    bashio::log.warning "TigerVNC failed to start (see log above)"
    return 1
}

start_xvfb_x11vnc() {
    # A failed TigerVNC attempt can leave :99 state behind, which would block
    # Xvfb from binding; clear it before falling back.
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true
    bashio::log.info "Starting virtual display (Xvfb)..."
    Xvfb :99 -screen 0 1280x1024x16 -ac -nolisten tcp &
    XVFB_PID=$!
    sleep 2
    if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
        bashio::log.warning "Xvfb failed to start — VNC will be unavailable (see log above)"
        return 1
    fi

    bashio::log.info "Starting VNC server (x11vnc, localhost only)..."
    local pw_args
    if [ -n "${VNC_PASSWORD}" ]; then
        pw_args=(-passwd "${VNC_PASSWORD}")
    else
        pw_args=(-nopw)
    fi
    x11vnc -display :99 -forever -shared -rfbport 5900 -localhost "${pw_args[@]}" &
    VNC_PID=$!
    sleep 1
    if ! kill -0 "${VNC_PID}" 2>/dev/null; then
        bashio::log.warning "x11vnc failed to start — noVNC will not be available"
        return 1
    fi
    return 0
}

if [ "${VNC_BACKEND}" = "x11vnc" ]; then
    start_xvfb_x11vnc && DISPLAY_STARTED="x11vnc"
elif [ "${VNC_BACKEND}" = "tigervnc" ]; then
    start_tigervnc && DISPLAY_STARTED="tigervnc"
else
    if start_tigervnc; then
        DISPLAY_STARTED="tigervnc"
    else
        bashio::log.info "Falling back to legacy Xvfb + x11vnc display stack..."
        start_xvfb_x11vnc && DISPLAY_STARTED="x11vnc"
    fi
fi

if [ -z "${DISPLAY_STARTED}" ]; then
    bashio::log.warning "No display server could be started — noVNC will not be available"
fi

# Start window manager on whichever display server came up
fluxbox &
FLUXBOX_PID=$!
sleep 1
if ! kill -0 "${FLUXBOX_PID}" 2>/dev/null; then
    bashio::log.warning "fluxbox failed to start (non-critical, see log above)"
fi

bashio::log.info "Starting noVNC on port 6080..."
websockify --web=/usr/share/novnc 6080 localhost:5900 &
NOVNC_PID=$!
sleep 1
if ! kill -0 "${NOVNC_PID}" 2>/dev/null; then
    bashio::log.warning "websockify/noVNC failed to start on port 6080"
fi

# Display a welcome banner on the virtual display so noVNC is not black
# before the user triggers the authentication flow (issue #108).
if [ -n "${DISPLAY_STARTED}" ] && [ -x /usr/local/bin/welcome-banner.sh ]; then
    /usr/local/bin/welcome-banner.sh || bashio::log.warning "Welcome banner failed to start (non-critical)"
fi

bashio::log.info "Starting FastAPI application..."

# Start the FastAPI application with uvicorn directly
cd /app || exit 1
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8099 \
    --log-level "${LOG_LEVEL}" \
    --no-access-log \
    --workers 1
