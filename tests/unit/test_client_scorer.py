"""Tests for the client relevance scorer."""

from src.schemas.scoring import SubjectTagResult
from src.scoring.client_scorer import ClientProfile, score_bill_for_client


def _make_tag_result(
    bill_id: str = "SB00093",
    subjects: list[str] | None = None,
    change_flags: list[str] | None = None,
) -> SubjectTagResult:
    return SubjectTagResult(
        bill_id=bill_id,
        version_id=f"2026-{bill_id}-FC00044",
        subject_tags=subjects or [],
        change_flags=change_flags or [],
        tag_confidence=0.8,
        rationale=[],
    )


class TestClientScorer:
    def test_keyword_match_scores_points(self):
        client = ClientProfile(
            client_id="client1",
            keywords=["transportation", "transit"],
        )
        tags = _make_tag_result()
        result = score_bill_for_client(
            client, tags,
            "A bill about transportation and transit services.",
        )
        assert result.rules_score > 0
        assert any(
            r.reason_code == "keyword_match"
            for r in result.match_reasons
        )

    def test_subject_match_scores_points(self):
        client = ClientProfile(
            client_id="client1",
            subject_interests=["transportation"],
        )
        tags = _make_tag_result(subjects=["transportation"])
        result = score_bill_for_client(client, tags, "Bill text.")
        assert result.rules_score > 0
        assert any(
            r.reason_code == "subject_match"
            for r in result.match_reasons
        )

    def test_watched_bill_scores_points(self):
        client = ClientProfile(
            client_id="client1",
            watched_bills=["SB00093"],
        )
        tags = _make_tag_result(bill_id="SB00093")
        result = score_bill_for_client(client, tags, "Bill text.")
        assert result.rules_score >= 20
        assert any(
            r.reason_code == "watched_bill"
            for r in result.match_reasons
        )

    def test_committee_match(self):
        client = ClientProfile(
            client_id="client1",
            committees_of_interest=["Transportation Committee"],
        )
        tags = _make_tag_result()
        result = score_bill_for_client(
            client, tags, "Bill text.",
            committee="Transportation Committee",
        )
        assert result.rules_score >= 15

    def test_below_threshold_suppressed(self):
        client = ClientProfile(
            client_id="client1",
            keywords=[],
            alert_threshold=50.0,
        )
        tags = _make_tag_result()
        result = score_bill_for_client(client, tags, "Unrelated bill.")
        assert result.should_alert is False
        assert result.alert_disposition == "suppressed_below_threshold"

    def test_high_score_immediate(self):
        client = ClientProfile(
            client_id="client1",
            keywords=["transportation", "transit", "vehicle"],
            subject_interests=["transportation"],
            watched_bills=["SB00093"],
            alert_threshold=30.0,
        )
        tags = _make_tag_result(
            subjects=["transportation"],
            change_flags=["effective_date_change"],
        )
        result = score_bill_for_client(
            client, tags,
            "A bill about transportation and transit for "
            "vehicle regulation.",
        )
        assert result.should_alert is True
        assert result.urgency in ("high", "critical")

    def test_urgency_levels(self):
        client = ClientProfile(client_id="c1", keywords=["test"])
        low_tags = _make_tag_result()
        result = score_bill_for_client(client, low_tags, "No match.")
        assert result.urgency == "low"

    def test_score_capped_at_100(self):
        client = ClientProfile(
            client_id="c1",
            keywords=[
                "transportation", "transit", "vehicle", "road",
                "highway", "bridge",
            ],
            subject_interests=["transportation", "environment"],
            watched_bills=["SB00093"],
            committees_of_interest=["transportation committee"],
        )
        tags = _make_tag_result(
            subjects=["transportation", "environment"],
            change_flags=["effective_date_change", "appropriation_change"],
        )
        result = score_bill_for_client(
            client, tags,
            "Transportation transit vehicle road highway bridge "
            "regulation.",
            committee="Transportation Committee",
        )
        assert result.rules_score <= 100
