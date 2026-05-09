"""Unit tests for the Finanzguru parser (Phase 1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from gwwc_import.data_sources.base import DataSourceError, DonationSource
from gwwc_import.data_sources.finanzguru import (
    FinanzguruConfig,
    FinanzguruSource,
    _parse_amount,
    _parse_date,
)
from gwwc_import.models import Donation

FIXTURE = Path(__file__).parent / "fixtures" / "finanzguru_dummy.csv"


# --------------------------------------------------------------------------- #
# End-to-end against the dummy fixture
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def donations() -> list[Donation]:
    return FinanzguruSource().load_donations(FIXTURE)


def test_implements_donation_source_protocol() -> None:
    assert isinstance(FinanzguruSource(), DonationSource)


def test_only_donation_rows_are_kept(donations: list[Donation]) -> None:
    # Fixture has 11 rows total: 4 non-donations (1 salary, 2 grocery, 1 cafe)
    # and 7 donations.
    assert len(donations) == 7
    assert {d.recipient_name for d in donations} == {
        "Against Malaria Foundation",
        "GiveDirectly",
        "GiveWell Inc",
        "Wikimedia Foerderverein",
    }


def test_recurring_flag_follows_vertrag_column(donations: list[Donation]) -> None:
    by_payee = {d.recipient_name: [] for d in donations}
    for d in donations:
        by_payee[d.recipient_name].append(d)

    # AMF and GiveDirectly entries all carry a Vertrag value.
    assert all(d.is_recurring for d in by_payee["Against Malaria Foundation"])
    assert all(d.is_recurring for d in by_payee["GiveDirectly"])

    # GiveWell and Wikimedia entries have no Vertrag value.
    assert all(not d.is_recurring for d in by_payee["GiveWell Inc"])
    assert all(not d.is_recurring for d in by_payee["Wikimedia Foerderverein"])


def test_amount_is_positive_decimal(donations: list[Donation]) -> None:
    for d in donations:
        assert isinstance(d.amount, Decimal)
        assert d.amount > 0
    amf = next(d for d in donations if d.recipient_name == "Against Malaria Foundation")
    assert amf.amount == Decimal("50.00")
    givewell = next(d for d in donations if d.recipient_name == "GiveWell Inc")
    assert givewell.amount == Decimal("200.00")


def test_currency_is_eur_by_default(donations: list[Donation]) -> None:
    assert {d.currency for d in donations} == {"EUR"}


def test_dates_parse_german_format(donations: list[Donation]) -> None:
    amf_jan = next(
        d for d in donations
        if d.recipient_name == "Against Malaria Foundation" and d.date.month == 1
    )
    assert amf_jan.date == date(2026, 1, 7)


def test_category_joins_main_and_sub(donations: list[Donation]) -> None:
    givewell = next(d for d in donations if d.recipient_name == "GiveWell Inc")
    assert givewell.category == "Spenden / Internationale Hilfe"


def test_source_id_is_deterministic_and_stable() -> None:
    a = FinanzguruSource().load_donations(FIXTURE)
    b = FinanzguruSource().load_donations(FIXTURE)
    assert [d.source_id for d in a] == [d.source_id for d in b]


def test_duplicate_looking_rows_get_distinct_source_ids(donations: list[Donation]) -> None:
    # The fixture has two identical Wikimedia rows on 2026-02-20, €10. They must
    # parse as two separate donations with distinct source_ids.
    wiki = [d for d in donations if d.recipient_name == "Wikimedia Foerderverein"]
    assert len(wiki) == 2
    assert wiki[0].source_id != wiki[1].source_id


# --------------------------------------------------------------------------- #
# Configuration and normalization
# --------------------------------------------------------------------------- #

def test_payee_normalization_applies() -> None:
    config = FinanzguruConfig(
        payee_normalization={"GiveWell Inc": "GiveWell"}
    )
    donations = FinanzguruSource(config).load_donations(FIXTURE)
    assert any(d.recipient_name == "GiveWell" for d in donations)
    assert not any(d.recipient_name == "GiveWell Inc" for d in donations)


def test_subcategory_filter_narrows_results() -> None:
    config = FinanzguruConfig(donation_subcategories=["Bildung"])
    donations = FinanzguruSource(config).load_donations(FIXTURE)
    assert {d.recipient_name for d in donations} == {"Wikimedia Foerderverein"}


def test_changing_donation_categories_drops_all_donations() -> None:
    config = FinanzguruConfig(donation_categories=["Wohnen"])
    donations = FinanzguruSource(config).load_donations(FIXTURE)
    assert donations == []


# --------------------------------------------------------------------------- #
# Tolerance to alternate column headers
# --------------------------------------------------------------------------- #

def test_accepts_umlaut_payee_column(tmp_path: Path) -> None:
    csv = tmp_path / "umlaut.csv"
    csv.write_text(
        "Datum;Begünstigter/Zahlungspflichtiger;Verwendungszweck;Betrag;"
        "Hauptkategorie;Unterkategorie;Vertrag\n"
        "07.01.2026;AMF;Spende;-50,00;Spenden;Internationale Hilfe;Monatsspende\n",
        encoding="utf-8",
    )
    donations = FinanzguruSource().load_donations(csv)
    assert len(donations) == 1
    assert donations[0].recipient_name == "AMF"
    assert donations[0].is_recurring is True


def test_missing_required_column_raises_clear_error(tmp_path: Path) -> None:
    csv = tmp_path / "broken.csv"
    csv.write_text("foo;bar;baz\n1;2;3\n", encoding="utf-8")
    with pytest.raises(DataSourceError) as exc:
        FinanzguruSource().load_donations(csv)
    assert "missing required columns" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# Low-level parsers
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("-50,00", Decimal("-50.00")),
        ("-50.00", Decimal("-50.00")),
        ("3.200,00", Decimal("3200.00")),
        ("3,200.00", Decimal("3200.00")),
        ("  -7,80 ", Decimal("-7.80")),
        ("−0,01", Decimal("-0.01")),  # unicode minus
        ("100", Decimal("100")),
    ],
)
def test_parse_amount(raw: str, expected: Decimal) -> None:
    assert _parse_amount(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("07.01.2026", date(2026, 1, 7)),
        ("2026-01-07", date(2026, 1, 7)),
    ],
)
def test_parse_date(raw: str, expected: date) -> None:
    assert _parse_date(raw) == expected


def test_parse_amount_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        _parse_amount("not-a-number")


def test_parse_date_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        _parse_date("31/31/2026")
