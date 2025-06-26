"""Authentication module for Google Family Link integration."""
from __future__ import annotations

from .browser import BrowserAuthenticator
from .session import SessionManager

__all__ = ["BrowserAuthenticator", "SessionManager"] 