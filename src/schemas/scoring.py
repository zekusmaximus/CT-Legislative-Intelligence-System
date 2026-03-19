"""Schemas for subject tagging and client relevance scoring."""

from typing import Literal

from pydantic import BaseModel, Field


class SubjectTagResult(BaseModel):
    """Subject tags and change flags assigned to a bill version."""

    bill_id: str
    version_id: str
    subject_tags: list[str]
    change_flags: list[str]
    tag_confidence: float = Field(ge=0, le=1)
    rationale: list[str]


class ClientMatchReason(BaseModel):
    """A single reason why a bill matched a client profile."""

    reason_code: Literal[
        "keyword_match",
        "agency_match",
        "committee_match",
        "subject_match",
        "change_flag_match",
        "embedding_match",
        "llm_relevance_reason",
        "watched_bill",
    ]
    reason_text: str
    weight: float


class ClientScoreResult(BaseModel):
    """Final relevance score for a client–bill pair."""

    client_id: str
    bill_id: str
    version_id: str
    rules_score: float = Field(ge=0, le=100)
    embedding_score: float = Field(ge=0, le=100, default=0.0)
    llm_score: float = Field(ge=0, le=100, default=0.0)
    final_score: float = Field(ge=0, le=100)
    urgency: Literal["low", "medium", "high", "critical"]
    should_alert: bool
    alert_disposition: Literal[
        "no_alert",
        "digest",
        "immediate",
        "suppressed_duplicate",
        "suppressed_below_threshold",
        "suppressed_cooldown",
    ]
    match_reasons: list[ClientMatchReason]
