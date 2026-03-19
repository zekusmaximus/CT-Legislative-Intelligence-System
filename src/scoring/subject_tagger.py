"""Subject tagging for bill versions.

Assigns subject tags and change flags based on text content.
Uses keyword/pattern matching as the rules-based layer.
"""

from src.schemas.diff import BillDiffResult
from src.schemas.extraction import ExtractedDocument
from src.schemas.scoring import SubjectTagResult

# Subject taxonomy with keyword patterns
SUBJECT_TAXONOMY: dict[str, list[str]] = {
    "transportation": [
        "transportation",
        "transit",
        "highway",
        "road",
        "vehicle",
        "motor",
        "traffic",
        "bridge",
        "rail",
    ],
    "education": [
        "education",
        "school",
        "student",
        "teacher",
        "university",
        "college",
        "curriculum",
        "tuition",
    ],
    "healthcare": [
        "health",
        "hospital",
        "medical",
        "insurance",
        "medicaid",
        "medicare",
        "pharmaceutical",
        "mental health",
    ],
    "environment": [
        "environment",
        "pollution",
        "emission",
        "climate",
        "water quality",
        "waste",
        "conservation",
        "energy",
    ],
    "housing": [
        "housing",
        "landlord",
        "tenant",
        "rent",
        "zoning",
        "affordable housing",
        "eviction",
    ],
    "taxation": [
        "tax",
        "revenue",
        "assessment",
        "exemption",
        "credit",
        "deduction",
        "income tax",
        "sales tax",
    ],
    "labor": [
        "employment",
        "wage",
        "worker",
        "labor",
        "workplace",
        "unemployment",
        "benefits",
        "overtime",
    ],
    "public_safety": [
        "police",
        "fire",
        "emergency",
        "public safety",
        "criminal",
        "law enforcement",
        "firearm",
        "gun",
    ],
    "technology": [
        "technology",
        "data",
        "privacy",
        "cyber",
        "artificial intelligence",
        "digital",
        "broadband",
    ],
    "government_operations": [
        "government",
        "state agency",
        "procurement",
        "audit",
        "transparency",
        "FOIA",
        "public records",
    ],
}

# Minimum keyword hits to assign a tag
_MIN_HITS = 2


def tag_bill_version(
    doc: ExtractedDocument,
    diff_result: BillDiffResult | None = None,
) -> SubjectTagResult:
    """Assign subject tags and change flags to a bill version."""
    text_lower = doc.full_cleaned_text.lower()

    tags: list[str] = []
    rationale: list[str] = []

    for subject, keywords in SUBJECT_TAXONOMY.items():
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hits >= _MIN_HITS:
            tags.append(subject)
            matched = [kw for kw in keywords if kw.lower() in text_lower]
            rationale.append(f"{subject}: matched {', '.join(matched[:3])}")

    # Extract change flags from diff result
    change_flags: list[str] = []
    if diff_result:
        change_flags = list({e.change_flag for e in diff_result.change_events})

    # Confidence based on keyword coverage
    if tags:
        confidence = min(0.9, 0.5 + len(tags) * 0.1)
    else:
        confidence = 0.3

    return SubjectTagResult(
        bill_id=doc.canonical_version_id.rsplit("-", 1)[0]
        if "-" in doc.canonical_version_id
        else doc.canonical_version_id,
        version_id=doc.canonical_version_id,
        subject_tags=tags,
        change_flags=change_flags,
        tag_confidence=confidence,
        rationale=rationale,
    )
