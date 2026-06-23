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


class ScheduleUpdatePartialError(FamilyLinkException):
	"""Exception raised when a multi-step schedule update partially succeeds."""

	def __init__(self, successful_updates: list[str], failed_update: str) -> None:
		"""Initialize the partial update error."""
		self.successful_updates = successful_updates
		self.failed_update = failed_update
		super().__init__(
			"Partial schedule update: completed "
			f"{', '.join(successful_updates)}; failed {failed_update}"
		)

