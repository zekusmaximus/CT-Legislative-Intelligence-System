"""Section-level differ for bill versions.

Compares two ExtractedDocument instances and produces SectionDelta
objects with similarity scores.

Section alignment strategy:
  1. Match by exact section_id first.
  2. For unmatched sections, attempt fuzzy heading alignment so that
     renumbered sections (e.g. "sec_3" → "sec_4" after an insertion)
     can still be paired.
"""

import difflib

from src.schemas.diff import BillDiffResult, SectionDelta
from src.utils.bill_id import bill_id_from_canonical
from src.schemas.extraction import ExtractedDocument, SectionSpan

# Similarity at or above this threshold is treated as unchanged.
UNCHANGED_THRESHOLD = 0.98

# Below this threshold a fuzzy heading match is not accepted.
FUZZY_HEADING_MIN_SIMILARITY = 0.60


def diff_documents(
    current: ExtractedDocument,
    prior: ExtractedDocument | None,
) -> BillDiffResult:
    """Diff two extracted documents at the section level.

    If prior is None, all current sections are marked as 'added'.
    """
    if prior is None:
        return _build_new_bill_result(current)

    current_sections = {s.section_id: s for s in current.sections}
    prior_sections = {s.section_id: s for s in prior.sections}

    # Phase 1: exact ID matching
    matched_current: set[str] = set()
    matched_prior: set[str] = set()
    deltas: list[SectionDelta] = []
    added = 0
    removed = 0
    modified = 0

    all_ids = list(dict.fromkeys(list(prior_sections.keys()) + list(current_sections.keys())))

    for sid in all_ids:
        old_sec = prior_sections.get(sid)
        new_sec = current_sections.get(sid)

        if old_sec and new_sec:
            matched_current.add(sid)
            matched_prior.add(sid)
            sim = _text_similarity(old_sec.text, new_sec.text)
            if sim >= UNCHANGED_THRESHOLD:
                delta_type = "unchanged"
            else:
                delta_type = "modified"
                modified += 1
            deltas.append(
                SectionDelta(
                    section_id=sid,
                    old_heading=old_sec.heading,
                    new_heading=new_sec.heading,
                    delta_type=delta_type,
                    old_text=old_sec.text if delta_type != "unchanged" else None,
                    new_text=new_sec.text if delta_type != "unchanged" else None,
                    similarity_score=sim,
                )
            )

    # Phase 2: fuzzy heading alignment for unmatched sections
    unmatched_current = {sid: current_sections[sid] for sid in current_sections if sid not in matched_current}
    unmatched_prior = {sid: prior_sections[sid] for sid in prior_sections if sid not in matched_prior}

    fuzzy_pairs = _fuzzy_align(unmatched_prior, unmatched_current)
    for old_sid, new_sid, sim in fuzzy_pairs:
        old_sec = unmatched_prior.pop(old_sid)
        unmatched_current.pop(new_sid)
        if sim >= UNCHANGED_THRESHOLD:
            delta_type = "unchanged"
        else:
            delta_type = "modified"
            modified += 1
        deltas.append(
            SectionDelta(
                section_id=new_sid,
                old_heading=old_sec.heading,
                new_heading=current_sections[new_sid].heading,
                delta_type=delta_type,
                old_text=old_sec.text if delta_type != "unchanged" else None,
                new_text=current_sections[new_sid].text if delta_type != "unchanged" else None,
                similarity_score=sim,
            )
        )

    # Remaining unmatched are pure adds/removes
    for sid in unmatched_prior:
        deltas.append(
            SectionDelta(
                section_id=sid,
                old_heading=unmatched_prior[sid].heading,
                new_heading=None,
                delta_type="removed",
                old_text=unmatched_prior[sid].text,
                new_text=None,
                similarity_score=0.0,
            )
        )
        removed += 1

    for sid in unmatched_current:
        deltas.append(
            SectionDelta(
                section_id=sid,
                old_heading=None,
                new_heading=unmatched_current[sid].heading,
                delta_type="added",
                old_text=None,
                new_text=unmatched_current[sid].text,
                similarity_score=0.0,
            )
        )
        added += 1

    return BillDiffResult(
        bill_id=bill_id_from_canonical(current.canonical_version_id),
        current_version_id=current.canonical_version_id,
        prior_version_id=prior.canonical_version_id,
        compared_against="prior_file_copy",
        sections_added=added,
        sections_removed=removed,
        sections_modified=modified,
        section_deltas=deltas,
        change_events=[],
    )


def _build_new_bill_result(doc: ExtractedDocument) -> BillDiffResult:
    """Build a diff result for a brand-new bill with no prior version."""
    deltas = [
        SectionDelta(
            section_id=s.section_id,
            old_heading=None,
            new_heading=s.heading,
            delta_type="added",
            old_text=None,
            new_text=s.text,
            similarity_score=0.0,
        )
        for s in doc.sections
    ]

    return BillDiffResult(
        bill_id=bill_id_from_canonical(doc.canonical_version_id),
        current_version_id=doc.canonical_version_id,
        prior_version_id=None,
        compared_against="none",
        sections_added=len(deltas),
        sections_removed=0,
        sections_modified=0,
        section_deltas=deltas,
        change_events=[],
    )


def _fuzzy_align(
    prior_unmatched: dict[str, SectionSpan],
    current_unmatched: dict[str, SectionSpan],
) -> list[tuple[str, str, float]]:
    """Attempt to pair unmatched sections by text similarity.

    Returns a list of (old_sid, new_sid, text_similarity) triples,
    best matches first. Only pairs above ``FUZZY_HEADING_MIN_SIMILARITY``
    are returned.
    """
    if not prior_unmatched or not current_unmatched:
        return []

    candidates: list[tuple[str, str, float]] = []
    for old_sid, old_sec in prior_unmatched.items():
        for new_sid, new_sec in current_unmatched.items():
            sim = _text_similarity(old_sec.text, new_sec.text)
            if sim >= FUZZY_HEADING_MIN_SIMILARITY:
                candidates.append((old_sid, new_sid, sim))

    # Greedy best-first matching
    candidates.sort(key=lambda c: c[2], reverse=True)
    used_old: set[str] = set()
    used_new: set[str] = set()
    pairs: list[tuple[str, str, float]] = []
    for old_sid, new_sid, sim in candidates:
        if old_sid not in used_old and new_sid not in used_new:
            pairs.append((old_sid, new_sid, sim))
            used_old.add(old_sid)
            used_new.add(new_sid)

    return pairs


def _text_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two texts using SequenceMatcher."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def get_unified_diff(old_text: str, new_text: str, n: int = 3) -> str:
    """Generate a unified diff string for display."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="prior", tofile="current", n=n)
    return "".join(diff)
