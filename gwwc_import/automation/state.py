"""Submitted-donations state tracker.

Records which source_id values have been successfully submitted to GWWC,
so that re-running the CLI on the same export does not create duplicates.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from gwwc_import.automation.submitter import SubmissionResult
from gwwc_import.models import Donation


class SubmissionRecord(BaseModel):
    source_id: str
    submitted_at: datetime
    dry_run: bool
    success: bool
    error: str | None = None


class SubmissionState:
    """Persists submission history as a JSON file on disk.

    A donation is considered "already submitted" only when there is at least
    one successful, non-dry-run record for its source_id.  Dry-run and failed
    records are stored for auditing but do not block re-submission.
    """

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser()
        self._records: list[SubmissionRecord] = []
        if self._path.exists():
            raw = json.loads(self._path.read_text())
            self._records = [SubmissionRecord.model_validate(r) for r in raw]

    def already_submitted(self, source_id: str) -> bool:
        return any(r.source_id == source_id and r.success and not r.dry_run for r in self._records)

    def filter_new(self, donations: list[Donation], *, force: bool = False) -> list[Donation]:
        """Return only donations not yet successfully submitted.

        With force=True, all donations are returned regardless of state.
        """
        if force:
            return donations
        return [d for d in donations if not self.already_submitted(d.source_id)]

    def record(self, result: SubmissionResult) -> None:
        """Append a result and persist to disk immediately."""
        self._records.append(
            SubmissionRecord(
                source_id=result.donation.source_id,
                submitted_at=datetime.now(tz=UTC),
                dry_run=result.dry_run,
                success=result.success,
                error=result.error,
            )
        )
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                [r.model_dump(mode="json") for r in self._records],
                indent=2,
                ensure_ascii=False,
            )
        )
