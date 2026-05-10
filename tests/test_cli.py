"""Unit and integration tests for the CLI layer (Phase 2)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from gwwc_import.cli import (
    SOURCES,
    _apply_filters,
    _build_arg_parser,
    _build_source,
    _JSONEncoder,
    _log_deferred_flags,
    _parse_date_arg,
    run,
)
from gwwc_import.data_sources.base import DonationSource
from gwwc_import.data_sources.finanzguru import FinanzguruConfig, FinanzguruSource

FIXTURE = Path(__file__).parent / "fixtures" / "finanzguru_dummy.csv"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_args(**overrides) -> argparse.Namespace:
    """Return a minimal valid Namespace, with optional field overrides."""
    defaults = dict(
        input=str(FIXTURE),
        source="finanzguru",
        mode="dry-run",
        headless=True,
        limit=None,
        from_date=None,
        to_date=None,
        only_recurring=False,
        only_onetime=False,
        force_resubmit=False,
        state_file="~/.gwwc_import_state.json",
        session_file="~/.gwwc_import_session.json",
        log_level="WARNING",
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #


def test_sources_registry_contains_finanzguru() -> None:
    assert "finanzguru" in SOURCES
    assert SOURCES["finanzguru"] is FinanzguruSource


def test_every_registered_source_exposes_from_env() -> None:
    """`_build_source` calls `cls.from_env()` for every registered source."""
    for name, cls in SOURCES.items():
        assert hasattr(cls, "from_env"), f"{name} must expose a from_env() classmethod"
        assert callable(cls.from_env)


def test_build_source_returns_finanzguru_instance() -> None:
    source = _build_source("finanzguru")
    assert isinstance(source, FinanzguruSource)
    # Must satisfy the protocol so `_build_source`'s return type holds.
    assert isinstance(source, DonationSource)


def test_build_source_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown source"):
        _build_source("not-a-real-source")


def test_finanzguru_source_from_env_uses_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FINANZGURU_DONATION_CATEGORIES", "Spenden,Wohltätigkeit")
    monkeypatch.setenv("FINANZGURU_CURRENCY", "USD")
    source = FinanzguruSource.from_env()
    assert source.config.donation_categories == ["Spenden", "Wohltätigkeit"]
    assert source.config.currency == "USD"


def test_finanzguru_config_from_env_defaults(monkeypatch) -> None:
    monkeypatch.delenv("FINANZGURU_DONATION_CATEGORIES", raising=False)
    monkeypatch.delenv("FINANZGURU_CURRENCY", raising=False)
    monkeypatch.delenv("FINANZGURU_ENCODING", raising=False)
    cfg = FinanzguruConfig.from_env()
    assert cfg.donation_categories == ["Spenden"]
    assert cfg.currency == "EUR"
    assert cfg.encoding == "utf-8-sig"


def test_arg_parser_requires_input_and_source() -> None:
    p = _build_arg_parser()
    with pytest.raises(SystemExit) as exc:
        p.parse_args([])
    assert exc.value.code != 0


def test_arg_parser_defaults() -> None:
    p = _build_arg_parser()
    args = p.parse_args(["--input", "foo.csv", "--source", "finanzguru"])
    assert args.mode == "dry-run"
    assert args.headless is True
    assert args.limit is None
    assert args.from_date is None
    assert args.to_date is None
    assert args.only_recurring is False
    assert args.only_onetime is False
    assert args.force_resubmit is False
    assert args.log_level == "INFO"


def test_arg_parser_only_recurring_and_onetime_are_mutually_exclusive() -> None:
    p = _build_arg_parser()
    with pytest.raises(SystemExit):
        p.parse_args(
            [
                "--input",
                "foo.csv",
                "--source",
                "finanzguru",
                "--only-recurring",
                "--only-onetime",
            ]
        )


def test_arg_parser_no_headless_flag() -> None:
    p = _build_arg_parser()
    args = p.parse_args(["--input", "foo.csv", "--source", "finanzguru", "--no-headless"])
    assert args.headless is False


def test_arg_parser_all_flags_accepted() -> None:
    p = _build_arg_parser()
    args = p.parse_args(
        [
            "--input",
            "export.csv",
            "--source",
            "finanzguru",
            "--mode",
            "dry-run",
            "--limit",
            "5",
            "--from-date",
            "2026-01-01",
            "--to-date",
            "2026-12-31",
            "--only-recurring",
            "--state-file",
            "/tmp/state.json",
            "--session-file",
            "/tmp/session.json",
            "--log-level",
            "DEBUG",
        ]
    )
    assert args.limit == 5
    assert args.from_date == "2026-01-01"
    assert args.to_date == "2026-12-31"
    assert args.only_recurring is True


# --------------------------------------------------------------------------- #
# Date arg parsing
# --------------------------------------------------------------------------- #


def test_parse_date_arg_none_returns_none() -> None:
    assert _parse_date_arg(None, "--from-date") is None


def test_parse_date_arg_valid_iso() -> None:
    assert _parse_date_arg("2026-01-07", "--from-date") == date(2026, 1, 7)


def test_parse_date_arg_invalid_raises_system_exit() -> None:
    with pytest.raises(SystemExit) as exc:
        _parse_date_arg("07.01.2026", "--from-date")
    assert "--from-date" in str(exc.value)


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def all_donations():
    return FinanzguruSource().load_donations(FIXTURE)


def test_from_date_filter(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=date(2026, 2, 1),
        to_date=None,
        only_recurring=False,
        only_onetime=False,
        limit=None,
    )
    assert all(d.date >= date(2026, 2, 1) for d in result)
    assert len(result) < len(all_donations)


def test_to_date_filter(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=None,
        to_date=date(2026, 1, 31),
        only_recurring=False,
        only_onetime=False,
        limit=None,
    )
    assert all(d.date <= date(2026, 1, 31) for d in result)
    assert len(result) < len(all_donations)


def test_date_range_filter(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31),
        only_recurring=False,
        only_onetime=False,
        limit=None,
    )
    assert all(date(2026, 1, 1) <= d.date <= date(2026, 1, 31) for d in result)


def test_only_recurring_filter(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=None,
        to_date=None,
        only_recurring=True,
        only_onetime=False,
        limit=None,
    )
    assert result
    assert all(d.is_recurring for d in result)


def test_only_onetime_filter(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=None,
        to_date=None,
        only_recurring=False,
        only_onetime=True,
        limit=None,
    )
    assert result
    assert all(not d.is_recurring for d in result)


def test_limit_filter(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=None,
        to_date=None,
        only_recurring=False,
        only_onetime=False,
        limit=2,
    )
    assert len(result) == 2


def test_limit_larger_than_total_returns_all(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=None,
        to_date=None,
        only_recurring=False,
        only_onetime=False,
        limit=9999,
    )
    assert len(result) == len(all_donations)


def test_filters_applied_in_order_before_limit(all_donations) -> None:
    # Apply recurring filter first, then limit — limit should apply to
    # the already-filtered set, not the original.
    recurring = [d for d in all_donations if d.is_recurring]
    result = _apply_filters(
        all_donations,
        from_date=None,
        to_date=None,
        only_recurring=True,
        only_onetime=False,
        limit=1,
    )
    assert len(result) == 1
    assert result[0].is_recurring
    # The chosen donation must be the first recurring one
    assert result[0].source_id == recurring[0].source_id


def test_empty_result_on_no_match(all_donations) -> None:
    result = _apply_filters(
        all_donations,
        from_date=date(2099, 1, 1),
        to_date=None,
        only_recurring=False,
        only_onetime=False,
        limit=None,
    )
    assert result == []


# --------------------------------------------------------------------------- #
# run() integration — dry-run JSON output
# --------------------------------------------------------------------------- #


def test_run_dryrun_returns_donations(capsys) -> None:
    donations = run(_make_args())
    assert len(donations) == 7


def test_run_dryrun_prints_valid_json(capsys) -> None:
    run(_make_args())
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert isinstance(payload, list)
    assert len(payload) == 7


def test_run_dryrun_json_fields(capsys) -> None:
    run(_make_args())
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    record = payload[0]
    assert set(record.keys()) >= {
        "source_system",
        "source_id",
        "date",
        "amount",
        "currency",
        "recipient_name",
        "description",
        "is_recurring",
    }
    assert record["source_system"] == "finanzguru"
    assert record["currency"] == "EUR"


def test_run_dryrun_amount_is_string_decimal(capsys) -> None:
    run(_make_args())
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    for record in payload:
        # Amounts must be serialised as decimal strings ("50.00"), not floats
        assert isinstance(record["amount"], str), (
            f"Expected string decimal, got {type(record['amount'])}: {record['amount']!r}"
        )
        assert "." in record["amount"]


def test_run_dryrun_json_to_stdout_not_stderr(capsys) -> None:
    run(_make_args(log_level="INFO"))
    captured = capsys.readouterr()
    # stdout must be valid JSON; stderr may have log lines
    json.loads(captured.out)
    assert captured.out.strip().startswith("[")


def test_run_dryrun_with_limit(capsys) -> None:
    donations = run(_make_args(limit=3))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert len(donations) == 3
    assert len(payload) == 3


def test_run_dryrun_with_from_date(capsys) -> None:
    donations = run(_make_args(from_date="2026-02-01"))
    assert all(d.date >= date(2026, 2, 1) for d in donations)


def test_run_dryrun_with_only_recurring(capsys) -> None:
    donations = run(_make_args(only_recurring=True))
    assert donations
    assert all(d.is_recurring for d in donations)


def test_run_dryrun_with_only_onetime(capsys) -> None:
    donations = run(_make_args(only_onetime=True))
    assert donations
    assert all(not d.is_recurring for d in donations)


def test_run_live_mode_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="Phase 3/4"):
        run(_make_args(mode="live"))


# --------------------------------------------------------------------------- #
# Deferred-flag debug logging
# --------------------------------------------------------------------------- #


def test_log_deferred_flags_force_resubmit(caplog) -> None:
    import logging

    log = logging.getLogger("test")
    with caplog.at_level(logging.DEBUG, logger="test"):
        _log_deferred_flags(_make_args(force_resubmit=True), log)
    assert any("--force-resubmit" in r.message for r in caplog.records)


def test_log_deferred_flags_custom_state_file(caplog) -> None:
    import logging

    log = logging.getLogger("test")
    with caplog.at_level(logging.DEBUG, logger="test"):
        _log_deferred_flags(_make_args(state_file="/tmp/custom.json"), log)
    assert any("--state-file" in r.message for r in caplog.records)


def test_log_deferred_flags_silent_when_defaults(caplog) -> None:
    import logging

    log = logging.getLogger("test")
    with caplog.at_level(logging.DEBUG, logger="test"):
        _log_deferred_flags(_make_args(), log)
    deferred_records = [
        r
        for r in caplog.records
        if any(
            flag in r.message
            for flag in ("--force-resubmit", "--state-file", "--session-file", "--no-headless")
        )
    ]
    assert deferred_records == []


# --------------------------------------------------------------------------- #
# JSON encoder
# --------------------------------------------------------------------------- #


def test_json_encoder_decimal() -> None:
    from decimal import Decimal

    result = json.dumps({"v": Decimal("50.00")}, cls=_JSONEncoder)
    assert json.loads(result) == {"v": "50.00"}


def test_json_encoder_date() -> None:
    result = json.dumps({"d": date(2026, 1, 7)}, cls=_JSONEncoder)
    assert json.loads(result) == {"d": "2026-01-07"}


# --------------------------------------------------------------------------- #
# Entry-point smoke test
# --------------------------------------------------------------------------- #


def test_python_m_gwwc_import_dry_run_exits_zero() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gwwc_import",
            "--input",
            str(FIXTURE),
            "--source",
            "finanzguru",
            "--mode",
            "dry-run",
            "--log-level",
            "WARNING",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) == 7


def test_python_m_gwwc_import_live_mode_exits_one() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gwwc_import",
            "--input",
            str(FIXTURE),
            "--source",
            "finanzguru",
            "--mode",
            "live",
        ],
        capture_output=True,
        text=True,
    )
    # Exit code 1 (general error), not 2 (argparse usage error).
    assert result.returncode == 1
    assert "Phase 3/4" in result.stderr


def test_python_m_gwwc_import_invalid_args_exits_two() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gwwc_import",
            "--input",
            str(FIXTURE),
            "--source",
            "not-a-real-source",
        ],
        capture_output=True,
        text=True,
    )
    # argparse uses 2 for usage errors — distinct from our runtime errors (1).
    assert result.returncode == 2


def test_python_m_gwwc_import_no_args_exits_nonzero() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "gwwc_import"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
