"""Taxonomy loader and vocabulary validation.

Loads controlled vocabularies from YAML config files and provides
fail-fast validation that runtime outputs use only approved values.
"""

import functools
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class InvalidTaxonomyValueError(ValueError):
    """Raised when a value is not in the approved controlled vocabulary."""


@functools.lru_cache(maxsize=1)
def load_subject_tags() -> frozenset[str]:
    """Load the approved subject tags from config/taxonomy.subjects.yaml."""
    path = _CONFIG_DIR / "taxonomy.subjects.yaml"
    data = yaml.safe_load(path.read_text())
    tags = frozenset(data["subjects"])
    logger.debug("Loaded %d subject tags from %s", len(tags), path)
    return tags


@functools.lru_cache(maxsize=1)
def load_change_flags() -> frozenset[str]:
    """Load the approved change flags from config/taxonomy.change_flags.yaml."""
    path = _CONFIG_DIR / "taxonomy.change_flags.yaml"
    data = yaml.safe_load(path.read_text())
    flags = frozenset(data["change_flags"])
    logger.debug("Loaded %d change flags from %s", len(flags), path)
    return flags


@functools.lru_cache(maxsize=1)
def load_urgency_levels() -> frozenset[str]:
    """Load the approved urgency levels from config/taxonomy.urgency.yaml."""
    path = _CONFIG_DIR / "taxonomy.urgency.yaml"
    data = yaml.safe_load(path.read_text())
    levels = frozenset(data["urgency_levels"])
    logger.debug("Loaded %d urgency levels from %s", len(levels), path)
    return levels


def validate_subject_tags(tags: list[str]) -> list[str]:
    """Validate that all subject tags are in the approved vocabulary.

    Raises InvalidTaxonomyValueError if any tag is not approved.
    Returns the validated list unchanged.
    """
    approved = load_subject_tags()
    invalid = [t for t in tags if t not in approved]
    if invalid:
        raise InvalidTaxonomyValueError(
            f"Invalid subject tag(s): {invalid}. "
            f"Approved values: {sorted(approved)}"
        )
    return tags


def validate_change_flags(flags: list[str]) -> list[str]:
    """Validate that all change flags are in the approved vocabulary.

    Raises InvalidTaxonomyValueError if any flag is not approved.
    Returns the validated list unchanged.
    """
    approved = load_change_flags()
    invalid = [f for f in flags if f not in approved]
    if invalid:
        raise InvalidTaxonomyValueError(
            f"Invalid change flag(s): {invalid}. "
            f"Approved values: {sorted(approved)}"
        )
    return flags


def validate_urgency(level: str) -> str:
    """Validate that an urgency level is in the approved vocabulary.

    Raises InvalidTaxonomyValueError if not approved.
    Returns the validated value unchanged.
    """
    approved = load_urgency_levels()
    if level not in approved:
        raise InvalidTaxonomyValueError(
            f"Invalid urgency level: '{level}'. "
            f"Approved values: {sorted(approved)}"
        )
    return level
