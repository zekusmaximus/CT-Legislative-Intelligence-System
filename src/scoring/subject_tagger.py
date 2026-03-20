"""Subject tagging for bill versions.

Assigns subject tags based on text content using keyword/pattern matching.
All emitted tags are validated against the controlled vocabulary loaded
from config/taxonomy.subjects.yaml.
"""

from src.metadata.taxonomy import load_subject_tags, validate_subject_tags
from src.schemas.diff import BillDiffResult
from src.schemas.extraction import ExtractedDocument
from src.schemas.scoring import SubjectTagResult

# Canonical subject taxonomy: maps each approved tag to keyword patterns.
# Only tags present in config/taxonomy.subjects.yaml may appear as keys.
SUBJECT_KEYWORDS: dict[str, list[str]] = {
    "health_care": [
        "health care",
        "hospital",
        "medical",
        "medicaid",
        "medicare",
        "physician",
        "nursing",
        "patient",
        "clinic",
        "pharmaceutical",
        "mental health",
        "behavioral health",
    ],
    "insurance": [
        "insurance",
        "insurer",
        "underwriting",
        "coverage",
        "policyholder",
        "premium",
        "deductible",
        "claims",
    ],
    "labor_employment": [
        "employment",
        "wage",
        "worker",
        "labor",
        "workplace",
        "unemployment",
        "overtime",
        "collective bargaining",
        "employee",
        "employer",
    ],
    "tax_revenue": [
        "tax",
        "revenue",
        "assessment",
        "income tax",
        "sales tax",
        "property tax",
        "tax credit",
        "tax exemption",
        "taxation",
    ],
    "appropriations_budget": [
        "appropriation",
        "budget",
        "general fund",
        "special fund",
        "fiscal year",
        "allocat",
        "expenditure",
    ],
    "municipalities": [
        "municipality",
        "municipal",
        "town",
        "city",
        "selectmen",
        "local government",
        "board of education",
        "regional",
    ],
    "housing": [
        "housing",
        "landlord",
        "tenant",
        "rent",
        "affordable housing",
        "eviction",
        "dwelling",
        "residential",
        "mortgage",
    ],
    "energy_environment": [
        "energy",
        "environment",
        "pollution",
        "emission",
        "climate",
        "water quality",
        "waste",
        "conservation",
        "renewable",
        "solar",
        "electric vehicle",
    ],
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
    "cannabis": [
        "cannabis",
        "marijuana",
        "hemp",
        "THC",
        "dispensary",
    ],
    "gaming": [
        "gaming",
        "gambling",
        "casino",
        "lottery",
        "sports betting",
        "wager",
    ],
    "data_privacy": [
        "data privacy",
        "personal data",
        "data protection",
        "privacy",
        "data breach",
        "consumer data",
        "biometric",
    ],
    "artificial_intelligence": [
        "artificial intelligence",
        "AI",
        "machine learning",
        "automated decision",
        "algorithm",
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
        "higher education",
    ],
    "procurement": [
        "procurement",
        "contracting",
        "competitive bid",
        "state contract",
        "vendor",
        "purchasing",
    ],
    "licensing_regulation": [
        "license",
        "licensing",
        "permit",
        "certification",
        "regulated",
        "regulation",
        "compliance",
        "inspection",
    ],
    "reimbursement_rate_setting": [
        "reimbursement",
        "rate setting",
        "provider rate",
        "payment rate",
        "fee schedule",
    ],
    "civil_liability": [
        "liability",
        "negligence",
        "tort",
        "damages",
        "civil action",
        "indemnif",
        "statute of limitations",
    ],
    "criminal_justice": [
        "criminal",
        "felony",
        "misdemeanor",
        "incarceration",
        "parole",
        "probation",
        "law enforcement",
        "police",
        "firearm",
        "gun",
        "sentencing",
    ],
    "consumer_protection": [
        "consumer protection",
        "unfair trade",
        "deceptive",
        "consumer rights",
        "warranty",
        "consumer complaint",
    ],
    "utilities": [
        "utility",
        "utilities",
        "electric",
        "gas",
        "water",
        "sewer",
        "ratepayer",
        "PURA",
        "public utility",
    ],
    "land_use_zoning": [
        "zoning",
        "land use",
        "planning",
        "subdivision",
        "building code",
        "setback",
        "variance",
    ],
    "public_health": [
        "public health",
        "disease",
        "vaccination",
        "epidemi",
        "pandemic",
        "communicable",
        "opioid",
        "substance abuse",
    ],
    "social_services": [
        "social services",
        "welfare",
        "SNAP",
        "childcare",
        "child care",
        "foster",
        "adoption",
        "disability",
        "elderly",
        "senior",
    ],
    "agriculture_food": [
        "agriculture",
        "farm",
        "food safety",
        "livestock",
        "crop",
        "dairy",
        "organic",
        "food",
    ],
    "banking_financial_services": [
        "bank",
        "banking",
        "financial",
        "credit union",
        "lending",
        "loan",
        "securities",
        "fintech",
    ],
    "professional_services": [
        "professional",
        "attorney",
        "accountant",
        "engineer",
        "architect",
        "real estate",
        "broker",
        "appraiser",
    ],
    "state_agency_governance": [
        "state agency",
        "government",
        "audit",
        "transparency",
        "FOIA",
        "public records",
        "executive branch",
        "commissioner",
        "department of",
    ],
}

# Minimum keyword hits to assign a tag
_MIN_HITS = 2


def _validate_keyword_map_on_load() -> None:
    """Verify at import time that SUBJECT_KEYWORDS keys match the config."""
    approved = load_subject_tags()
    keyword_keys = set(SUBJECT_KEYWORDS.keys())
    extra = keyword_keys - approved
    missing = approved - keyword_keys
    if extra:
        raise ValueError(
            f"SUBJECT_KEYWORDS contains tags not in taxonomy config: {extra}"
        )
    if missing:
        raise ValueError(
            f"Taxonomy config has tags without keyword patterns: {missing}"
        )


# Validate on module load
_validate_keyword_map_on_load()


def tag_bill_version(
    doc: ExtractedDocument,
    diff_result: BillDiffResult | None = None,
) -> SubjectTagResult:
    """Assign subject tags and change flags to a bill version.

    All emitted tags and flags are validated against the controlled vocabulary.
    Raises InvalidTaxonomyValueError if any value is not in the approved set.
    """
    text_lower = doc.full_cleaned_text.lower()

    tags: list[str] = []
    rationale: list[str] = []

    for subject, keywords in SUBJECT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hits >= _MIN_HITS:
            tags.append(subject)
            matched = [kw for kw in keywords if kw.lower() in text_lower]
            rationale.append(f"{subject}: matched {', '.join(matched[:3])}")

    # Validate all emitted tags
    validate_subject_tags(tags)

    # Extract change flags from diff result (already validated by classifier)
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
