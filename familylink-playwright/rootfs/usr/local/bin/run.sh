#!/usr/bin/with-contenv bashio
# ==============================================================================
# Start Family Link Auth Service
# ==============================================================================

bashio::log.info "Starting Google Family Link Auth Service..."

# Read configuration from Home Assistant
LOG_LEVEL=$(bashio::config 'log_level' 'info')
AUTH_TIMEOUT=$(bashio::config 'auth_timeout' '300')
SESSION_DURATION=$(bashio::config 'session_duration' '86400')

# Export environment variables
export LOG_LEVEL="${LOG_LEVEL}"
export AUTH_TIMEOUT="${AUTH_TIMEOUT}"
export SESSION_DURATION="${SESSION_DURATION}"

bashio::log.info "Configuration loaded:"
bashio::log.info "  - Log Level: ${LOG_LEVEL}"
bashio::log.info "  - Auth Timeout: ${AUTH_TIMEOUT}s"
bashio::log.info "  - Session Duration: ${SESSION_DURATION}s"

# Ensure shared directory exists
mkdir -p /share/familylink
chmod 700 /share/familylink

bashio::log.info "Shared storage ready at /share/familylink"

# Set Playwright to use system Chromium
export PLAYWRIGHT_BROWSERS_PATH=/usr/bin
export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

bashio::log.info "Starting FastAPI application..."

# Start the FastAPI application with uvicorn directly
cd /app || exit 1
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8099 \
    --log-level "${LOG_LEVEL}" \
    --no-access-log \
    --workers 1
