"""Schemas for PDF text extraction and section parsing."""

from typing import Literal

from pydantic import BaseModel, Field


class PageText(BaseModel):
    """Extracted text from a single PDF page."""

    page_number: int = Field(ge=1)
    raw_text: str
    cleaned_text: str
    extraction_method: Literal["text", "ocr"]
    extraction_confidence: float = Field(ge=0, le=1)


class SectionSpan(BaseModel):
    """A detected legislative section within the document."""

    section_id: str
    heading: str
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    text: str


class ExtractedDocument(BaseModel):
    """Full extraction result for a file copy."""

    canonical_version_id: str
    pages: list[PageText]
    full_raw_text: str
    full_cleaned_text: str
    sections: list[SectionSpan]
    overall_extraction_confidence: float = Field(ge=0, le=1)
    extraction_warnings: list[str] = []
