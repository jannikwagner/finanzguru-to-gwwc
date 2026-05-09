"""Tiny redaction helpers used in user-facing logs and error messages.

Real Finanzguru exports are highly sensitive (full payee names, amounts,
memos). The rule for this project is: at INFO/WARNING/ERROR level we refer
to a donation only by the first 8 chars of its `source_id`. Full details
appear at DEBUG level only when the user opts in via `--log-level DEBUG`.
"""

from __future__ import annotations

from gwwc_import.models import Donation


def short_id(source_id: str) -> str:
    """Stable 8-char prefix used in non-debug logs."""
    return source_id[:8] if source_id else "????????"


def redacted_label(donation: Donation) -> str:
    """A privacy-safe single-line label for a donation."""
    return f"donation[{short_id(donation.source_id)}] ({donation.date.isoformat()})"
