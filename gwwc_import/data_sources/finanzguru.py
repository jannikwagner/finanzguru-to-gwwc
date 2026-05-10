"""Finanzguru CSV / XLSX export parser.

Reads a Finanzguru export, filters donation rows by `Hauptkategorie`
(and optionally `Unterkategorie`), and yields normalized `Donation`
objects.

Real Finanzguru exports vary slightly across locales, app versions, and
account types. This module therefore:

* accepts both German-locale (`;` separator, `,` decimal) and US-style
  CSVs, and `.xlsx` files;
* matches columns by an explicit alias map and raises a clear
  `DataSourceError` listing the columns it actually saw if no candidate
  matches, instead of silently producing empty fields;
* parses `Betrag` defensively (handles `-50,00`, `-50.00`, `3.200,00`,
  unicode minus);
* derives `source_id` deterministically from the source fields plus a
  per-export ordinal so genuinely-distinct duplicate-looking rows still
  get distinct IDs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

import pandas as pd
from pydantic import BaseModel, Field

from gwwc_import.data_sources.base import DataSourceError
from gwwc_import.models import Donation

SOURCE_SYSTEM = "finanzguru"

# Logical field name -> list of column-header candidates seen in real exports.
# Order matters: earlier candidates are preferred.
COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["Buchungstag", "Datum", "Wertstellungstag"],
    "payee": [
        "Beguenstigter/Auftraggeber",
        "Begünstigter/Auftraggeber",
        "Beguenstigter/Zahlungspflichtiger",
        "Begünstigter/Zahlungspflichtiger",
        "Empfaenger",
        "Empfänger",
    ],
    "purpose": ["Verwendungszweck", "Zweck", "Buchungstext"],
    "amount": ["Betrag", "Umsatz"],
    "main_category": ["Hauptkategorie", "Kategorie"],
    "sub_category": ["Unterkategorie", "Subkategorie"],
    "contract": ["Vertrag", "Vertragsname"],
    "account": ["Name Referenzkonto", "Konto", "Kontoname"],
}

REQUIRED_LOGICAL = {"date", "payee", "purpose", "amount", "main_category"}


class FinanzguruConfig(BaseModel):
    """Configuration for `FinanzguruSource`."""

    donation_categories: list[str] = Field(default_factory=lambda: ["Spenden"])
    donation_subcategories: list[str] | None = None
    currency: str = "EUR"
    payee_normalization: dict[str, str] = Field(default_factory=dict)
    # utf-8-sig strips the BOM that Windows / Finanzguru sometimes emits;
    # falls back transparently for plain UTF-8. Use "latin-1" or "cp1252" if
    # your export was generated on an older Windows system.
    encoding: str = "utf-8-sig"

    @classmethod
    def from_env(cls) -> FinanzguruConfig:
        """Build a config from environment variables (call after dotenv.load_dotenv)."""
        import os

        cats_raw = os.environ.get("FINANZGURU_DONATION_CATEGORIES", "Spenden")
        categories = [c.strip() for c in cats_raw.split(",") if c.strip()]
        return cls(
            donation_categories=categories,
            currency=os.environ.get("FINANZGURU_CURRENCY", "EUR"),
            encoding=os.environ.get("FINANZGURU_ENCODING", "utf-8-sig"),
        )


class FinanzguruSource:
    """Concrete `DonationSource` for Finanzguru exports."""

    def __init__(self, config: FinanzguruConfig | None = None) -> None:
        self.config = config or FinanzguruConfig()

    @classmethod
    def from_env(cls) -> FinanzguruSource:
        """Build a fully-configured source from environment variables.

        Used by `cli._build_source` so the CLI doesn't need per-source
        knowledge — every registered source just exposes `from_env()`.
        """
        return cls(FinanzguruConfig.from_env())

    def load_donations(self, path: Path) -> list[Donation]:
        path = Path(path)
        df = _read_table(path, encoding=self.config.encoding)
        col_map = _resolve_columns(df.columns)

        donations: list[Donation] = []
        seen_keys: dict[tuple[str, str, str, str], int] = {}

        for raw in cast(list[dict[str, object]], df.to_dict(orient="records")):
            row = {logical: _cell(raw, col) for logical, col in col_map.items()}

            if not self._is_donation_row(row):
                continue

            try:
                booking_date = _parse_date(row["date"])
                signed_amount = _parse_amount(row["amount"])
            except ValueError as e:
                raise DataSourceError(
                    f"Could not parse a Finanzguru row: {e}. "
                    "Check the export's date and amount columns."
                ) from e

            payee_raw = row["payee"].strip()
            payee = self.config.payee_normalization.get(payee_raw, payee_raw)
            purpose = row["purpose"].strip()

            key = (row["date"].strip(), str(signed_amount), payee_raw, purpose)
            ordinal = seen_keys.get(key, 0)
            seen_keys[key] = ordinal + 1

            source_id = _hash_id(*key, ordinal=ordinal)
            category = _join_category(row.get("main_category"), row.get("sub_category"))

            donations.append(
                Donation(
                    source_system=SOURCE_SYSTEM,
                    source_id=source_id,
                    date=booking_date,
                    amount=abs(signed_amount),
                    currency=self.config.currency,
                    recipient_name=payee,
                    description=purpose,
                    is_recurring=bool(row.get("contract", "").strip()),
                    category=category,
                    notes=None,
                )
            )

        return donations

    def _is_donation_row(self, row: dict[str, str]) -> bool:
        main = row.get("main_category", "").strip()
        if main not in self.config.donation_categories:
            return False
        if self.config.donation_subcategories is not None:
            sub = row.get("sub_category", "").strip()
            if sub not in self.config.donation_subcategories:
                return False
        return True


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _read_table(path: Path, encoding: str = "utf-8-sig") -> pd.DataFrame:
    """Read a Finanzguru CSV/XLSX as strings (no implicit type coercion).

    `encoding` defaults to `utf-8-sig` which strips the UTF-8 BOM that
    Windows and some Finanzguru builds emit, while being transparent for
    plain UTF-8 files.  Set `FinanzguruConfig.encoding = "latin-1"` for
    older Windows exports in a Western European code page.
    """
    if not path.exists():
        raise DataSourceError(f"Finanzguru export not found: {path}")

    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
    elif suffix == ".csv":
        sep = _sniff_csv_separator(path, encoding=encoding)
        df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding=encoding)
    else:
        raise DataSourceError(
            f"Unsupported Finanzguru export extension: {suffix!r}. Expected .csv, .xlsx, or .xls."
        )
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _sniff_csv_separator(path: Path, encoding: str = "utf-8-sig") -> str:
    """Return the most likely CSV separator (German `;` vs. US `,`)."""
    with path.open("r", encoding=encoding) as f:
        head = f.readline()
    return ";" if head.count(";") >= head.count(",") and ";" in head else ","


def _resolve_columns(columns: Iterable[str]) -> dict[str, str]:
    cols = list(columns)
    resolved: dict[str, str] = {}
    for logical, candidates in COLUMN_ALIASES.items():
        for cand in candidates:
            if cand in cols:
                resolved[logical] = cand
                break

    missing = REQUIRED_LOGICAL - set(resolved)
    if missing:
        raise DataSourceError(
            f"Finanzguru export is missing required columns for: {sorted(missing)}. "
            f"Found columns: {cols}"
        )
    return resolved


def _cell(row: dict[str, object], column: str) -> str:
    """Return cell value as a stripped string, treating NaN/None as ''."""
    value = row.get(column, "")
    if value is None:
        return ""
    s = str(value)
    if s.lower() == "nan":
        return ""
    return s


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    if not raw:
        raise ValueError("empty date")
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date format: {raw!r}")


def _parse_amount(raw: str) -> Decimal:
    """Parse a Finanzguru amount string into a signed Decimal.

    Tolerates German (`-50,00`, `3.200,00`), US (`-50.00`, `3,200.00`),
    spaces, and unicode minus.
    """
    if raw is None:
        raise ValueError("empty amount")
    s = str(raw).strip().replace(" ", "").replace("−", "-")  # noqa: RUF001
    if not s:
        raise ValueError("empty amount")
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    if last_comma > last_dot:
        s = s.replace(".", "").replace(",", ".")
    elif last_dot > last_comma and "," in s:
        s = s.replace(",", "")
    try:
        return Decimal(s)
    except InvalidOperation as e:
        raise ValueError(f"invalid amount: {raw!r}") from e


def _hash_id(date_str: str, amount_str: str, payee: str, purpose: str, ordinal: int) -> str:
    payload = "|".join([date_str, amount_str, payee, purpose, str(ordinal)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _join_category(main: str | None, sub: str | None) -> str | None:
    main = (main or "").strip()
    sub = (sub or "").strip()
    if main and sub:
        return f"{main} / {sub}"
    return main or sub or None
