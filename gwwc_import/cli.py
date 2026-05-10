"""CLI entry point for gwwc_import.

Run:
    python -m gwwc_import --help
or after `pip install -e .`:
    gwwc_import --help

Phase 2 delivers argument parsing, filtering, and dry-run JSON output.
Phase 3/4 will implement live submission via Playwright.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from gwwc_import.data_sources.base import DonationSource
from gwwc_import.data_sources.finanzguru import FinanzguruSource
from gwwc_import.privacy import redacted_label

if TYPE_CHECKING:
    from gwwc_import.models import Donation

# Registry of supported data sources.  New sources only need to appear here
# and must expose a `from_env()` classmethod.
SOURCES: dict[str, type[DonationSource]] = {
    "finanzguru": FinanzguruSource,
}

# Default values for flags that are accepted by argparse but not yet acted on
# (Phase 5 / Phase 3-4).  Used to detect non-default user input for DEBUG logs.
_DEFAULT_STATE_FILE = "~/.gwwc_import_state.json"
_DEFAULT_SESSION_FILE = "~/.gwwc_import_session.json"


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #


def main() -> None:
    """Installed entry-point and `python -m gwwc_import` target."""
    load_dotenv()
    parser = _build_arg_parser()
    args = parser.parse_args()
    _setup_logging(args.log_level)
    try:
        run(args)
    except Exception as exc:
        # NotImplementedError and any other failure both exit with 1 — exit code
        # 2 is reserved by argparse for usage errors (invalid arguments).
        logging.error("%s", exc)
        sys.exit(1)


def run(args: argparse.Namespace) -> list[Donation]:
    """Core orchestration — separated from main() for testability.

    Returns the list of donations that were (or would be) processed.
    """
    log = logging.getLogger(__name__)

    from_date = _parse_date_arg(args.from_date, "--from-date")
    to_date = _parse_date_arg(args.to_date, "--to-date")

    source = _build_source(args.source)
    donations = source.load_donations(Path(args.input))
    log.debug("Loaded %d total row(s) from %s.", len(donations), args.input)

    donations = _apply_filters(
        donations,
        from_date=from_date,
        to_date=to_date,
        only_recurring=args.only_recurring,
        only_onetime=args.only_onetime,
        limit=args.limit,
    )
    log.info("Found %d donation(s) after filtering.", len(donations))

    if args.mode == "dry-run":
        _dry_run_output(donations, log)
    elif args.mode == "live":
        _run_live(args, donations, log)

    return donations


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gwwc_import",
        description=(
            "Import Finanzguru donation transactions into the "
            "EA.org / Giving What We Can 'My Giving' dashboard."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    p.add_argument(
        "--input", required=True, metavar="FILE", help="Path to the export file (.csv or .xlsx)"
    )
    p.add_argument("--source", required=True, choices=list(SOURCES), help="Data source type")
    p.add_argument(
        "--mode",
        choices=["dry-run", "live"],
        default="dry-run",
        help="dry-run prints what would be submitted; live submits",
    )
    p.add_argument(
        "--headless",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Run browser headlessly (Phase 3/4 only)",
    )
    p.add_argument(
        "--limit",
        type=int,
        metavar="N",
        default=None,
        help="Only process the first N donations after all other filters",
    )
    p.add_argument(
        "--from-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only include donations on or after this date",
    )
    p.add_argument(
        "--to-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Only include donations on or before this date",
    )

    recurrence = p.add_mutually_exclusive_group()
    recurrence.add_argument(
        "--only-recurring",
        action="store_true",
        help="Only process recurring (Vertrag-based) donations",
    )
    recurrence.add_argument(
        "--only-onetime", action="store_true", help="Only process one-time donations"
    )

    p.add_argument(
        "--force-resubmit",
        action="store_true",
        help="Re-submit donations already recorded in the state file (Phase 5)",
    )
    p.add_argument(
        "--state-file",
        metavar="PATH",
        default=_DEFAULT_STATE_FILE,
        help="State file tracking already-submitted donations",
    )
    p.add_argument(
        "--session-file",
        metavar="PATH",
        default=_DEFAULT_SESSION_FILE,
        help="Playwright session/cookie persistence file (Phase 3)",
    )
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity",
    )

    return p


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #


def _apply_filters(
    donations: list[Donation],
    *,
    from_date: date | None,
    to_date: date | None,
    only_recurring: bool,
    only_onetime: bool,
    limit: int | None,
) -> list[Donation]:
    if from_date is not None:
        donations = [d for d in donations if d.date >= from_date]
    if to_date is not None:
        donations = [d for d in donations if d.date <= to_date]
    if only_recurring:
        donations = [d for d in donations if d.is_recurring]
    if only_onetime:
        donations = [d for d in donations if not d.is_recurring]
    if limit is not None:
        donations = donations[:limit]
    return donations


# --------------------------------------------------------------------------- #
# Dry-run output
# --------------------------------------------------------------------------- #


def _dry_run_output(donations: list[Donation], log: logging.Logger) -> None:
    """Log a privacy-safe summary and print a full JSON array to stdout."""
    for d in donations:
        log.info("[dry-run] Would submit: %s", redacted_label(d))
        log.debug("[dry-run] Full record: %s", d.model_dump())

    payload = [d.model_dump() for d in donations]
    print(json.dumps(payload, indent=2, ensure_ascii=False, cls=_JSONEncoder))


class _JSONEncoder(json.JSONEncoder):
    """Serialise `Decimal` and `date`/`datetime` objects produced by model_dump()."""

    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, date):
            return o.isoformat()
        return super().default(o)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _build_source(source_key: str) -> DonationSource:
    """Look up a source class in `SOURCES` and build it from the environment.

    Every registered source class must expose a `from_env()` classmethod.
    """
    cls = SOURCES.get(source_key)
    if cls is None:
        # Unreachable in normal flow — argparse `choices` already validates this.
        raise ValueError(f"Unknown source: {source_key!r}")
    return cls.from_env()


def _run_live(args: argparse.Namespace, donations: list[Donation], log: logging.Logger) -> None:
    from gwwc_import.automation.session import GWWCSession, SessionError
    from gwwc_import.automation.state import SubmissionState
    from gwwc_import.automation.submitter import DonationSubmitter

    state = SubmissionState(Path(args.state_file))
    to_submit = state.filter_new(donations, force=args.force_resubmit)

    skipped = len(donations) - len(to_submit)
    if skipped:
        log.info(
            "Skipping %d already-submitted donation(s) (use --force-resubmit to override).",
            skipped,
        )

    if not to_submit:
        log.info("Nothing new to submit.")
        return

    email = os.environ.get("GWWC_EMAIL", "")
    password = os.environ.get("GWWC_PASSWORD", "")
    if not email or not password:
        raise SessionError("GWWC_EMAIL and GWWC_PASSWORD must be set (e.g. in a .env file).")

    with GWWCSession(
        email=email,
        password=password,
        session_file=Path(args.session_file),
        headless=args.headless,
    ) as session:
        session.ensure_logged_in()
        submitter = DonationSubmitter(session.get_page(), dry_run=False)
        results = submitter.submit_all(to_submit)

    for result in results:
        state.record(result)

    failed = [r for r in results if not r.success]
    if failed:
        log.error(
            "%d/%d submission(s) failed. See above for details.",
            len(failed),
            len(results),
        )
    else:
        log.info("All %d donation(s) submitted successfully.", len(results))


def _parse_date_arg(value: str | None, flag: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise SystemExit(f"{flag}: invalid date {value!r} — expected YYYY-MM-DD") from e


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stderr,
    )
