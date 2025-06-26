"""Constants for the Google Family Link integration."""
from __future__ import annotations

from typing import Final

# Integration constants
DOMAIN: Final = "familylink"
INTEGRATION_NAME: Final = "Google Family Link"

# Configuration
CONF_COOKIE_FILE: Final = "cookie_file"
CONF_UPDATE_INTERVAL: Final = "update_interval"
CONF_TIMEOUT: Final = "timeout"

# Default values
DEFAULT_UPDATE_INTERVAL: Final = 60  # seconds
DEFAULT_TIMEOUT: Final = 30  # seconds
DEFAULT_COOKIE_FILE: Final = "familylink_cookies.json"

# Family Link URLs
FAMILYLINK_BASE_URL: Final = "https://families.google.com"
FAMILYLINK_LOGIN_URL: Final = "https://accounts.google.com/signin"

# Browser settings
BROWSER_TIMEOUT: Final = 60000  # milliseconds
BROWSER_NAVIGATION_TIMEOUT: Final = 30000  # milliseconds

# Session management
SESSION_REFRESH_INTERVAL: Final = 86400  # 24 hours in seconds
COOKIE_EXPIRY_BUFFER: Final = 3600  # 1 hour buffer before expiry

# Device control
DEVICE_LOCK_ACTION: Final = "lock"
DEVICE_UNLOCK_ACTION: Final = "unlock"

# Error codes
ERROR_AUTH_FAILED: Final = "auth_failed"
ERROR_TIMEOUT: Final = "timeout"
ERROR_NETWORK: Final = "network_error"
ERROR_INVALID_DEVICE: Final = "invalid_device"
ERROR_SESSION_EXPIRED: Final = "session_expired"

# Logging
LOGGER_NAME: Final = f"custom_components.{DOMAIN}"

# Device attributes
ATTR_DEVICE_ID: Final = "device_id"
ATTR_DEVICE_NAME: Final = "device_name"
ATTR_DEVICE_TYPE: Final = "device_type"
ATTR_LAST_SEEN: Final = "last_seen"
ATTR_LOCKED: Final = "locked"
ATTR_BATTERY_LEVEL: Final = "battery_level"

# Service names
SERVICE_REFRESH_DEVICES: Final = "refresh_devices"
SERVICE_FORCE_UNLOCK: Final = "force_unlock"
SERVICE_EMERGENCY_UNLOCK: Final = "emergency_unlock" 