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


def get_config() -> Config:
    """Get configuration from environment variables."""
    return Config(
        log_level=os.getenv("LOG_LEVEL", "info"),
        auth_timeout=int(os.getenv("AUTH_TIMEOUT", "300")),
        session_duration=int(os.getenv("SESSION_DURATION", "86400")),
    )
