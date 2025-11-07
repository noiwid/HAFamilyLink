"""Browser-based authentication manager using Playwright."""
import asyncio
import logging
import uuid
from typing import Dict, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

_LOGGER = logging.getLogger(__name__)


class BrowserAuthManager:
    """Manages browser-based authentication sessions."""

    def __init__(self, auth_timeout: int = 300):
        """Initialize browser auth manager."""
        self._sessions: Dict[str, Dict] = {}
        self._playwright = None
        self._auth_timeout = auth_timeout

    async def initialize(self):
        """Initialize Playwright."""
        try:
            self._playwright = await async_playwright().start()
            _LOGGER.info("Playwright initialized successfully")
        except Exception as e:
            _LOGGER.error(f"Failed to initialize Playwright: {e}")
            raise

    async def start_auth_session(self) -> str:
        """Start a new authentication session."""
        session_id = str(uuid.uuid4())
        _LOGGER.info(f"Starting authentication session: {session_id}")

        try:
            # Launch browser (non-headless so user can interact)
            browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )

            # Create context with realistic user agent
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale='fr-FR',
                timezone_id='Europe/Paris'
            )

            # Create page
            page = await context.new_page()

            # Store session
            self._sessions[session_id] = {
                'browser': browser,
                'context': context,
                'page': page,
                'status': 'authenticating',
                'cookies': None,
                'error': None
            }

            # Listen for new tabs/popups
            def on_page(new_page):
                _LOGGER.info(f"New tab detected, switching monitoring to new page")
                self._sessions[session_id]['page'] = new_page

            context.on("page", on_page)

            # Navigate to Google Family Link
            _LOGGER.info("Navigating to Google Family Link...")
            await page.goto('https://families.google.com', wait_until='networkidle', timeout=30000)

            # Start monitoring in background
            asyncio.create_task(self._monitor_authentication(session_id))

            return session_id

        except Exception as e:
            _LOGGER.error(f"Failed to start auth session: {e}")
            raise

    async def _monitor_authentication(self, session_id: str):
        """Monitor authentication progress."""
        session = self._sessions.get(session_id)
        if not session:
            return

        context: BrowserContext = session['context']

        try:
            _LOGGER.info(f"Monitoring authentication for session {session_id}")

            # Wait for successful login - multiple possible indicators
            # We'll wait for URL change or specific elements that indicate success
            max_wait_time = self._auth_timeout * 1000  # Convert to milliseconds

            # Wait for URL to contain "families.google.com" and not be on login page
            await asyncio.sleep(5)  # Give initial page time to load

            # Poll for authentication completion
            start_time = asyncio.get_event_loop().time()
            authenticated = False

            while (asyncio.get_event_loop().time() - start_time) < self._auth_timeout:
                # Get the current page (might have changed if new tab opened)
                page: Page = session['page']
                current_url = page.url
                _LOGGER.info(f"Checking authentication - Current URL: {current_url}")

                # Check if we're past the login page
                # Google Family Link redirects to myaccount.google.com/family after successful login
                if 'accounts.google.com' not in current_url:
                    # Check for Family Link dashboard URLs
                    if ('families.google.com' in current_url or
                        'myaccount.google.com/family' in current_url):
                        _LOGGER.info(f"✓ Authentication detected at: {current_url}")

                        # Navigate to families.google.com to ensure cookies are properly configured
                        _LOGGER.info("Navigating to families.google.com to finalize cookie configuration...")
                        try:
                            await page.goto('https://families.google.com/families/', wait_until='networkidle', timeout=15000)
                            _LOGGER.info("Successfully navigated to families.google.com")
                            # Wait a moment for any final cookie updates
                            await asyncio.sleep(2)
                        except Exception as e:
                            _LOGGER.warning(f"Failed to navigate to families.google.com: {e}")

                        authenticated = True
                        break

                await asyncio.sleep(2)  # Check every 2 seconds

            if not authenticated:
                raise asyncio.TimeoutError("Authentication timeout")

            # Extract cookies
            _LOGGER.info("Authentication detected, extracting cookies...")
            cookies = await context.cookies()

            # Filter relevant Google cookies
            google_cookies = [
                c for c in cookies
                if any(domain in c.get('domain', '') for domain in [
                    'google.com', 'families.google.com', 'accounts.google.com'
                ])
            ]

            if not google_cookies:
                raise Exception("No valid Google cookies found")

            _LOGGER.info(f"Extracted {len(google_cookies)} Google cookies")

            # Save to shared storage
            from app.storage.file_storage import SharedStorage
            storage = SharedStorage()
            await storage.save_cookies(google_cookies)

            # Update session
            session['status'] = 'completed'
            session['cookies'] = google_cookies

            _LOGGER.info(f"Authentication completed successfully for session {session_id}")

            # Close browser after a short delay
            await asyncio.sleep(2)
            await self._cleanup_session(session_id)

        except asyncio.TimeoutError:
            session['status'] = 'timeout'
            session['error'] = 'Authentication timeout - user did not complete login in time'
            _LOGGER.error(f"Authentication timeout for session {session_id}")
            await self._cleanup_session(session_id)

        except Exception as e:
            session['status'] = 'error'
            session['error'] = str(e)
            _LOGGER.error(f"Authentication error for session {session_id}: {e}")
            await self._cleanup_session(session_id)

    async def get_session_status(self, session_id: str) -> Dict:
        """Get status of authentication session."""
        session = self._sessions.get(session_id)
        if not session:
            return {'status': 'not_found'}

        return {
            'status': session['status'],
            'has_cookies': session['cookies'] is not None,
            'error': session.get('error'),
            'cookie_count': len(session['cookies']) if session['cookies'] else 0
        }

    async def _cleanup_session(self, session_id: str):
        """Clean up session resources."""
        session = self._sessions.get(session_id)
        if session:
            try:
                if session.get('page'):
                    await session['page'].close()
                if session.get('context'):
                    await session['context'].close()
                if session.get('browser'):
                    await session['browser'].close()
                _LOGGER.info(f"Cleaned up session {session_id}")
            except Exception as e:
                _LOGGER.warning(f"Cleanup error for session {session_id}: {e}")
            finally:
                # Keep session info for status checks
                session['browser'] = None
                session['context'] = None
                session['page'] = None

    async def cleanup(self):
        """Cleanup all resources."""
        _LOGGER.info("Cleaning up all sessions...")
        for session_id in list(self._sessions.keys()):
            await self._cleanup_session(session_id)

        if self._playwright:
            await self._playwright.stop()
            _LOGGER.info("Playwright stopped")
