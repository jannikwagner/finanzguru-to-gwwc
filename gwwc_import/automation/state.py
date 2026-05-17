"""Submitted-donations state tracker.

Records which source_id values have been successfully submitted to GWWC,
so that re-running the CLI on the same export does not create duplicates.

The state file is critical for idempotency — if it's corrupted, the CLI
either loses duplicate prevention or refuses to run.  Therefore:

* writes are atomic (write-to-tempfile + os.replace), so an interrupted
  run never leaves a half-written file;
* a corrupted file on load is moved aside to `<path>.corrupted-<ts>` and
  a fresh empty state is used, with a clear WARNING — better UX than
  crashing on every subsequent run.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from gwwc_import.automation.submitter import SubmissionResult
from gwwc_import.models import Donation

log = logging.getLogger(__name__)


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
        self._records: list[SubmissionRecord] = self._load()

    def _load(self) -> list[SubmissionRecord]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text())
            return [SubmissionRecord.model_validate(r) for r in raw]
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            backup = self._path.with_suffix(
                self._path.suffix + f".corrupted-{int(datetime.now(tz=UTC).timestamp())}"
            )
            self._path.rename(backup)
            log.warning(
                "State file %s was unreadable (%s). "
                "Moved to %s and starting fresh. "
                "Duplicates already submitted before this run will not be detected.",
                self._path,
                type(exc).__name__,
                backup,
            )
            return []

    def already_submitted(self, source_id: str) -> bool:
        return any(r.source_id == source_id and r.success and not r.dry_run for r in self._records)

    def filter_new(self, donations: list[Donation], *, force: bool = False) -> list[Donation]:
        """Return only donations not yet successfully submitted.

        With force=True, all donations are returned regardless of state.
        """
        if force:
            return donations
        submitted_ids = {
            r.source_id for r in self._records if r.success and not r.dry_run
        }
        return [d for d in donations if d.source_id not in submitted_ids]

    def record(self, result: SubmissionResult) -> None:
        """Append a result and persist to disk immediately (atomically)."""
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
        """Atomic write: temp file in the same directory, then os.replace."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                [r.model_dump(mode="json") for r in self._records],
                indent=2,
                ensure_ascii=False,
            )
        )
        # os.replace is atomic on POSIX and Windows when both paths are on
        # the same filesystem (guaranteed: same parent directory).
        os.replace(tmp, self._path)
