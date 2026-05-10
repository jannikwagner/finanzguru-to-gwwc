"""GWWC donation form submission via Playwright.

Fills the 'Report a donation' dialog at:
  /dashboard/pledge/donations?report=true&mode=manual

Recipient organisation uses a fuzzy-search combobox backed by react-select.
If no existing org matches exactly, the 'Create "X"' option is used.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from gwwc_import.models import Donation
from gwwc_import.privacy import redacted_label

_DONATIONS_URL = "https://www.givingwhatwecan.org/dashboard/pledge/donations"
_TIMEOUT = 10_000  # ms — used for form rendering and Save button
# Matches "Report your first donation" (no donations) and "Report a donation"
# (once donations exist). Both open the same form dialog.
_REPORT_BTN_RE = re.compile(r"report.+donation", re.IGNORECASE)

log = logging.getLogger(__name__)


class FormStructureError(Exception):
    """Raised when expected DOM elements are missing from the donation form."""


@dataclass
class SubmissionResult:
    donation: Donation
    dry_run: bool
    success: bool = True
    error: str | None = None


class DonationSubmitter:
    """Fills and submits the GWWC 'Report a donation' form.

    Usage::

        submitter = DonationSubmitter(session.get_page(), dry_run=False)
        results = submitter.submit_all(donations)
    """

    def __init__(self, page: Page, dry_run: bool = True) -> None:
        self.page = page
        self.dry_run = dry_run

    def submit_all(self, donations: list[Donation]) -> list[SubmissionResult]:
        """Submit each donation in sequence, collecting results."""
        return [self.submit(d) for d in donations]

    def submit(self, donation: Donation) -> SubmissionResult:
        log.info("%s %s", "Dry-run:" if self.dry_run else "Submitting:", redacted_label(donation))
        log.debug(
            "Full record: %s %s on %s to %r",
            donation.amount,
            donation.currency,
            donation.date,
            donation.recipient_name,
        )
        try:
            dialog = self._open_form()
            self._fill_recipient(dialog, donation.recipient_name)
            self._fill_currency(dialog, donation.currency)
            self._fill_amount(dialog, donation.amount)
            self._fill_date(dialog, donation.date)
            self._set_recurring(dialog, donation.is_recurring)

            if self.dry_run:
                log.info("Dry-run: form filled — cancelling without save.")
                dialog.get_by_role("button", name="Cancel").click()
                return SubmissionResult(donation=donation, dry_run=True)

            self._save(dialog)
            return SubmissionResult(donation=donation, dry_run=False)

        except Exception as exc:
            log.error("Submission failed for %s: %s", donation.source_id, exc)
            return SubmissionResult(
                donation=donation, dry_run=self.dry_run, success=False, error=str(exc)
            )

    # ------------------------------------------------------------------
    # Form steps
    # ------------------------------------------------------------------

    def _open_form(self) -> Locator:
        """Navigate to the donations page if needed, click the report button,
        and return the dialog locator.

        Navigating directly to the form URL via page.goto() does not reliably
        open the dialog in headless Chromium because the React Router component
        only reads the ?report=true query param on a fresh mount. Clicking the
        button triggers a proper client-side navigation.

        We skip re-navigation when already on the donations page to avoid a
        full page reload that would restart async data fetching and push button
        visibility past the timeout window.
        """
        if _DONATIONS_URL not in self.page.url or "report=true" in self.page.url:
            self.page.goto(_DONATIONS_URL)

        # Cookie consent can reappear on navigation in a fresh browser context.
        try:
            self.page.get_by_role("button", name="Accept all").click(timeout=4_000)
            log.debug("Cookie consent dismissed in _open_form.")
        except PlaywrightTimeoutError:
            pass

        # Wait for and click the report button. Using a regex matches both
        # "Report your first donation" (no donations yet) and "Report a donation"
        # (once donations exist) with a single timeout rather than serial checks.
        # Use 30 s here: the donation list is loaded by an async API call after
        # page render, and on a freshly-authenticated session this can be slow.
        report_btn = self.page.get_by_role("button", name=_REPORT_BTN_RE).first
        try:
            report_btn.wait_for(state="visible", timeout=30_000)
            report_btn.click()
        except PlaywrightTimeoutError as exc:
            raise FormStructureError(
                f"Could not find a 'Report a donation' button on {_DONATIONS_URL}."
            ) from exc

        # Wait for the form's first field to confirm the dialog is ready.
        try:
            self.page.get_by_role("combobox", name="Recipient organisation").wait_for(
                state="visible", timeout=_TIMEOUT
            )
        except PlaywrightTimeoutError as exc:
            raise FormStructureError(
                "Donation form did not render — 'Recipient organisation' field not found."
            ) from exc

        return self.page.get_by_role("dialog")

    def _fill_recipient(self, dialog: Locator, name: str) -> None:
        # Form fields are rendered in a React portal outside the dialog's DOM
        # subtree, so scope to self.page rather than dialog.
        combobox = self.page.get_by_role("combobox", name="Recipient organisation")
        combobox.press_sequentially(name, delay=50)

        listbox = self.page.get_by_role("listbox")
        try:
            listbox.wait_for(state="visible", timeout=5_000)
            # Wait for at least one option to load (react-select fetches async).
            listbox.get_by_role("option").first.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeoutError as exc:
            raise FormStructureError(
                "Recipient organisation dropdown did not open or load options."
            ) from exc

        # Prefer an exact case-insensitive match over the create option.
        options = listbox.get_by_role("option").all()
        for option in options:
            text = option.inner_text().strip()
            if text.lower() == name.lower():
                option.click()
                return

        # Fall back to the react-select "Create X" option.
        create_option = listbox.get_by_role("option", name=f'Create "{name}"', exact=True)
        if create_option.count() > 0:
            log.debug("No exact org match for %r — using create option.", name)
            create_option.click()
            return

        # Last resort: pick the first suggestion if it contains a substring of the target name.
        if options:
            first_text = options[0].inner_text().strip()
            if any(word.lower() in first_text.lower() for word in name.split() if len(word) > 3):
                log.warning(
                    "No exact or create match for %r — picking first result %r.", name, first_text
                )
                options[0].click()
                return

        raise FormStructureError(f"No dropdown options found for recipient: {name!r}")

    def _fill_currency(self, dialog: Locator, currency: str) -> None:
        combobox = self.page.get_by_role("combobox", name="Currency")
        combobox.press_sequentially(currency, delay=50)

        listbox = self.page.get_by_role("listbox")
        try:
            listbox.wait_for(state="visible", timeout=5_000)
            listbox.get_by_role("option").first.wait_for(state="visible", timeout=5_000)
        except PlaywrightTimeoutError as exc:
            raise FormStructureError(f"Currency dropdown did not open for {currency!r}.") from exc

        options = listbox.get_by_role("option").all()
        cu = currency.upper()
        for option in options:
            text = option.inner_text().strip().upper()
            # Match "EUR", "EUR - Euro", "EUR (Euro)", etc.
            if text == cu or text.startswith(cu + " ") or text.startswith(cu + "("):
                option.click()
                return

        raise FormStructureError(
            f"No currency match found for {currency!r}. "
            f"Available: {[o.inner_text().strip() for o in options]}"
        )

    def _fill_amount(self, dialog: Locator, amount: Decimal) -> None:
        self.page.get_by_role("textbox", name="Amount").fill(str(amount))

    def _fill_date(self, dialog: Locator, donation_date: date) -> None:
        self.page.get_by_role("textbox", name="Donation date").fill(
            donation_date.strftime("%Y-%m-%d")
        )

    def _set_recurring(self, dialog: Locator, is_recurring: bool) -> None:
        label = "Recurring" if is_recurring else "One-time"
        # The radio <input> is overlaid by a <span> that intercepts pointer events;
        # force=True dispatches the event directly on the input element.
        self.page.get_by_role("radio", name=label).click(force=True)

    def _save(self, dialog: Locator) -> None:
        save_btn = dialog.get_by_role("button", name="Save")
        try:
            expect(save_btn).to_be_enabled(timeout=5_000)
        except Exception as exc:
            raise FormStructureError(
                "Save button did not become enabled — form may be incomplete."
            ) from exc

        save_btn.click()

        # Dialog closing is the success signal.
        try:
            dialog.wait_for(state="hidden", timeout=15_000)
        except PlaywrightTimeoutError as exc:
            raise FormStructureError(
                "Dialog did not close after Save — submission may have failed."
            ) from exc

        log.info("Donation submitted successfully.")
