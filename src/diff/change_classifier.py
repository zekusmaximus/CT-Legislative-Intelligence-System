"""Change event classifier.

Analyzes SectionDeltas to produce ChangeEvent objects with
classified change flags per the controlled vocabulary in
config/taxonomy.change_flags.yaml.
"""

import re

from src.metadata.taxonomy import load_change_flags, validate_change_flags
from src.schemas.diff import BillDiffResult, ChangeEvent, SectionDelta

# Map old non-canonical flag names used internally to canonical flags.
# The canonical flags come from config/taxonomy.change_flags.yaml.

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
    r"(penalty|penalt|fine|imprison|infraction|violation)",
    re.IGNORECASE,
)
_ENFORCEMENT_RE = re.compile(
    r"(enforce|enforcement|attorney general|inspector)",
    re.IGNORECASE,
)
_LICENSING_RE = re.compile(
    r"(licens|permit|certif|registration required)",
    re.IGNORECASE,
)
_REGULATORY_RE = re.compile(
    r"(regulat|compliance|inspect|audit)",
    re.IGNORECASE,
)
_EXEMPTION_RE = re.compile(
    r"(exempt|exclusion|shall not apply|does not apply)",
    re.IGNORECASE,
)
_SCOPE_RE = re.compile(
    r"(scope|applicability|shall apply to|subject to this)",
    re.IGNORECASE,
)
_REPORTING_RE = re.compile(
    r"(report|reporting requirement|shall submit|annual report)",
    re.IGNORECASE,
)
_DEADLINE_RE = re.compile(
    r"(deadline|not later than|on or before|within \d+ days)",
    re.IGNORECASE,
)
_FUNDING_RE = re.compile(
    r"(fund|funding|grant|bond|revenue)",
    re.IGNORECASE,
)
_RULEMAKING_RE = re.compile(
    r"(rulemaking|adopt regulations|promulgate|regulatory authority)",
    re.IGNORECASE,
)
_MANDATE_RE = re.compile(
    r"(shall|must|required to|mandate|obligat)",
    re.IGNORECASE,
)
_SUNSET_RE = re.compile(
    r"(sunset|repeal|terminat.*provision|expire[sd]?)",
    re.IGNORECASE,
)
_PREEMPTION_RE = re.compile(
    r"(preempt|supersede|notwithstanding.*local|federal law)",
    re.IGNORECASE,
)
_PRIVATE_ACTION_RE = re.compile(
    r"(private right of action|private cause of action|may bring an action|civil remedy)",
    re.IGNORECASE,
)
_REIMBURSEMENT_RE = re.compile(
    r"(reimburs|rate setting|payment rate|provider rate|fee schedule)",
    re.IGNORECASE,
)
_ELIGIBILITY_RE = re.compile(
    r"(eligib|qualify|qualification|eligible|meets the criteria)",
    re.IGNORECASE,
)


def classify_changes(diff_result: BillDiffResult) -> list[ChangeEvent]:
    """Analyze section deltas and produce classified change events.

    All emitted change_flag values are validated against the controlled
    vocabulary. Raises InvalidTaxonomyValueError if any flag is invalid.
    """
    events: list[ChangeEvent] = []

    for delta in diff_result.section_deltas:
        if delta.delta_type == "unchanged":
            continue
        delta_events = _classify_delta(delta)
        events.extend(delta_events)

    # Validate all emitted flags before returning
    flags = [e.change_flag for e in events]
    validate_change_flags(flags)

    return events


def _classify_delta(delta: SectionDelta) -> list[ChangeEvent]:
    """Classify a single section delta into change events."""
    events: list[ChangeEvent] = []

    if delta.delta_type == "added":
        events.append(
            _make_event(
                "section_added",
                delta,
                old_summary="",
                new_summary=_summarize(delta.new_text or ""),
                effect="New legislative language added",
                confidence=0.9,
            )
        )
        # Check for specific content in added section
        events.extend(_detect_added_content_flags(delta, delta.new_text or ""))

    elif delta.delta_type == "removed":
        events.append(
            _make_event(
                "section_removed",
                delta,
                old_summary=_summarize(delta.old_text or ""),
                new_summary="",
                effect="Legislative language removed",
                confidence=0.9,
            )
        )

    elif delta.delta_type == "modified":
        old = delta.old_text or ""
        new = delta.new_text or ""

        # Detect specific content changes in modified sections
        events.extend(_detect_modified_content_flags(delta, old, new))

        # If no specific flags were detected, classify generically
        if not events:
            if delta.similarity_score > 0.95:
                # Truly minor change (typo-level) — skip
                pass
            else:
                # Check for scope changes as a fallback for substantive mods
                events.extend(_detect_scope_flags(delta, old, new))

    return events


def _detect_added_content_flags(
    delta: SectionDelta, text: str
) -> list[ChangeEvent]:
    """Detect content-specific flags in newly added text."""
    events: list[ChangeEvent] = []

    checks: list[tuple[re.Pattern[str], str, str]] = [
        (_EFFECTIVE_DATE_RE, "effective_date_changed", "Contains effective date language"),
        (_DEFINITION_RE, "definition_changed", "Contains definitions"),
        (_APPROPRIATION_RE, "appropriation_added", "Contains appropriation language"),
        (_PENALTY_RE, "penalty_added", "Contains penalty provisions"),
        (_ENFORCEMENT_RE, "enforcement_changed", "Contains enforcement provisions"),
        (_LICENSING_RE, "licensing_requirement_added", "Contains licensing requirements"),
        (_EXEMPTION_RE, "exemption_added", "Contains exemption language"),
        (_REPORTING_RE, "reporting_requirement_added", "Contains reporting requirement"),
        (_DEADLINE_RE, "deadline_changed", "Contains deadline language"),
        (_FUNDING_RE, "funding_language_added", "Contains funding language"),
        (_RULEMAKING_RE, "rulemaking_authority_added", "Contains rulemaking authority"),
        (_MANDATE_RE, "mandate_added", "Contains mandate language"),
        (_SUNSET_RE, "sunset_added", "Contains sunset provision"),
        (_PREEMPTION_RE, "preemption_risk", "Contains preemption language"),
        (_PRIVATE_ACTION_RE, "private_right_of_action_added", "Contains private right of action"),
        (_REIMBURSEMENT_RE, "reimbursement_changed", "Contains reimbursement language"),
        (_ELIGIBILITY_RE, "eligibility_changed", "Contains eligibility language"),
    ]

    for pattern, flag, effect in checks:
        if pattern.search(text):
            events.append(
                _make_event(
                    flag,
                    delta,
                    old_summary="",
                    new_summary=_summarize(text),
                    effect=effect,
                    confidence=0.7,
                )
            )

    return events


def _detect_modified_content_flags(
    delta: SectionDelta, old: str, new: str
) -> list[ChangeEvent]:
    """Detect when specific content types changed between versions."""
    events: list[ChangeEvent] = []

    # Paired checks: presence/absence in old vs new determines the specific flag
    _paired_checks: list[tuple[re.Pattern[str], str, str, str]] = [
        (_EFFECTIVE_DATE_RE, "effective_date_changed", "effective_date_changed",
         "Effective date language changed"),
        (_DEFINITION_RE, "definition_changed", "definition_changed",
         "Definitions changed"),
        (_PENALTY_RE, "penalty_added", "penalty_removed",
         "Penalty provisions changed"),
        (_EXEMPTION_RE, "exemption_added", "exemption_removed",
         "Exemption language changed"),
        (_FUNDING_RE, "funding_language_added", "funding_language_removed",
         "Funding language changed"),
        (_APPROPRIATION_RE, "appropriation_added", "appropriation_removed",
         "Appropriation language changed"),
        (_LICENSING_RE, "licensing_requirement_added", "licensing_requirement_removed",
         "Licensing requirements changed"),
        (_REPORTING_RE, "reporting_requirement_added", "reporting_requirement_removed",
         "Reporting requirements changed"),
        (_RULEMAKING_RE, "rulemaking_authority_added", "rulemaking_authority_removed",
         "Rulemaking authority changed"),
        (_PRIVATE_ACTION_RE, "private_right_of_action_added", "private_right_of_action_removed",
         "Private right of action changed"),
        (_MANDATE_RE, "mandate_added", "mandate_removed",
         "Mandate language changed"),
        (_SUNSET_RE, "sunset_added", "sunset_removed",
         "Sunset provision changed"),
        (_ENFORCEMENT_RE, "enforcement_changed", "enforcement_changed",
         "Enforcement changed"),
        (_REIMBURSEMENT_RE, "reimbursement_changed", "reimbursement_changed",
         "Reimbursement language changed"),
        (_ELIGIBILITY_RE, "eligibility_changed", "eligibility_changed",
         "Eligibility criteria changed"),
        (_DEADLINE_RE, "deadline_changed", "deadline_changed",
         "Deadline changed"),
        (_PREEMPTION_RE, "preemption_risk", "preemption_risk",
         "Preemption language changed"),
    ]

    seen_flags: set[str] = set()

    for pattern, added_flag, removed_flag, effect in _paired_checks:
        old_match = bool(pattern.search(old))
        new_match = bool(pattern.search(new))

        if not old_match and new_match:
            flag = added_flag
            conf = 0.75  # new content detected — higher confidence
        elif old_match and not new_match:
            flag = removed_flag
            conf = 0.70  # removal detected
        elif old_match and new_match:
            # Both present but text changed — use the "added" / changed variant
            flag = added_flag
            conf = 0.55  # both present, lower confidence change is meaningful
        else:
            continue

        if flag not in seen_flags:
            seen_flags.add(flag)
            events.append(
                _make_event(
                    flag,
                    delta,
                    old_summary=_summarize(old),
                    new_summary=_summarize(new),
                    effect=effect,
                    confidence=conf,
                )
            )

    return events


def _detect_scope_flags(
    delta: SectionDelta, old: str, new: str
) -> list[ChangeEvent]:
    """Detect scope expansion or narrowing."""
    events: list[ChangeEvent] = []

    if _SCOPE_RE.search(new) or _SCOPE_RE.search(old):
        # Heuristic: longer new text = expansion, shorter = narrowing
        if len(new) > len(old) * 1.1:
            flag = "scope_expanded"
            effect = "Scope of applicability expanded"
        elif len(new) < len(old) * 0.9:
            flag = "scope_narrowed"
            effect = "Scope of applicability narrowed"
        else:
            flag = "scope_expanded"
            effect = "Scope of applicability modified"

        events.append(
            _make_event(
                flag,
                delta,
                old_summary=_summarize(old),
                new_summary=_summarize(new),
                effect=effect,
                confidence=0.5,
            )
        )

    return events


def _make_event(
    flag: str,
    delta: SectionDelta,
    *,
    old_summary: str,
    new_summary: str,
    effect: str,
    confidence: float,
) -> ChangeEvent:
    """Create a ChangeEvent, asserting the flag is in the approved set."""
    return ChangeEvent(
        change_flag=flag,
        section_id=delta.section_id,
        old_text_summary=old_summary,
        new_text_summary=new_summary,
        practical_effect=effect,
        confidence=confidence,
    )


def _summarize(text: str, max_len: int = 200) -> str:
    """Create a brief summary of text for change event display."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "..."
