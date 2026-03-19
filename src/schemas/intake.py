"""Schemas for source page and file-copy listing intake."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SourcePageRecord(BaseModel):
    """Record of a fetched CGA source page."""

    source_type: Literal["daily_filecopies", "all_filecopies", "bill_status"]
    source_url: HttpUrl
    fetched_at: datetime
    content_sha256: str
    http_status: int
    session_year: int


class FileCopyListingRow(BaseModel):
    """A single row parsed from a CGA file-copy listing page."""

    session_year: int
    bill_id: str = Field(pattern=r"^(HB|SB)\d{5}$")
    bill_number_display: str
    bill_title: str
    file_copy_number: int = Field(ge=1)
    file_copy_pdf_url: HttpUrl
    listing_date: date
    listing_source_url: HttpUrl
