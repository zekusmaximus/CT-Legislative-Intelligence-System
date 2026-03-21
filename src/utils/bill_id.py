"""Bill ID normalization and canonical version ID generation."""

import re

_BILL_PATTERN = re.compile(
    r"^\s*(S\.?B\.?|H\.?B\.?|Senate\s+Bill|House\s+Bill)\s*(?:No\.?\s*)?(\d+)\s*$",
    re.IGNORECASE,
)


def normalize_bill_id(raw: str) -> str:
    """Normalize a bill identifier to the canonical format: HB00001 or SB00093.

    Accepts formats like:
        - "SB 93", "S.B. 93", "Senate Bill 93"
        - "HB 5140", "H.B. 5140", "House Bill 5140"
        - "SB00093" (already normalized)

    Returns:
        Canonical bill ID string (e.g., "SB00093").

    Raises:
        ValueError: If the input cannot be parsed as a valid bill identifier.
    """
    match = _BILL_PATTERN.match(raw.strip())
    if not match:
        raise ValueError(f"Cannot parse bill identifier: {raw!r}")

    prefix_raw = match.group(1).upper().replace(".", "").replace(" ", "")
    number = int(match.group(2))

    if prefix_raw in ("SB", "SENATEBILL"):
        chamber_prefix = "SB"
    elif prefix_raw in ("HB", "HOUSEBILL"):
        chamber_prefix = "HB"
    else:
        raise ValueError(f"Unknown chamber prefix: {prefix_raw!r}")

    return f"{chamber_prefix}{number:05d}"


def bill_id_to_chamber(bill_id: str) -> str:
    """Return 'house' or 'senate' from a normalized bill ID."""
    if bill_id.startswith("HB"):
        return "house"
    elif bill_id.startswith("SB"):
        return "senate"
    raise ValueError(f"Invalid bill ID prefix: {bill_id!r}")


def bill_id_to_number(bill_id: str) -> int:
    """Extract the numeric portion from a normalized bill ID."""
    return int(bill_id[2:])


def parse_canonical_version_id(canonical_version_id: str) -> tuple[int, str, int]:
    """Parse a canonical version ID into its components.

    Input format: {session_year}-{bill_id}-FC{file_copy_number:05d}
    Example: "2026-SB00093-FC00044" → (2026, "SB00093", 44)

    Returns:
        Tuple of (session_year, bill_id, file_copy_number).

    Raises:
        ValueError: If the input cannot be parsed.
    """
    match = re.match(r"^(\d{4})-([A-Z]{2}\d{5})-FC(\d{5})$", canonical_version_id)
    if not match:
        raise ValueError(f"Cannot parse canonical version ID: {canonical_version_id!r}")
    return int(match.group(1)), match.group(2), int(match.group(3))


def bill_id_from_canonical(canonical_version_id: str) -> str:
    """Extract the bill_id from a canonical version ID.

    Example: "2026-SB00093-FC00044" → "SB00093"

    Falls back to returning the full string if it doesn't match
    the canonical format (e.g. test fixtures using short IDs).
    """
    match = re.match(r"^(\d{4})-([A-Z]{2}\d{5})-FC(\d{5})$", canonical_version_id)
    if match:
        return match.group(2)
    # Fallback: try to strip trailing -FC segment if present
    if "-FC" in canonical_version_id:
        return canonical_version_id.rsplit("-FC", 1)[0]
    return canonical_version_id


def make_canonical_version_id(session_year: int, bill_id: str, file_copy_number: int) -> str:
    """Create a canonical version ID.

    Format: {session_year}-{bill_id}-FC{file_copy_number:05d}
    Example: 2026-SB00093-FC00044
    """
    return f"{session_year}-{bill_id}-FC{file_copy_number:05d}"
