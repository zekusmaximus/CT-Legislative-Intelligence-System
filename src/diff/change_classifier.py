"""Change event classifier.

Analyzes SectionDeltas to produce ChangeEvent objects with
classified change flags per technical contract §11.2.
"""

import re

from src.schemas.diff import BillDiffResult, ChangeEvent, SectionDelta

# Change flag definitions
CHANGE_FLAGS = {
    "effective_date_change": "Effective date modified",
    "new_section_added": "New section added to bill",
    "section_removed": "Section removed from bill",
    "definition_change": "Definitions modified",
    "appropriation_change": "Funding or appropriation modified",
    "penalty_change": "Penalties or enforcement modified",
    "regulatory_change": "Regulatory requirements modified",
    "scope_change": "Scope of applicability modified",
    "substantive_amendment": "Substantive text changes",
    "technical_correction": "Minor/technical correction",
}

_EFFECTIVE_DATE_RE = re.compile(
    r"(effective|take[s]?\s+effect|shall\s+be\s+effective)",
    re.IGNORECASE,
)
_DEFINITION_RE = re.compile(
    r'("[\w\s]+" means|as used in this|for purposes of)',
    re.IGNORECASE,
)
_APPROPRIATION_RE = re.compile(
    r"(appropriat|allocat|sum of|general fund|special fund)",
    re.IGNORECASE,
)
_PENALTY_RE = re.compile(
    r"(penalty|penalt|fine|imprison|infraction|violation|enforce)",
    re.IGNORECASE,
)
_REGULATORY_RE = re.compile(
    r"(regulat|permit|license|certif|compliance|inspect|audit)",
    re.IGNORECASE,
)


def classify_changes(diff_result: BillDiffResult) -> list[ChangeEvent]:
    """Analyze section deltas and produce classified change events."""
    events: list[ChangeEvent] = []

    for delta in diff_result.section_deltas:
        if delta.delta_type == "unchanged":
            continue

        delta_events = _classify_delta(delta)
        events.extend(delta_events)

    return events


def _classify_delta(delta: SectionDelta) -> list[ChangeEvent]:
    """Classify a single section delta into change events."""
    events: list[ChangeEvent] = []

    if delta.delta_type == "added":
        events.append(
            ChangeEvent(
                change_flag="new_section_added",
                section_id=delta.section_id,
                old_text_summary="",
                new_text_summary=_summarize(delta.new_text or ""),
                practical_effect="New legislative language added",
                confidence=0.9,
            )
        )
        # Check for specific content in added section
        events.extend(_detect_content_flags(delta, delta.new_text or ""))

    elif delta.delta_type == "removed":
        events.append(
            ChangeEvent(
                change_flag="section_removed",
                section_id=delta.section_id,
                old_text_summary=_summarize(delta.old_text or ""),
                new_text_summary="",
                practical_effect="Legislative language removed",
                confidence=0.9,
            )
        )

    elif delta.delta_type == "modified":
        old = delta.old_text or ""
        new = delta.new_text or ""

        # Check if it's just a technical correction
        if delta.similarity_score > 0.90:
            events.append(
                ChangeEvent(
                    change_flag="technical_correction",
                    section_id=delta.section_id,
                    old_text_summary=_summarize(old),
                    new_text_summary=_summarize(new),
                    practical_effect="Minor textual changes",
                    confidence=0.8,
                )
            )
        else:
            events.append(
                ChangeEvent(
                    change_flag="substantive_amendment",
                    section_id=delta.section_id,
                    old_text_summary=_summarize(old),
                    new_text_summary=_summarize(new),
                    practical_effect="Substantive changes to section",
                    confidence=0.7,
                )
            )

        # Detect specific content changes
        events.extend(_detect_content_change_flags(delta, old, new))

    return events


def _detect_content_flags(delta: SectionDelta, text: str) -> list[ChangeEvent]:
    """Detect content-specific flags in new text."""
    events: list[ChangeEvent] = []

    checks = [
        (_EFFECTIVE_DATE_RE, "effective_date_change", "Contains effective date"),
        (_DEFINITION_RE, "definition_change", "Contains definitions"),
        (_APPROPRIATION_RE, "appropriation_change", "Contains appropriation"),
        (_PENALTY_RE, "penalty_change", "Contains penalty provisions"),
        (_REGULATORY_RE, "regulatory_change", "Contains regulatory provisions"),
    ]

    for pattern, flag, effect in checks:
        if pattern.search(text):
            events.append(
                ChangeEvent(
                    change_flag=flag,
                    section_id=delta.section_id,
                    old_text_summary="",
                    new_text_summary=_summarize(text),
                    practical_effect=effect,
                    confidence=0.7,
                )
            )

    return events


def _detect_content_change_flags(delta: SectionDelta, old: str, new: str) -> list[ChangeEvent]:
    """Detect when specific content types changed between versions."""
    events: list[ChangeEvent] = []

    checks = [
        (_EFFECTIVE_DATE_RE, "effective_date_change", "Effective date language changed"),
        (_DEFINITION_RE, "definition_change", "Definitions changed"),
        (_APPROPRIATION_RE, "appropriation_change", "Appropriation language changed"),
        (_PENALTY_RE, "penalty_change", "Penalty provisions changed"),
        (_REGULATORY_RE, "regulatory_change", "Regulatory provisions changed"),
    ]

    for pattern, flag, effect in checks:
        old_match = bool(pattern.search(old))
        new_match = bool(pattern.search(new))
        if old_match or new_match:
            if old_match != new_match or (old_match and new_match):
                events.append(
                    ChangeEvent(
                        change_flag=flag,
                        section_id=delta.section_id,
                        old_text_summary=_summarize(old),
                        new_text_summary=_summarize(new),
                        practical_effect=effect,
                        confidence=0.6,
                    )
                )

    return events


def _summarize(text: str, max_len: int = 200) -> str:
    """Create a brief summary of text for change event display."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "..."
