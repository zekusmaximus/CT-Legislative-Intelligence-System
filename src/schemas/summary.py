"""Schemas for summaries and alert payloads."""

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class InternalSummary(BaseModel):
    """Internal review summary for a bill version."""

    bill_id: str
    version_id: str
    one_sentence_summary: str
    deep_summary: str
    key_sections_to_review: list[str]
    practical_takeaways: list[str]
    confidence: float = Field(ge=0, le=1)


class TelegramAlertPayload(BaseModel):
    """Payload for sending a Telegram alert."""

    client_id: str
    bill_id: str
    version_id: str
    urgency: Literal["low", "medium", "high", "critical"]
    alert_text: str
    file_copy_url: HttpUrl
    bill_status_url: HttpUrl | None = None
    suppression_key: str
