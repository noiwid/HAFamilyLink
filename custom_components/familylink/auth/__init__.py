"""Authentication module for Google Family Link integration."""
from __future__ import annotations

from .addon_client import AddonCookieClient
from .session import SessionManager

__all__ = ["AddonCookieClient", "SessionManager"] 