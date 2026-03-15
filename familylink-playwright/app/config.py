"""Configuration management for the add-on."""
import os
from typing import Optional
from pydantic import BaseModel


class Config(BaseModel):
    """Application configuration."""

    log_level: str = "info"
    auth_timeout: int = 300
    session_duration: int = 86400
    host: str = "0.0.0.0"
    port: int = 8099

    # Paths
    share_dir: str = "/share/familylink"
    cookie_file: str = "cookies.enc"
    key_file: str = ".key"

    # Browser settings
    browser_timeout: int = 300000  # 5 minutes in milliseconds
    browser_navigation_timeout: int = 30000  # 30 seconds
    language: str = "en-US"  # Browser locale (e.g., fr-FR, en-GB, de-DE)
    timezone: str = "Europe/Paris"  # Browser timezone (e.g., America/New_York)


def _safe_int(value: str, default: int) -> int:
    """Safely convert string to int with fallback."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_config() -> Config:
    """Get configuration from environment variables."""
    return Config(
        log_level=os.getenv("LOG_LEVEL", "info"),
        auth_timeout=_safe_int(os.getenv("AUTH_TIMEOUT", "300"), 300),
        session_duration=_safe_int(os.getenv("SESSION_DURATION", "86400"), 86400),
        language=os.getenv("LANGUAGE", "en-US"),
        timezone=os.getenv("TIMEZONE", "Europe/Paris"),
    )
