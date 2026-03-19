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


def make_canonical_version_id(session_year: int, bill_id: str, file_copy_number: int) -> str:
    """Create a canonical version ID.

    Format: {session_year}-{bill_id}-FC{file_copy_number:05d}
    Example: 2026-SB00093-FC00044
    """
    return f"{session_year}-{bill_id}-FC{file_copy_number:05d}"
