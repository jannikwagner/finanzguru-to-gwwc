"""Common protocol every data source must implement."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from gwwc_import.models import Donation


class DataSourceError(Exception):
    """Raised when a source export cannot be parsed (e.g. missing columns)."""


@runtime_checkable
class DonationSource(Protocol):
    """Loads and normalizes donations from a single export file."""

    def load_donations(self, path: Path) -> list[Donation]:
        ...
