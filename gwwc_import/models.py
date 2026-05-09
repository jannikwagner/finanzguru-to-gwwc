"""Normalized data model shared by data sources and the automation layer."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Donation(BaseModel):
    """A normalized donation, source-agnostic.

    `amount` is a Decimal so euro/cent values round-trip without binary-float
    drift before they are written into the EA.org form.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    source_system: str
    source_id: str = Field(min_length=1)
    date: date
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(min_length=3, max_length=3)
    recipient_name: str = Field(min_length=1)
    description: str = ""
    is_recurring: bool = False
    category: str | None = None
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper()
