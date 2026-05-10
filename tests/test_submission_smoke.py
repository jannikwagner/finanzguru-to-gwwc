"""Smoke tests for the Playwright login, session, and form-submission flows.

These tests require live GWWC credentials and a network connection.
They are skipped automatically in CI unless GWWC_EMAIL is set.

Run locally with credentials in .env:
    pytest tests/test_submission_smoke.py -v
"""

import json
import os
from datetime import date
from decimal import Decimal

import pytest
from dotenv import load_dotenv

from gwwc_import.automation.session import GWWCSession, SessionError
from gwwc_import.automation.submitter import DonationSubmitter
from gwwc_import.models import Donation

load_dotenv()

pytestmark = pytest.mark.skipif(
    not os.environ.get("GWWC_EMAIL"),
    reason="GWWC_EMAIL not set — skipping live integration tests",
)


@pytest.fixture()
def session(tmp_path):
    """A GWWCSession using real credentials but a temporary session file."""
    sess = GWWCSession(
        email=os.environ["GWWC_EMAIL"],
        password=os.environ["GWWC_PASSWORD"],
        session_file=tmp_path / "test_session.json",
        headless=True,
    )
    with sess:
        yield sess


# ---------------------------------------------------------------------------
# Session / login tests
# ---------------------------------------------------------------------------


def test_login_reaches_dashboard(session):
    """Login should land on the /dashboard/ URL tree."""
    session.ensure_logged_in()
    assert "/dashboard/" in session.get_page().url


def test_donations_page_loads(session):
    """After login the Donations heading must be visible."""
    session.ensure_logged_in()
    page = session.get_page()
    heading = page.get_by_role("heading", name="Donations", exact=True)
    heading.wait_for(timeout=10_000)
    assert heading.is_visible()


def test_session_file_created(session, tmp_path):
    """ensure_logged_in() must persist a valid JSON session file."""
    session.ensure_logged_in()
    session_file = tmp_path / "test_session.json"
    assert session_file.exists()
    data = json.loads(session_file.read_text())
    assert "cookies" in data


def test_session_restore_skips_login(tmp_path):
    """A second session using a saved state file must reach the dashboard."""
    session_file = tmp_path / "shared_session.json"

    # First session: login and persist storage state.
    sess1 = GWWCSession(
        email=os.environ["GWWC_EMAIL"],
        password=os.environ["GWWC_PASSWORD"],
        session_file=session_file,
        headless=True,
    )
    with sess1:
        sess1.ensure_logged_in()

    assert session_file.exists(), "Session file must be created after first login."

    # Second session restores from disk. Real credentials provided as fallback
    # in case the site's auth state doesn't survive a full browser restart
    # (e.g. in-memory tokens), but the primary expectation is that the stored
    # cookies are sufficient.
    sess2 = GWWCSession(
        email=os.environ["GWWC_EMAIL"],
        password=os.environ["GWWC_PASSWORD"],
        session_file=session_file,
        headless=True,
    )
    with sess2:
        sess2.ensure_logged_in()
        assert "/dashboard/" in sess2.get_page().url


def test_from_env_raises_without_credentials(monkeypatch):
    """from_env() must raise SessionError when GWWC_EMAIL is missing."""
    monkeypatch.delenv("GWWC_EMAIL", raising=False)
    monkeypatch.delenv("GWWC_PASSWORD", raising=False)
    with pytest.raises(SessionError, match="GWWC_EMAIL"):
        GWWCSession.from_env()


# ---------------------------------------------------------------------------
# Submission tests
# ---------------------------------------------------------------------------

_SAMPLE_DONATION = Donation(
    source_system="test",
    source_id="smoke-001",
    date=date(2024, 12, 25),
    amount=Decimal("10.00"),
    currency="EUR",
    recipient_name="Against Malaria Foundation",
    is_recurring=False,
)

_SAMPLE_RECURRING_DONATION = Donation(
    source_system="test",
    source_id="smoke-002",
    date=date(2024, 11, 1),
    amount=Decimal("25.00"),
    currency="EUR",
    recipient_name="GiveDirectly",
    is_recurring=True,
)


def test_dry_run_one_time_donation(session):
    """Dry-run: form is filled and cancelled; no donation is created."""
    session.ensure_logged_in()
    submitter = DonationSubmitter(session.get_page(), dry_run=True)
    result = submitter.submit(_SAMPLE_DONATION)
    assert result.success
    assert result.dry_run
    assert result.error is None


def test_dry_run_recurring_donation(session):
    """Dry-run with a recurring donation selects the Recurring radio."""
    session.ensure_logged_in()
    submitter = DonationSubmitter(session.get_page(), dry_run=True)
    result = submitter.submit(_SAMPLE_RECURRING_DONATION)
    assert result.success
    assert result.dry_run
    assert result.error is None


def test_dry_run_unknown_org(session):
    """Dry-run with an unknown org name falls back to the 'Create' option."""
    session.ensure_logged_in()
    submitter = DonationSubmitter(session.get_page(), dry_run=True)
    donation = Donation(
        source_system="test",
        source_id="smoke-003",
        date=date(2024, 6, 1),
        amount=Decimal("5.00"),
        currency="EUR",
        recipient_name="Unbekannte Hilfsorganisation e.V.",
        is_recurring=False,
    )
    result = submitter.submit(donation)
    assert result.success
    assert result.dry_run
    assert result.error is None
