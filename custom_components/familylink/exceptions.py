"""Custom exceptions for the Google Family Link integration."""
from __future__ import annotations


class FamilyLinkException(Exception):
	"""Base exception for Family Link integration."""


class AuthenticationError(FamilyLinkException):
	"""Exception raised when authentication fails."""


class SessionExpiredError(FamilyLinkException):
	"""Exception raised when session has expired."""


class DeviceNotFoundError(FamilyLinkException):
	"""Exception raised when a device cannot be found."""


class DeviceControlError(FamilyLinkException):
	"""Exception raised when device control operation fails."""


class NetworkError(FamilyLinkException):
	"""Exception raised when network operations fail."""


class TimeoutError(FamilyLinkException):
	"""Exception raised when operations timeout."""


class ConfigurationError(FamilyLinkException):
	"""Exception raised when configuration is invalid."""


class BrowserError(FamilyLinkException):
	"""Exception raised when browser automation fails."""


class CookieError(FamilyLinkException):
	"""Exception raised when cookie operations fail."""


class ValidationError(FamilyLinkException):
	"""Exception raised when data validation fails.""" 