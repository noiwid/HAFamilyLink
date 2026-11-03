"""Configuration management for the add-on."""
import os
import re
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
    vnc_password: str = ""  # VNC password (mirrors add-on option; empty = generated at start)


def _safe_int(value: str, default: int) -> int:
    """Safely convert string to int with fallback."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def normalize_language(value: Optional[str]) -> str:
    """The browser locale as a BCP 47 tag: ``de_DE`` -> ``de-DE``, ``en_US.UTF-8`` -> ``en-US``.

    The value becomes the browser's Accept-Language header. With an underscore
    (``en_EN``, the POSIX spelling) that header is no longer a "simple" CORS
    header, so every cross-origin request of Google's sign-in page to
    gstatic.com needs a preflight that Google refuses: the page loads without
    its script and its buttons do nothing (issue #209).
    """
    text = (value or "").strip().split(".", 1)[0].split("@", 1)[0].replace("_", "-")
    parts = [p for p in re.split(r"-+", text) if p]
    if not parts or not all(re.fullmatch(r"[A-Za-z0-9]{1,8}", p) for p in parts):
        return "en-US"
    tag = [parts[0].lower()]
    for part in parts[1:]:
        tag.append(part.upper() if len(part) == 2 and part.isalpha() else part)
    return "-".join(tag)


def get_config() -> Config:
    """Get configuration from environment variables."""
    return Config(
        log_level=os.getenv("LOG_LEVEL", "info"),
        auth_timeout=_safe_int(os.getenv("AUTH_TIMEOUT", "300"), 300),
        session_duration=_safe_int(os.getenv("SESSION_DURATION", "86400"), 86400),
        language=normalize_language(os.getenv("LANGUAGE", "en-US")),
        timezone=os.getenv("TIMEZONE", "Europe/Paris"),
        vnc_password=os.getenv("VNC_PASSWORD", ""),
    )
