"""Client relevance scorer.

Computes a rules-based relevance score for a bill against a
client profile. Produces ClientScoreResult per technical contract §12.
"""

from src.schemas.scoring import ClientMatchReason, ClientScoreResult, SubjectTagResult


class ClientProfile:
    """Represents a client's interest profile for scoring."""

    def __init__(
        self,
        client_id: str,
        keywords: list[str] | None = None,
        subject_interests: list[str] | None = None,
        committees_of_interest: list[str] | None = None,
        watched_bills: list[str] | None = None,
        alert_threshold: float = 30.0,
        digest_threshold: float | None = None,
    ):
        self.client_id = client_id
        self.keywords = [k.lower() for k in (keywords or [])]
        self.subject_interests = subject_interests or []
        self.committees_of_interest = [c.lower() for c in (committees_of_interest or [])]
        self.watched_bills = watched_bills or []
        self.alert_threshold = alert_threshold
        # digest_threshold defaults to alert_threshold if not specified,
        # giving a two-tier model: digest_threshold <= score < alert_threshold → digest,
        # score >= alert_threshold → immediate.
        self.digest_threshold = digest_threshold if digest_threshold is not None else alert_threshold


def score_bill_for_client(
    client: ClientProfile,
    tag_result: SubjectTagResult,
    bill_text: str,
    committee: str | None = None,
) -> ClientScoreResult:
    """Score a bill version's relevance for a specific client."""
    reasons: list[ClientMatchReason] = []
    text_lower = bill_text.lower()

    # Keyword matching (up to 40 points)
    keyword_score = 0.0
    for kw in client.keywords:
        if kw in text_lower:
            keyword_score += 10.0
            reasons.append(
                ClientMatchReason(
                    reason_code="keyword_match",
                    reason_text=f"Keyword '{kw}' found in bill text",
                    weight=10.0,
                )
            )
    keyword_score = min(keyword_score, 40.0)

    # Subject tag matching (up to 30 points)
    subject_score = 0.0
    for subject in tag_result.subject_tags:
        if subject in client.subject_interests:
            subject_score += 15.0
            reasons.append(
                ClientMatchReason(
                    reason_code="subject_match",
                    reason_text=f"Subject '{subject}' matches interest",
                    weight=15.0,
                )
            )
    subject_score = min(subject_score, 30.0)

    # Committee matching (up to 15 points)
    committee_score = 0.0
    if committee and committee.lower() in client.committees_of_interest:
        committee_score = 15.0
        reasons.append(
            ClientMatchReason(
                reason_code="committee_match",
                reason_text=f"Committee '{committee}' is of interest",
                weight=15.0,
            )
        )

    # Watched bill (up to 20 points)
    watched_score = 0.0
    bill_id = tag_result.bill_id
    if bill_id in client.watched_bills:
        watched_score = 20.0
        reasons.append(
            ClientMatchReason(
                reason_code="watched_bill",
                reason_text=f"Bill '{bill_id}' is on watch list",
                weight=20.0,
            )
        )

    # Change flag boost (up to 10 points)
    change_boost = 0.0
    high_impact_flags = {
        "effective_date_changed",
        "appropriation_added",
        "penalty_added",
    }
    for flag in tag_result.change_flags:
        if flag in high_impact_flags:
            change_boost += 5.0
            reasons.append(
                ClientMatchReason(
                    reason_code="change_flag_match",
                    reason_text=f"High-impact change: {flag}",
                    weight=5.0,
                )
            )
    change_boost = min(change_boost, 10.0)

    rules_score = min(
        100.0,
        keyword_score + subject_score + committee_score + watched_score + change_boost,
    )

    urgency = _compute_urgency(rules_score, tag_result.change_flags)
    should_alert = rules_score >= client.digest_threshold
    disposition = _compute_disposition(
        rules_score, client.alert_threshold, client.digest_threshold
    )

    return ClientScoreResult(
        client_id=client.client_id,
        bill_id=bill_id,
        version_id=tag_result.version_id,
        rules_score=rules_score,
        final_score=rules_score,
        urgency=urgency,
        should_alert=should_alert,
        alert_disposition=disposition,
        match_reasons=reasons,
    )


def _compute_urgency(score: float, change_flags: list[str]) -> str:
    """Determine urgency level based on score and change flags."""
    if score >= 80 or "effective_date_changed" in change_flags:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _compute_disposition(
    score: float, alert_threshold: float, digest_threshold: float
) -> str:
    """Determine alert disposition using two-tier thresholds.

    - score >= alert_threshold → immediate
    - digest_threshold <= score < alert_threshold → digest
    - score < digest_threshold → suppressed
    """
    if score >= alert_threshold:
        return "immediate"
    if score >= digest_threshold:
        return "digest"
    return "suppressed_below_threshold"
