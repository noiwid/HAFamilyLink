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

# Start Xvfb (virtual display)
# Using 16-bit color depth for better VM compatibility and lower memory usage
bashio::log.info "Starting virtual display (Xvfb)..."
Xvfb :99 -screen 0 1280x1024x16 -ac -nolisten tcp &
export DISPLAY=:99

# Wait for Xvfb to start
sleep 2

# Start window manager
fluxbox &

# Start VNC server (localhost only) and noVNC web interface
bashio::log.info "Starting VNC server (localhost only)..."
VNC_PASSWORD=$(bashio::config 'vnc_password' 'familylink')
x11vnc -display :99 -forever -shared -rfbport 5900 -localhost -passwd "${VNC_PASSWORD}" &

bashio::log.info "Starting noVNC on port 6080..."
websockify --web=/usr/share/novnc 6080 localhost:5900 &

bashio::log.info "Starting FastAPI application..."

# Start the FastAPI application with uvicorn directly
cd /app || exit 1
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8099 \
    --log-level "${LOG_LEVEL}" \
    --no-access-log \
    --workers 1
