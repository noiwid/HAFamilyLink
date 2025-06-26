"""Browser-based authentication for Google Family Link."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import async_playwright, Browser, Page

from homeassistant.core import HomeAssistant

from ..const import (
	BROWSER_TIMEOUT,
	BROWSER_NAVIGATION_TIMEOUT,
	FAMILYLINK_BASE_URL,
	FAMILYLINK_LOGIN_URL,
	LOGGER_NAME,
)
from ..exceptions import AuthenticationError, BrowserError, TimeoutError

_LOGGER = logging.getLogger(LOGGER_NAME)


class BrowserAuthenticator:
	"""Handle browser-based authentication for Google Family Link."""

	def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
		"""Initialize the browser authenticator."""
		self.hass = hass
		self.config = config
		self._browser: Browser | None = None
		self._page: Page | None = None

	async def async_authenticate(self) -> dict[str, Any]:
		"""Perform browser-based authentication."""
		_LOGGER.debug("Starting browser authentication")

		try:
			async with async_playwright() as playwright:
				# Launch browser
				self._browser = await playwright.chromium.launch(
					headless=False,  # Keep visible for user interaction
					args=[
						"--no-sandbox",
						"--disable-blink-features=AutomationControlled",
						"--disable-extensions",
					],
				)

				# Create new page
				self._page = await self._browser.new_page()

				# Set user agent to avoid detection
				await self._page.set_extra_http_headers({
					"User-Agent": (
						"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
						"AppleWebKit/537.36 (KHTML, like Gecko) "
						"Chrome/120.0.0.0 Safari/537.36"
					)
				})

				# Navigate to Family Link
				await self._page.goto(FAMILYLINK_BASE_URL, timeout=BROWSER_NAVIGATION_TIMEOUT)

				# Wait for user to complete authentication
				session_data = await self._wait_for_authentication()

				return session_data

		except Exception as err:
			_LOGGER.error("Browser authentication failed: %s", err)
			raise BrowserError(f"Authentication failed: {err}") from err

		finally:
			await self._cleanup()

	async def _wait_for_authentication(self) -> dict[str, Any]:
		"""Wait for user to complete authentication and extract session data."""
		_LOGGER.info("Waiting for user to complete authentication...")

		try:
			# Wait for successful login (look for Family Link dashboard)
			await self._page.wait_for_selector(
				'[data-testid="family-dashboard"]',
				timeout=BROWSER_TIMEOUT,
			)

			# Extract cookies
			cookies = await self._page.context.cookies()
			
			# Filter for relevant Google cookies
			relevant_cookies = [
				cookie for cookie in cookies
				if any(domain in cookie.get("domain", "") for domain in [
					"google.com", "families.google.com", "accounts.google.com"
				])
			]

			if not relevant_cookies:
				raise AuthenticationError("No valid authentication cookies found")

			_LOGGER.info("Authentication completed successfully")

			return {
				"cookies": relevant_cookies,
				"authenticated": True,
				"timestamp": asyncio.get_event_loop().time(),
			}

		except asyncio.TimeoutError as err:
			_LOGGER.error("Authentication timeout")
			raise TimeoutError("Authentication timeout - user did not complete login") from err

	async def _cleanup(self) -> None:
		"""Clean up browser resources."""
		try:
			if self._page:
				await self._page.close()
			if self._browser:
				await self._browser.close()
		except Exception as err:
			_LOGGER.warning("Error during browser cleanup: %s", err)

		self._page = None
		self._browser = None 