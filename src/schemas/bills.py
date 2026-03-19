"""Schemas for bill and file-copy records."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class BillRecord(BaseModel):
    """Normalized bill record."""

    session_year: int
    bill_id: str = Field(pattern=r"^(HB|SB)\d{5}$")
    chamber: Literal["house", "senate"]
    bill_number_numeric: int
    current_title: str
    committee_name: str | None = None
    bill_status_url: HttpUrl | None = None
    last_seen_at: datetime


class FileCopyRecord(BaseModel):
    """A specific file copy (version) of a bill."""

    session_year: int
    bill_id: str = Field(pattern=r"^(HB|SB)\d{5}$")
    file_copy_number: int = Field(ge=1)
    canonical_version_id: str = Field(pattern=r"^\d{4}-(HB|SB)\d{5}-FC\d{5}$")
    pdf_url: HttpUrl
    pdf_sha256: str
    local_pdf_path: str | None = None
    page_count: int | None = None
    discovered_at: datetime
    extracted_at: datetime | None = None
