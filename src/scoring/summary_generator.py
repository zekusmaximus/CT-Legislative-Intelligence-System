"""Summary generator for bill versions.

Generates internal summaries from extracted document content.
This is the rules-based layer; LLM enhancement is a future pass.
"""

from src.schemas.diff import BillDiffResult
from src.schemas.extraction import ExtractedDocument
from src.schemas.summary import InternalSummary


def generate_summary(
    doc: ExtractedDocument,
    diff_result: BillDiffResult | None = None,
    bill_title: str = "",
) -> InternalSummary:
    """Generate an internal summary for a bill version."""
    one_sentence = _generate_one_sentence(bill_title, doc, diff_result)
    deep = _generate_deep_summary(doc, diff_result)
    key_sections = _identify_key_sections(doc, diff_result)
    takeaways = _generate_takeaways(doc, diff_result)

    # Confidence based on extraction quality and diff availability
    confidence = doc.overall_extraction_confidence * 0.7
    if diff_result:
        confidence += 0.2
    if bill_title:
        confidence += 0.1
    confidence = min(1.0, confidence)

    return InternalSummary(
        bill_id=doc.canonical_version_id.rsplit("-", 1)[0]
        if "-" in doc.canonical_version_id
        else doc.canonical_version_id,
        version_id=doc.canonical_version_id,
        one_sentence_summary=one_sentence,
        deep_summary=deep,
        key_sections_to_review=key_sections,
        practical_takeaways=takeaways,
        confidence=confidence,
    )


def _generate_one_sentence(
    title: str,
    doc: ExtractedDocument,
    diff: BillDiffResult | None,
) -> str:
    """Generate a one-sentence summary."""
    if diff and diff.compared_against != "none":
        changes = []
        if diff.sections_added > 0:
            changes.append(f"{diff.sections_added} section(s) added")
        if diff.sections_removed > 0:
            changes.append(f"{diff.sections_removed} section(s) removed")
        if diff.sections_modified > 0:
            changes.append(f"{diff.sections_modified} section(s) modified")

        if changes:
            change_str = ", ".join(changes)
            if title:
                return f"{title} — updated with {change_str}."
            return f"Bill updated with {change_str}."

    if title:
        section_count = len(doc.sections)
        return f"{title} ({section_count} section(s))."
    return f"Bill with {len(doc.sections)} section(s)."


def _generate_deep_summary(
    doc: ExtractedDocument,
    diff: BillDiffResult | None,
) -> str:
    """Generate a detailed summary."""
    parts: list[str] = []

    # Summarize each section briefly
    for section in doc.sections[:10]:  # Cap at 10 sections
        heading = section.heading
        text_preview = section.text[:150].replace("\n", " ").strip()
        if len(section.text) > 150:
            text_preview += "..."
        parts.append(f"**{heading}**: {text_preview}")

    if len(doc.sections) > 10:
        parts.append(
            f"... and {len(doc.sections) - 10} additional section(s)."
        )

    # Add diff summary
    if diff and diff.compared_against != "none":
        diff_parts = []
        for delta in diff.section_deltas:
            if delta.delta_type == "added":
                diff_parts.append(f"- Added: {delta.new_heading}")
            elif delta.delta_type == "removed":
                diff_parts.append(f"- Removed: {delta.old_heading}")
            elif delta.delta_type == "modified":
                diff_parts.append(
                    f"- Modified: {delta.new_heading} "
                    f"(similarity: {delta.similarity_score:.0%})"
                )
        if diff_parts:
            parts.append("\n**Changes from prior version:**")
            parts.extend(diff_parts)

    return "\n\n".join(parts)


def _identify_key_sections(
    doc: ExtractedDocument,
    diff: BillDiffResult | None,
) -> list[str]:
    """Identify sections that need human review."""
    key: list[str] = []

    # Changed sections are always key
    if diff:
        for delta in diff.section_deltas:
            if delta.delta_type in ("added", "modified"):
                heading = delta.new_heading or delta.section_id
                key.append(heading)

    # Sections with key content are important
    import re

    for section in doc.sections:
        text_lower = section.text.lower()
        if re.search(r"effective|take[s]?\s+effect", text_lower):
            if section.heading not in key:
                key.append(section.heading)
        if re.search(r"appropriat|general fund", text_lower):
            if section.heading not in key:
                key.append(section.heading)

    return key[:10]  # Cap at 10


def _generate_takeaways(
    doc: ExtractedDocument,
    diff: BillDiffResult | None,
) -> list[str]:
    """Generate practical takeaway bullet points."""
    takeaways: list[str] = []

    if diff:
        if diff.sections_added > 0:
            takeaways.append(
                f"{diff.sections_added} new section(s) added — "
                "review for new requirements or provisions."
            )
        if diff.sections_removed > 0:
            takeaways.append(
                f"{diff.sections_removed} section(s) removed — "
                "check if previously tracked provisions are affected."
            )
        if diff.sections_modified > 0:
            takeaways.append(
                f"{diff.sections_modified} section(s) substantively "
                "modified — compare against prior version."
            )

        for event in diff.change_events[:5]:
            if event.change_flag in (
                "effective_date_change",
                "appropriation_change",
            ):
                takeaways.append(
                    f"{event.change_flag}: {event.practical_effect}"
                )

    if not takeaways:
        takeaways.append(
            f"New bill with {len(doc.sections)} section(s) — "
            "initial review recommended."
        )

    return takeaways[:5]  # Cap at 5
