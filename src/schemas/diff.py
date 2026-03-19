"""Schemas for bill version diffing and change classification."""

from typing import Literal

from pydantic import BaseModel, Field


class SectionDelta(BaseModel):
    """Comparison result for a single section between two versions."""

    section_id: str
    old_heading: str | None = None
    new_heading: str | None = None
    delta_type: Literal["added", "removed", "modified", "unchanged"]
    old_text: str | None = None
    new_text: str | None = None
    similarity_score: float = Field(ge=0, le=1)


class ChangeEvent(BaseModel):
    """A classified change detected in the diff."""

    change_flag: str
    section_id: str | None = None
    old_text_summary: str
    new_text_summary: str
    practical_effect: str
    confidence: float = Field(ge=0, le=1)


class BillDiffResult(BaseModel):
    """Full diff result between two versions of a bill."""

    bill_id: str
    current_version_id: str
    prior_version_id: str | None = None
    compared_against: Literal["prior_file_copy", "prior_bill_text", "none"]
    sections_added: int = Field(ge=0)
    sections_removed: int = Field(ge=0)
    sections_modified: int = Field(ge=0)
    section_deltas: list[SectionDelta]
    change_events: list[ChangeEvent]
    effective_date_old: str | None = None
    effective_date_new: str | None = None
