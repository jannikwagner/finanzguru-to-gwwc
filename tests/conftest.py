"""Shared pytest fixtures."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from openpyxl import Workbook

CSV_FIXTURE = Path(__file__).parent / "fixtures" / "finanzguru_dummy.csv"


@pytest.fixture(scope="session")
def xlsx_fixture(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Materialise an XLSX equivalent of the CSV fixture.

    We don't commit a binary fixture to the repo: the XLSX is generated on
    the fly so it always tracks the CSV's contents, and it exercises the
    `pd.read_excel` path in `FinanzguruSource`.
    """
    out = tmp_path_factory.mktemp("fixtures") / "finanzguru_dummy.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Umsätze"

    with CSV_FIXTURE.open("r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            ws.append(row)

    wb.save(out)
    return out
