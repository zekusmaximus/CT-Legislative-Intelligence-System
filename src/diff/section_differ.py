"""Section-level differ for bill versions.

Compares two ExtractedDocument instances and produces SectionDelta
objects with similarity scores.
"""

import difflib

from src.schemas.diff import BillDiffResult, SectionDelta
from src.schemas.extraction import ExtractedDocument


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

    all_ids = list(dict.fromkeys(list(prior_sections.keys()) + list(current_sections.keys())))

    deltas: list[SectionDelta] = []
    added = 0
    removed = 0
    modified = 0

    for sid in all_ids:
        old_sec = prior_sections.get(sid)
        new_sec = current_sections.get(sid)

        if old_sec and not new_sec:
            deltas.append(
                SectionDelta(
                    section_id=sid,
                    old_heading=old_sec.heading,
                    new_heading=None,
                    delta_type="removed",
                    old_text=old_sec.text,
                    new_text=None,
                    similarity_score=0.0,
                )
            )
            removed += 1
        elif new_sec and not old_sec:
            deltas.append(
                SectionDelta(
                    section_id=sid,
                    old_heading=None,
                    new_heading=new_sec.heading,
                    delta_type="added",
                    old_text=None,
                    new_text=new_sec.text,
                    similarity_score=0.0,
                )
            )
            added += 1
        else:
            assert old_sec is not None and new_sec is not None
            sim = _text_similarity(old_sec.text, new_sec.text)
            if sim >= 0.99:
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

    return BillDiffResult(
        bill_id=current.canonical_version_id.rsplit("-", 1)[0]
        if "-" in current.canonical_version_id
        else current.canonical_version_id,
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
        bill_id=doc.canonical_version_id.rsplit("-", 1)[0]
        if "-" in doc.canonical_version_id
        else doc.canonical_version_id,
        current_version_id=doc.canonical_version_id,
        prior_version_id=None,
        compared_against="none",
        sections_added=len(deltas),
        sections_removed=0,
        sections_modified=0,
        section_deltas=deltas,
        change_events=[],
    )


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
