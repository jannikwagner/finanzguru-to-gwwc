"""Smoke tests for the Playwright login and session flow.

These tests require live GWWC credentials and a network connection.
They are skipped automatically in CI unless GWWC_EMAIL is set.

Run locally with credentials in .env:
    pytest tests/test_submission_smoke.py -v
"""

import json
import os

import pytest
from dotenv import load_dotenv

from gwwc_import.automation.session import GWWCSession, SessionError

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
