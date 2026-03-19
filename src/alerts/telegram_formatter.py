"""Telegram alert message formatter.

Formats ClientScoreResult + summary into TelegramAlertPayload
and plain-text message suitable for Telegram's MarkdownV2.
"""

import hashlib

from src.schemas.scoring import ClientScoreResult
from src.schemas.summary import InternalSummary, TelegramAlertPayload

CGA_BASE_URL = "https://www.cga.ct.gov"

# Urgency display labels
_URGENCY_EMOJI = {
    "critical": "RED",
    "high": "ORANGE",
    "medium": "YELLOW",
    "low": "GREEN",
}


def build_alert_payload(
    score: ClientScoreResult,
    summary: InternalSummary,
    file_copy_pdf_url: str,
    bill_status_url: str | None = None,
) -> TelegramAlertPayload:
    """Build a TelegramAlertPayload from scoring and summary."""
    alert_text = format_alert_text(score, summary)

    suppression_key = hashlib.sha256(
        f"{score.client_id}:{score.version_id}".encode()
    ).hexdigest()[:16]

    return TelegramAlertPayload(
        client_id=score.client_id,
        bill_id=score.bill_id,
        version_id=score.version_id,
        urgency=score.urgency,
        alert_text=alert_text,
        file_copy_url=file_copy_pdf_url,
        bill_status_url=bill_status_url,
        suppression_key=suppression_key,
    )


def format_alert_text(
    score: ClientScoreResult,
    summary: InternalSummary,
) -> str:
    """Format a plain-text alert message."""
    urgency_label = _URGENCY_EMOJI.get(score.urgency, "INFO")
    lines = [
        f"[{urgency_label}] Legislative Alert",
        f"Bill: {score.bill_id}",
        f"Score: {score.final_score:.0f}/100 | Urgency: {score.urgency}",
        "",
        summary.one_sentence_summary,
        "",
    ]

    if summary.practical_takeaways:
        lines.append("Key points:")
        for takeaway in summary.practical_takeaways[:3]:
            lines.append(f"  - {takeaway}")
        lines.append("")

    if score.match_reasons:
        lines.append("Why this matters:")
        for reason in score.match_reasons[:3]:
            lines.append(f"  - {reason.reason_text}")

    return "\n".join(lines)


def format_telegram_markdown(
    score: ClientScoreResult,
    summary: InternalSummary,
    pdf_url: str,
) -> str:
    """Format for Telegram MarkdownV2 (escaped)."""
    bill = _escape_md(score.bill_id)
    urgency = _escape_md(score.urgency.upper())
    one_line = _escape_md(summary.one_sentence_summary)
    score_val = _escape_md(f"{score.final_score:.0f}")

    lines = [
        f"*\\[{urgency}\\] {bill}*",
        f"Score: {score_val}/100",
        "",
        one_line,
        "",
        f"[View PDF]({pdf_url})",
    ]

    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    for char in special:
        text = text.replace(char, f"\\{char}")
    return text
