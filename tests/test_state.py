"""Unit tests for the SubmissionState / SubmissionRecord tracker."""

from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal
from pathlib import Path

from gwwc_import.automation.state import SubmissionRecord, SubmissionState
from gwwc_import.automation.submitter import SubmissionResult
from gwwc_import.models import Donation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_donation(source_id: str = "test-001") -> Donation:
    return Donation(
        source_system="test",
        source_id=source_id,
        date=date(2024, 1, 1),
        amount=Decimal("10.00"),
        currency="EUR",
        recipient_name="AMF",
        is_recurring=False,
    )


def _live_success(donation: Donation) -> SubmissionResult:
    return SubmissionResult(donation=donation, dry_run=False, success=True)


def _dry_run_success(donation: Donation) -> SubmissionResult:
    return SubmissionResult(donation=donation, dry_run=True, success=True)


def _live_failure(donation: Donation) -> SubmissionResult:
    return SubmissionResult(donation=donation, dry_run=False, success=False, error="boom")


# ---------------------------------------------------------------------------
# already_submitted
# ---------------------------------------------------------------------------


def test_empty_state_not_submitted(tmp_path: Path) -> None:
    state = SubmissionState(tmp_path / "state.json")
    assert not state.already_submitted("test-001")


def test_dry_run_record_not_counted_as_submitted(tmp_path: Path) -> None:
    d = _make_donation()
    state = SubmissionState(tmp_path / "state.json")
    state.record(_dry_run_success(d))
    assert not state.already_submitted(d.source_id)


def test_failed_live_record_not_counted_as_submitted(tmp_path: Path) -> None:
    d = _make_donation()
    state = SubmissionState(tmp_path / "state.json")
    state.record(_live_failure(d))
    assert not state.already_submitted(d.source_id)


def test_successful_live_record_counts_as_submitted(tmp_path: Path) -> None:
    d = _make_donation()
    state = SubmissionState(tmp_path / "state.json")
    state.record(_live_success(d))
    assert state.already_submitted(d.source_id)


def test_already_submitted_is_per_source_id(tmp_path: Path) -> None:
    d1 = _make_donation("id-1")
    d2 = _make_donation("id-2")
    state = SubmissionState(tmp_path / "state.json")
    state.record(_live_success(d1))
    assert state.already_submitted("id-1")
    assert not state.already_submitted("id-2")
    _ = d2  # not submitted


# ---------------------------------------------------------------------------
# filter_new
# ---------------------------------------------------------------------------


def test_filter_new_excludes_already_submitted(tmp_path: Path) -> None:
    d1 = _make_donation("id-1")
    d2 = _make_donation("id-2")
    state = SubmissionState(tmp_path / "state.json")
    state.record(_live_success(d1))
    result = state.filter_new([d1, d2])
    assert result == [d2]


def test_filter_new_force_returns_all(tmp_path: Path) -> None:
    d1 = _make_donation("id-1")
    d2 = _make_donation("id-2")
    state = SubmissionState(tmp_path / "state.json")
    state.record(_live_success(d1))
    result = state.filter_new([d1, d2], force=True)
    assert result == [d1, d2]


def test_filter_new_empty_state_returns_all(tmp_path: Path) -> None:
    donations = [_make_donation(f"id-{i}") for i in range(3)]
    state = SubmissionState(tmp_path / "state.json")
    assert state.filter_new(donations) == donations


# ---------------------------------------------------------------------------
# Persistence (round-trip)
# ---------------------------------------------------------------------------


def test_record_creates_state_file(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    state = SubmissionState(state_file)
    state.record(_live_success(_make_donation()))
    assert state_file.exists()


def test_round_trip_persists_records(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    d = _make_donation()
    SubmissionState(state_file).record(_live_success(d))

    reloaded = SubmissionState(state_file)
    assert reloaded.already_submitted(d.source_id)


def test_round_trip_preserves_all_fields(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    d = _make_donation("abc-123")
    state = SubmissionState(state_file)
    state.record(_live_failure(d))

    reloaded = SubmissionState(state_file)
    assert len(reloaded._records) == 1
    rec = reloaded._records[0]
    assert rec.source_id == "abc-123"
    assert rec.dry_run is False
    assert rec.success is False
    assert rec.error == "boom"


def test_multiple_records_accumulate(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    donations = [_make_donation(f"id-{i}") for i in range(5)]
    state = SubmissionState(state_file)
    for d in donations:
        state.record(_live_success(d))

    reloaded = SubmissionState(state_file)
    for d in donations:
        assert reloaded.already_submitted(d.source_id)


def test_state_file_in_nonexistent_parent_is_created(tmp_path: Path) -> None:
    state_file = tmp_path / "deep" / "nested" / "state.json"
    state = SubmissionState(state_file)
    state.record(_live_success(_make_donation()))
    assert state_file.exists()


# ---------------------------------------------------------------------------
# SubmissionRecord model
# ---------------------------------------------------------------------------


def test_submission_record_error_defaults_to_none() -> None:
    from datetime import datetime

    rec = SubmissionRecord(
        source_id="x",
        submitted_at=datetime.now(tz=UTC),
        dry_run=False,
        success=True,
    )
    assert rec.error is None
