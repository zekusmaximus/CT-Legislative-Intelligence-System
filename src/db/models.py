"""SQLAlchemy ORM models for all database tables."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SourcePage(Base):
    __tablename__ = "source_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    session_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (
        UniqueConstraint("session_year", "bill_id", name="uq_bill_session_year_bill_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_year: Mapped[int] = mapped_column(Integer, nullable=False)
    bill_id: Mapped[str] = mapped_column(String(10), nullable=False)
    chamber: Mapped[str] = mapped_column(String(10), nullable=False)
    bill_number_numeric: Mapped[int] = mapped_column(Integer, nullable=False)
    current_title: Mapped[str] = mapped_column(Text, nullable=False)
    committee_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bill_status_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    file_copies: Mapped[list["FileCopy"]] = relationship(back_populates="bill")


class FileCopy(Base):
    __tablename__ = "file_copies"
    __table_args__ = (
        UniqueConstraint("canonical_version_id", name="uq_file_copy_canonical_version_id"),
        Index("ix_file_copy_bill_id", "bill_id_fk"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id_fk: Mapped[int] = mapped_column(ForeignKey("bills.id"), nullable=False)
    session_year: Mapped[int] = mapped_column(Integer, nullable=False)
    file_copy_number: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_version_id: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    listing_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    pdf_url: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    bill: Mapped["Bill"] = relationship(back_populates="file_copies")


class BillTextExtraction(Base):
    __tablename__ = "bill_text_extractions"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    full_raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    full_cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    overall_extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BillTextPage(Base):
    __tablename__ = "bill_text_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    extraction_id: Mapped[int] = mapped_column(
        ForeignKey("bill_text_extractions.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(10), nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)


class BillSection(Base):
    __tablename__ = "bill_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    section_id: Mapped[str] = mapped_column(String(50), nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class BillDiff(Base):
    __tablename__ = "bill_diffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id_fk: Mapped[int] = mapped_column(ForeignKey("bills.id"), nullable=False)
    current_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    prior_version_id: Mapped[str | None] = mapped_column(String(30), nullable=True)
    compared_against: Mapped[str] = mapped_column(String(20), nullable=False)
    sections_added: Mapped[int] = mapped_column(Integer, default=0)
    sections_removed: Mapped[int] = mapped_column(Integer, default=0)
    sections_modified: Mapped[int] = mapped_column(Integer, default=0)
    effective_date_old: Mapped[str | None] = mapped_column(String(100), nullable=True)
    effective_date_new: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BillChangeEvent(Base):
    __tablename__ = "bill_change_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_diff_id: Mapped[int] = mapped_column(ForeignKey("bill_diffs.id"), nullable=False)
    change_flag: Mapped[str] = mapped_column(String(50), nullable=False)
    section_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    old_text_summary: Mapped[str] = mapped_column(Text, nullable=False)
    new_text_summary: Mapped[str] = mapped_column(Text, nullable=False)
    practical_effect: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_threshold: Mapped[int] = mapped_column(Integer, default=78)
    digest_threshold: Mapped[int] = mapped_column(Integer, default=58)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ClientInterestProfile(Base):
    __tablename__ = "client_interest_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id_fk: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    profile_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    profile_text_for_embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClientBillScore(Base):
    __tablename__ = "client_bill_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id_fk: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    bill_id_fk: Mapped[int] = mapped_column(ForeignKey("bills.id"), nullable=False)
    canonical_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    rules_score: Mapped[float] = mapped_column(Float, nullable=False)
    embedding_score: Mapped[float] = mapped_column(Float, default=0.0)
    llm_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    urgency: Mapped[str] = mapped_column(String(10), nullable=False)
    should_alert: Mapped[bool] = mapped_column(Boolean, nullable=False)
    alert_disposition: Mapped[str] = mapped_column(String(30), nullable=False)
    reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id_fk: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    bill_id_fk: Mapped[int] = mapped_column(ForeignKey("bills.id"), nullable=False)
    canonical_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    urgency: Mapped[str] = mapped_column(String(10), nullable=False)
    alert_disposition: Mapped[str] = mapped_column(String(30), nullable=False)
    alert_text: Mapped[str] = mapped_column(Text, nullable=False)
    telegram_message_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    suppression_key: Mapped[str] = mapped_column(String(200), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivery_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_delivery_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BillSummary(Base):
    __tablename__ = "bill_summaries"
    __table_args__ = (
        UniqueConstraint(
            "canonical_version_id",
            name="uq_bill_summary_version_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    bill_id: Mapped[str] = mapped_column(String(10), nullable=False)
    one_sentence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    deep_summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_sections_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    practical_takeaways_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BillSubjectTag(Base):
    __tablename__ = "bill_subject_tags"
    __table_args__ = (
        UniqueConstraint(
            "canonical_version_id", "subject_tag",
            name="uq_bill_subject_tag_version_tag",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    subject_tag: Mapped[str] = mapped_column(String(50), nullable=False)
    tag_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PipelineRun(Base):
    """Tracks each pipeline execution for auditability."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False)  # daily, reconciliation, single
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running, completed, failed
    entries_collected: Mapped[int] = mapped_column(Integer, default=0)
    entries_processed: Mapped[int] = mapped_column(Integer, default=0)
    entries_failed: Mapped[int] = mapped_column(Integer, default=0)
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FeedbackLabel(Base):
    __tablename__ = "feedback_labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id_fk: Mapped[int] = mapped_column(ForeignKey("clients.id"), nullable=False)
    bill_id_fk: Mapped[int] = mapped_column(ForeignKey("bills.id"), nullable=False)
    canonical_version_id: Mapped[str] = mapped_column(
        String(30), ForeignKey("file_copies.canonical_version_id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
