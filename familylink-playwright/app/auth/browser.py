"""Browser-based authentication manager using Playwright."""
import asyncio
import logging
import time
import uuid
from typing import Dict, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

_LOGGER = logging.getLogger(__name__)


class BrowserAuthManager:
    """Manages browser-based authentication sessions."""

    MAX_CONCURRENT_SESSIONS = 1

    def __init__(self, auth_timeout: int = 300, language: str = "en-US", timezone: str = "Europe/Paris", storage=None):
        """Initialize browser auth manager."""
        self._sessions: Dict[str, Dict] = {}
        self._monitor_tasks: Dict[str, asyncio.Task] = {}
        self._playwright = None
        self._auth_timeout = auth_timeout
        self._language = language
        self._timezone = timezone
        self._storage = storage  # Injected SharedStorage instance

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
        # Prune old completed sessions (prevent memory leak)
        self._prune_old_sessions()

        # Prevent concurrent sessions (memory protection, especially on RPi)
        active = [s for s in self._sessions.values() if s.get('status') == 'authenticating']
        if len(active) >= self.MAX_CONCURRENT_SESSIONS:
            raise RuntimeError("An authentication session is already in progress. Please wait or cancel it first.")

        session_id = str(uuid.uuid4())
        _LOGGER.info(f"Starting authentication session: {session_id}")

        browser = None
        context = None
        page = None
        try:
            # Launch browser (non-headless so user can interact)
            # Extensive flags for virtualized/nested VM environments (VirtualBox, VMware, etc.)
            # These prevent crashes caused by GPU acceleration and missing system services
            browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    # Sandbox settings
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    # Memory and shared memory
                    '--disable-dev-shm-usage',
                    # GPU and rendering - critical for VMs without GPU passthrough
                    '--disable-gpu',
                    '--disable-gpu-compositing',
                    '--disable-gpu-sandbox',
                    '--disable-software-rasterizer',
                    '--disable-accelerated-2d-canvas',
                    '--disable-accelerated-video-decode',
                    '--disable-accelerated-video-encode',
                    # Skia and rendering - addresses SEGV crashes in VMs
                    '--disable-skia-runtime-opts',
                    '--disable-partial-raster',
                    '--disable-zero-copy',
                    '--disable-lcd-text',
                    '--disable-font-subpixel-positioning',
                    # Consolidated disable-features flag
                    '--disable-features=VizDisplayCompositor,dbus,IsolateOrigins,site-per-process,UseSkiaRenderer,TranslateUI',
                    # System services
                    '--disable-breakpad',
                    '--disable-component-update',
                    # Anti-detection
                    '--disable-blink-features=AutomationControlled',
                    # Stability flags
                    '--disable-background-networking',
                    '--disable-default-apps',
                    '--disable-extensions',
                    '--disable-sync',
                    '--no-first-run',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-background-timer-throttling',
                    # Memory optimization
                    '--memory-pressure-off',
                    '--disable-low-res-tiling',
                    # ARM64 / RPi compatibility
                    '--ozone-platform=x11',
                ]
            )

            # Create context with realistic user agent
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1280, 'height': 800},
                locale=self._language,
                timezone_id=self._timezone
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
                'error': None,
                'created_at': time.time(),
            }

            # Listen for new tabs/popups
            def on_page(new_page):
                _LOGGER.info(f"New tab detected, switching monitoring to new page")
                self._sessions[session_id]['page'] = new_page

            context.on("page", on_page)

            # Navigate to Google Family Link
            # Using 'load' instead of 'networkidle' for better reliability
            # 'networkidle' can timeout on pages with continuous background requests
            _LOGGER.info("Navigating to Google Family Link...")
            await page.goto('https://families.google.com', wait_until='load', timeout=30000)

            # Start monitoring in background with proper error handling
            task = asyncio.create_task(self._monitor_authentication(session_id))
            task.add_done_callback(lambda t: self._on_monitor_done(session_id, t))
            self._monitor_tasks[session_id] = task

            return session_id

        except Exception as e:
            _LOGGER.error(f"Failed to start auth session: {e}")
            # Cleanup browser resources on failure to prevent leaks
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
                if browser:
                    await browser.close()
            except Exception as cleanup_err:
                _LOGGER.warning(f"Cleanup after failed session start: {cleanup_err}")
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
                            await page.goto('https://families.google.com/families/', wait_until='load', timeout=15000)
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

            # Save to shared storage (use injected instance to avoid config mismatch)
            if self._storage:
                await self._storage.save_cookies(google_cookies)
            else:
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

        except (asyncio.TimeoutError, PlaywrightTimeoutError):
            session['status'] = 'timeout'
            session['error'] = 'Authentication timeout - user did not complete login in time'
            _LOGGER.error(f"Authentication timeout for session {session_id}")
            await self._cleanup_session(session_id)

        except Exception as e:
            session['status'] = 'error'
            session['error'] = str(e)
            _LOGGER.error(f"Authentication error for session {session_id}: {e}")
            await self._cleanup_session(session_id)

    def _on_monitor_done(self, session_id: str, task: asyncio.Task):
        """Handle monitor task completion, log unhandled errors."""
        self._monitor_tasks.pop(session_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            _LOGGER.error(f"Monitor task for session {session_id} failed: {exc}")

    def _prune_old_sessions(self, max_age: int = 3600):
        """Remove completed/errored sessions older than max_age seconds."""
        now = time.time()
        to_delete = [
            sid for sid, session in self._sessions.items()
            if session.get('status') in ('completed', 'timeout', 'error', 'cleaned_up')
            and now - session.get('created_at', 0) > max_age
        ]
        for sid in to_delete:
            del self._sessions[sid]
        if to_delete:
            _LOGGER.debug(f"Pruned {len(to_delete)} old sessions")

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
                # Retain only minimal metadata, discard heavy objects
                self._sessions[session_id] = {
                    'status': session.get('status', 'cleaned_up'),
                    'created_at': session.get('created_at'),
                }

    async def cleanup(self):
        """Cleanup all resources."""
        _LOGGER.info("Cleaning up all sessions...")
        for session_id in list(self._sessions.keys()):
            await self._cleanup_session(session_id)

        if self._playwright:
            await self._playwright.stop()
            _LOGGER.info("Playwright stopped")
