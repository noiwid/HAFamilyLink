"""Custom exceptions for the Google Family Link integration."""
from __future__ import annotations


class FamilyLinkException(Exception):
	"""Base exception for Family Link integration."""


class AuthenticationError(FamilyLinkException):
	"""Exception raised when authentication fails."""


class SessionExpiredError(FamilyLinkException):
	"""Exception raised when session has expired."""


class DeviceControlError(FamilyLinkException):
	"""Exception raised when device control operation fails."""


class NetworkError(FamilyLinkException):
	"""Exception raised when network operations fail."""


class FamilyLinkTimeoutError(FamilyLinkException):
	"""Exception raised when operations timeout."""


