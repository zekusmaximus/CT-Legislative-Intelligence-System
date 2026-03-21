"""Load and validate client interest profiles from YAML files.

Reads client YAML configs from ``config/clients/`` and converts them
into validated ``ClientProfile`` objects used by the scoring engine.
"""

import logging
from pathlib import Path

import yaml

from src.scoring.client_scorer import ClientProfile

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config" / "clients"


def load_client_profile(path: Path) -> ClientProfile:
    """Load a single client profile from a YAML file.

    Raises ``ValueError`` if required fields are missing or invalid.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid client profile format in {path}")

    client_id = data.get("client_id")
    if not client_id:
        raise ValueError(f"Missing client_id in {path}")

    keywords: list[str] = []
    keywords.extend(data.get("positive_keywords") or [])
    keywords.extend(data.get("agency_keywords") or [])

    subject_interests = list((data.get("subject_priorities") or {}).keys())
    committees = data.get("committee_keywords") or []
    watched_bills = data.get("watched_bills") or []
    alert_threshold = float(data.get("alert_threshold", 78.0))
    digest_threshold = float(data.get("digest_threshold", 58.0))

    return ClientProfile(
        client_id=client_id,
        keywords=keywords,
        subject_interests=subject_interests,
        committees_of_interest=committees,
        watched_bills=watched_bills,
        alert_threshold=alert_threshold,
        digest_threshold=digest_threshold,
    )


def load_all_profiles(config_dir: Path | None = None) -> list[ClientProfile]:
    """Load all active client profiles from the config directory.

    Only loads files matching ``*.yaml`` or ``*.yml``. Skips files
    where ``is_active`` is explicitly ``false``.
    """
    directory = config_dir or _CONFIG_DIR
    if not directory.is_dir():
        logger.warning("Client config directory not found: %s", directory)
        return []

    profiles: list[ClientProfile] = []
    for path in sorted(directory.iterdir()):
        if path.suffix not in (".yaml", ".yml"):
            continue
        try:
            with open(path) as f:
                raw = yaml.safe_load(f)
            if isinstance(raw, dict) and raw.get("is_active") is False:
                logger.debug("Skipping inactive client: %s", path.name)
                continue
            profile = load_client_profile(path)
            profiles.append(profile)
            logger.info("Loaded client profile: %s", profile.client_id)
        except Exception as e:
            logger.error("Failed to load client profile %s: %s", path.name, e)

    return profiles


def get_client_metadata(path: Path) -> dict:
    """Extract metadata fields from a client YAML for DB persistence."""
    with open(path) as f:
        data = yaml.safe_load(f)

    return {
        "client_id": data.get("client_id", ""),
        "display_name": data.get("client_name", data.get("client_id", "")),
        "is_active": data.get("is_active", True),
        "alert_threshold": int(data.get("alert_threshold", 78)),
        "digest_threshold": int(data.get("digest_threshold", 58)),
        "profile_yaml": yaml.dump(data, default_flow_style=False),
    }
