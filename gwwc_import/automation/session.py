"""GWWC dashboard session management via Playwright.

Handles browser launch, cookie-consent dismissal, email/password login,
and storage_state persistence so subsequent runs skip the login form.

Phase 4 form selectors (for reference):
  - Recipient org:  page.get_by_role("combobox", name="Recipient organisation")
  - Currency:       page.get_by_role("combobox", name="Currency")
  - Amount:         page.get_by_role("textbox", name="Amount")
  - Donation date:  page.get_by_role("textbox", name="Donation date")  # YYYY-MM-DD
  - One-time radio: page.get_by_role("radio", name="One-time")
  - Recurring radio:page.get_by_role("radio", name="Recurring")
  - Income period:  page.get_by_role("combobox", name="Income period")
  - Save button:    page.get_by_role("button", name="Save")
  - Form URL:       /dashboard/pledge/donations?report=true&mode=manual
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    expect,
    sync_playwright,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

_DONATIONS_URL = "https://www.givingwhatwecan.org/dashboard/pledge/donations"
_DEFAULT_SESSION_FILE = Path("~/.gwwc_import_session.json")

log = logging.getLogger(__name__)


class SessionError(Exception):
    """Raised when login or session management fails."""


class GWWCSession:
    """Playwright browser session for the GWWC dashboard.

    Usage::

        with GWWCSession.from_env() as session:
            session.ensure_logged_in()
            page = session.get_page()
    """

    def __init__(
        self,
        email: str,
        password: str,
        session_file: Path,
        headless: bool = True,
    ) -> None:
        self.email = email
        self.password = password
        self.session_file = session_file.expanduser()
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> GWWCSession:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch browser and restore session from disk if available."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        if self.session_file.exists():
            log.debug("Restoring session from %s", self.session_file)
            storage = json.loads(self.session_file.read_text())
            self._context = self._browser.new_context(storage_state=storage)
        else:
            self._context = self._browser.new_context()
        self._page = self._context.new_page()

    def close(self) -> None:
        """Close browser and stop Playwright."""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def ensure_logged_in(self) -> None:
        """Navigate to the donations dashboard; login with email/password if needed.

        Persists the resulting session to disk so the next run is credential-free.
        """
        page = self._require_page()
        page.goto(_DONATIONS_URL)

        # Cookie consent banner appears before the login dialog becomes active.
        try:
            page.get_by_role("button", name="Accept all").click(timeout=4_000)
            log.debug("Cookie consent accepted.")
        except PlaywrightTimeoutError:
            pass  # consent banner not present or already accepted

        if page.get_by_role("dialog").filter(has_text="Welcome back").is_visible():
            log.info("Session unauthenticated — logging in.")
            self._login(page)
        else:
            log.debug("Session already authenticated.")

        if "/dashboard/" not in page.url:
            raise SessionError(f"Login did not reach dashboard — got: {page.url}")

        self._save_session()

        # Post-login redirect may land on /dashboard/pledge rather than the
        # donations page. Navigate explicitly so callers get a consistent start.
        if "/pledge/donations" not in page.url:
            page.goto(_DONATIONS_URL)

    def _login(self, page: Page) -> None:
        """Fill and submit the email/password form."""
        if not self.email or not self.password:
            raise SessionError("Cannot login: GWWC_EMAIL and GWWC_PASSWORD must be set.")
        page.get_by_role("textbox", name="Email").fill(self.email)
        page.get_by_role("textbox", name="Password").fill(self.password)
        # Button starts disabled; becomes enabled once both fields have content.
        login_btn = page.get_by_role("button", name="Login")
        expect(login_btn).to_be_enabled(timeout=5_000)
        login_btn.click()
        page.wait_for_url("**/dashboard/**", timeout=20_000)
        log.info("Login successful.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_page(self) -> Page:
        """Return the active Playwright page (must call start() first)."""
        return self._require_page()

    def _require_page(self) -> Page:
        if self._page is None:
            raise SessionError("Session not started — use as a context manager or call start().")
        return self._page

    def _save_session(self) -> None:
        if self._context is None:
            raise SessionError("Cannot save session: browser context is not open.")
        storage = self._context.storage_state()
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(storage))
        log.debug("Session persisted to %s", self.session_file)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> GWWCSession:
        """Build a GWWCSession from environment variables.

        Required: GWWC_EMAIL, GWWC_PASSWORD
        Optional: GWWC_SESSION_FILE (default: ~/.gwwc_import_session.json)
                  GWWC_HEADLESS     (default: true; set to "false" to see the browser)
        """
        email = os.environ.get("GWWC_EMAIL", "")
        password = os.environ.get("GWWC_PASSWORD", "")
        if not email or not password:
            raise SessionError("GWWC_EMAIL and GWWC_PASSWORD must be set (e.g. in a .env file).")
        session_file = Path(os.environ.get("GWWC_SESSION_FILE", str(_DEFAULT_SESSION_FILE)))
        headless = os.environ.get("GWWC_HEADLESS", "true").lower() != "false"
        return cls(email=email, password=password, session_file=session_file, headless=headless)
