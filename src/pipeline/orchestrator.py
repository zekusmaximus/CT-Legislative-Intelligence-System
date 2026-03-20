"""Main pipeline orchestrator.

Wires together: Fetch → Parse → Persist → Extract → Diff → Enrich → Score → Alert.
Each stage is independently callable for testing and partial reruns.
"""

import logging

from sqlalchemy.orm import Session

from pathlib import Path

from src.alerts.telegram_formatter import build_alert_payload, format_alert_text
from src.collectors.cga_all_filecopies import parse_all_filecopies_page
from src.collectors.cga_bill_status import parse_bill_status_page
from src.collectors.cga_daily_filecopies import parse_daily_filecopies_page
from src.collectors.http_fetcher import CGAFetcher
from src.alerts.telegram_sender import TelegramSender
from src.db.models import Alert
from src.db.repositories.alerts import AlertRepository
from src.db.repositories.bills import BillRepository
from src.db.repositories.clients import ClientRepository
from src.db.repositories.diffs import DiffRepository
from src.db.repositories.extractions import ExtractionRepository
from src.db.repositories.file_copies import FileCopyRepository
from src.db.repositories.scores import ClientBillScoreRepository
from src.db.repositories.sections import SectionRepository
from src.db.repositories.source_pages import SourcePageRepository
from src.db.repositories.subject_tags import SubjectTagRepository
from src.db.repositories.summaries import SummaryRepository
from src.diff.change_classifier import classify_changes
from src.diff.section_differ import diff_documents
from src.extract.confidence import (
    compute_overall_confidence,
    needs_ocr_fallback,
)
from src.extract.normalize_text import normalize_pages
from src.extract.pdf_text import extract_text_from_pdf, get_page_count
from src.extract.section_parser import parse_sections
from src.schemas.diff import BillDiffResult
from src.schemas.extraction import ExtractedDocument
from src.schemas.intake import FileCopyListingRow
from src.schemas.scoring import ClientScoreResult
from src.scoring.alert_decisioner import AlertDecision, decide_alert
from src.scoring.client_profile_loader import (
    get_client_metadata,
    load_all_profiles,
)
from src.scoring.client_scorer import ClientProfile, score_bill_for_client
from src.scoring.subject_tagger import tag_bill_version
from src.scoring.summary_generator import generate_summary
from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)

CGA_BASE_URL = "https://www.cga.ct.gov"


class Pipeline:
    """End-to-end legislative intelligence pipeline."""

    def __init__(
        self,
        db_session: Session,
        storage: LocalStorage,
        fetcher: CGAFetcher | None = None,
        session_year: int = 2026,
        client_config_dir: Path | None = None,
        telegram_sender: TelegramSender | None = None,
    ):
        self.db = db_session
        self.storage = storage
        self.fetcher = fetcher or CGAFetcher()
        self.session_year = session_year
        self.client_config_dir = client_config_dir
        self.telegram_sender = telegram_sender

        self.bill_repo = BillRepository(db_session)
        self.fc_repo = FileCopyRepository(db_session)
        self.source_repo = SourcePageRepository(db_session)
        self.extraction_repo = ExtractionRepository(db_session)
        self.section_repo = SectionRepository(db_session)
        self.diff_repo = DiffRepository(db_session)
        self.tag_repo = SubjectTagRepository(db_session)
        self.summary_repo = SummaryRepository(db_session)
        self.client_repo = ClientRepository(db_session)
        self.score_repo = ClientBillScoreRepository(db_session)
        self.alert_repo = AlertRepository(db_session)

    # ------------------------------------------------------------------
    # Stage 1: Collect daily file copies
    # ------------------------------------------------------------------
    def collect_daily(self) -> list[FileCopyListingRow]:
        """Fetch and parse the daily file-copies page."""
        url = f"{CGA_BASE_URL}/asp/cgabillstatus/CGABillCopy.asp"
        html, status = self.fetcher.fetch_html(url)
        if status != 200 or not html:
            logger.error("Failed to fetch daily page: status %d", status)
            return []

        source_record, rows = parse_daily_filecopies_page(html, self.session_year, source_url=url)

        # Check for duplicate page
        if self.source_repo.exists_by_hash(source_record.content_sha256):
            logger.info("Daily page already ingested, skipping")
            return []

        # Store raw HTML
        html_path = self.storage.store_html(
            "daily_filecopies",
            self.session_year,
            source_record.content_sha256,
            html.encode(),
        )
        self.source_repo.create(source_record, raw_html_path=html_path)
        self.db.commit()

        logger.info("Collected %d file copy rows from daily page", len(rows))
        return rows

    # ------------------------------------------------------------------
    # Stage 1b: Collect all file copies (reconciliation)
    # ------------------------------------------------------------------
    def collect_all(self) -> list[FileCopyListingRow]:
        """Fetch and parse the all-file-copies page."""
        url = f"{CGA_BASE_URL}/asp/cgabillstatus/CGABillCopy.asp?which_year={self.session_year}"
        html, status = self.fetcher.fetch_html(url)
        if status != 200 or not html:
            logger.error("Failed to fetch all-FC page: status %d", status)
            return []

        source_record, rows = parse_all_filecopies_page(html, self.session_year, source_url=url)

        if self.source_repo.exists_by_hash(source_record.content_sha256):
            logger.info("All-FC page already ingested, skipping")
            return []

        html_path = self.storage.store_html(
            "all_filecopies",
            self.session_year,
            source_record.content_sha256,
            html.encode(),
        )
        self.source_repo.create(source_record, raw_html_path=html_path)
        self.db.commit()

        logger.info("Collected %d file copy rows from all-FC page", len(rows))
        return rows

    # ------------------------------------------------------------------
    # Stage 2: Persist bills and file copies
    # ------------------------------------------------------------------
    def persist_rows(self, rows: list[FileCopyListingRow]) -> list[dict]:
        """Persist parsed rows into DB. Returns list of new file copies."""
        new_entries: list[dict] = []

        for row in rows:
            bill = self.bill_repo.upsert(
                session_year=row.session_year,
                bill_id=row.bill_id,
                title=row.bill_title,
            )

            fc, created = self.fc_repo.create_if_new(
                bill_db_id=bill.id,
                session_year=row.session_year,
                bill_id=row.bill_id,
                file_copy_number=row.file_copy_number,
                pdf_url=str(row.file_copy_pdf_url),
                listing_date=str(row.listing_date),
            )

            if created:
                new_entries.append(
                    {
                        "bill_id": row.bill_id,
                        "file_copy_number": row.file_copy_number,
                        "pdf_url": str(row.file_copy_pdf_url),
                        "canonical_id": fc.canonical_version_id,
                        "bill_db_id": bill.id,
                    }
                )

        self.db.commit()
        logger.info("Persisted %d new file copies", len(new_entries))
        return new_entries

    # ------------------------------------------------------------------
    # Stage 3: Download PDFs
    # ------------------------------------------------------------------
    def download_pdf(self, entry: dict) -> str | None:
        """Download a PDF for a file copy entry. Returns local path."""
        pdf_url = entry["pdf_url"]
        bill_id = entry["bill_id"]
        fc_num = entry["file_copy_number"]
        canonical_id = entry["canonical_id"]

        storage_key = f"pdfs/{self.session_year}/{bill_id}/FC{fc_num:05d}.pdf"
        if self.storage.exists(storage_key):
            logger.info("PDF already stored: %s", canonical_id)
            data = self.storage.retrieve(storage_key)
            if data:
                sha = self.storage.sha256(data)
                self.fc_repo.update_pdf_info(
                    canonical_id,
                    str(self.storage._resolve(storage_key)),
                    sha,
                )
                self.db.commit()
                return str(self.storage._resolve(storage_key))
            return None

        pdf_bytes, status = self.fetcher.fetch_pdf(pdf_url)
        if status != 200 or not pdf_bytes:
            logger.error("Failed to download PDF for %s", canonical_id)
            return None

        sha = self.storage.sha256(pdf_bytes)
        local_path = self.storage.store_pdf(self.session_year, bill_id, fc_num, pdf_bytes)
        page_count = None
        try:
            page_count = get_page_count(local_path)
        except Exception:
            pass

        self.fc_repo.update_pdf_info(canonical_id, local_path, sha, page_count)
        self.db.commit()
        logger.info("Downloaded PDF: %s (%d bytes)", canonical_id, len(pdf_bytes))
        return local_path

    # ------------------------------------------------------------------
    # Stage 4: Extract and parse
    # ------------------------------------------------------------------
    def extract_document(
        self, pdf_path: str, canonical_version_id: str
    ) -> ExtractedDocument | None:
        """Extract text from PDF and parse into sections."""
        try:
            pages = extract_text_from_pdf(pdf_path)
        except Exception as e:
            logger.error("PDF extraction failed for %s: %s", canonical_version_id, e)
            return None

        if not pages:
            logger.warning("No pages extracted from %s", canonical_version_id)
            return None

        overall_conf, warnings = compute_overall_confidence(pages)

        # Try OCR fallback if needed
        if needs_ocr_fallback(overall_conf):
            logger.info("Low confidence, attempting OCR for %s", canonical_version_id)
            try:
                from src.extract.ocr_fallback import ocr_all_low_confidence_pages

                pages = ocr_all_low_confidence_pages(pdf_path, pages)
                overall_conf, warnings = compute_overall_confidence(pages)
            except Exception as e:
                logger.warning("OCR fallback failed: %s", e)

        # Normalize
        pages = normalize_pages(pages)

        # Build full text
        full_raw = "\n\n".join(p.raw_text for p in pages)
        full_cleaned = "\n\n".join(p.cleaned_text for p in pages)

        # Parse sections
        total_pages = len(pages)
        sections = parse_sections(full_cleaned, start_page=1, total_pages=total_pages)

        return ExtractedDocument(
            canonical_version_id=canonical_version_id,
            pages=pages,
            full_raw_text=full_raw,
            full_cleaned_text=full_cleaned,
            sections=sections,
            overall_extraction_confidence=overall_conf,
            extraction_warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Stage 5: Diff against prior version
    # ------------------------------------------------------------------
    def diff_version(
        self,
        current_doc: ExtractedDocument,
        bill_db_id: int,
        file_copy_number: int,
    ) -> BillDiffResult:
        """Diff current document against the prior version if one exists."""
        prior_fc = self.fc_repo.get_prior_version(bill_db_id, file_copy_number)

        if prior_fc and prior_fc.local_pdf_path:
            prior_doc = self.extract_document(
                prior_fc.local_pdf_path,
                prior_fc.canonical_version_id,
            )
            if prior_doc:
                result = diff_documents(current_doc, prior_doc)
                result.change_events = classify_changes(result)
                return result

        result = diff_documents(current_doc, None)
        result.change_events = classify_changes(result)
        return result

    # ------------------------------------------------------------------
    # Stage 5b: Enrich bill metadata from status page
    # ------------------------------------------------------------------
    def enrich_bill_status(self, bill_id: str, session_year: int) -> dict | None:
        """Fetch and parse the bill status page, updating the bill record.

        Returns parsed metadata dict or None if fetch failed.
        """
        bill = self.bill_repo.get_by_bill_id(session_year, bill_id)
        if not bill:
            logger.warning("Cannot enrich: bill %s not found", bill_id)
            return None

        # Build status URL
        # CGA format: https://www.cga.ct.gov/asp/cgabillstatus/cgabillstatus.asp?selBillType=Bill&which_year=2026&bill_num=SB00093
        status_url = (
            f"{CGA_BASE_URL}/asp/cgabillstatus/cgabillstatus.asp"
            f"?selBillType=Bill&which_year={session_year}&bill_num={bill_id}"
        )

        html, status = self.fetcher.fetch_html(status_url)
        if status != 200 or not html:
            logger.warning("Failed to fetch status page for %s: %d", bill_id, status)
            return None

        metadata = parse_bill_status_page(html)

        # Update bill record with enriched metadata
        self.bill_repo.upsert(
            session_year=session_year,
            bill_id=bill_id,
            title=metadata.get("title") or bill.current_title,
            committee=metadata.get("committee"),
            status_url=status_url,
        )
        self.db.commit()

        logger.info("Enriched bill %s: committee=%s", bill_id, metadata.get("committee"))
        return metadata

    # ------------------------------------------------------------------
    # Stage 6: Score and summarize
    # ------------------------------------------------------------------
    def score_and_summarize(
        self,
        doc: ExtractedDocument,
        diff_result: BillDiffResult,
        bill_title: str = "",
    ) -> dict:
        """Run subject tagging, summary generation, and persist tags + summary."""
        tags = tag_bill_version(doc, diff_result)
        summary = generate_summary(doc, diff_result, bill_title=bill_title)

        # Persist subject tags
        self.tag_repo.save_tags(tags)

        # Persist summary
        self.summary_repo.save_summary(summary)

        self.db.commit()
        logger.info(
            "Persisted %d subject tags and summary for %s",
            len(tags.subject_tags),
            doc.canonical_version_id,
        )

        return {
            "tags": tags,
            "summary": summary,
            "diff": diff_result,
        }

    # ------------------------------------------------------------------
    # Stage 7: Per-client scoring and alert decisioning
    # ------------------------------------------------------------------
    def score_clients(
        self,
        doc: ExtractedDocument,
        tag_result,
        summary,
        bill_db_id: int,
        committee: str | None = None,
        pdf_url: str = "",
        bill_status_url: str | None = None,
    ) -> list[dict]:
        """Score bill against all active clients and persist decisions."""
        profiles = load_all_profiles(self.client_config_dir)
        if not profiles:
            logger.info("No active client profiles found, skipping scoring")
            return []

        # Ensure clients exist in DB and sync profiles
        self._sync_clients_to_db(profiles)

        results: list[dict] = []
        for profile in profiles:
            client_row = self.client_repo.get_by_client_id(profile.client_id)
            if not client_row:
                continue

            # Score
            score = score_bill_for_client(
                client=profile,
                tag_result=tag_result,
                bill_text=doc.full_cleaned_text,
                committee=committee,
            )

            # Persist score
            self.score_repo.save_score(score, client_row.id, bill_db_id)

            # Alert decisioning with suppression
            decision = decide_alert(
                score=score,
                client_db_id=client_row.id,
                bill_db_id=bill_db_id,
                alert_repo=self.alert_repo,
            )

            # Create alert record for non-duplicate decisions
            alert_row = None
            if decision.should_create_alert:
                payload = build_alert_payload(
                    score=score,
                    summary=summary,
                    file_copy_pdf_url=pdf_url,
                    bill_status_url=bill_status_url,
                )
                alert_row = self.alert_repo.create_alert(
                    client_db_id=client_row.id,
                    bill_db_id=bill_db_id,
                    canonical_version_id=score.version_id,
                    urgency=score.urgency,
                    alert_disposition=decision.final_disposition,
                    alert_text=payload.alert_text,
                    suppression_key=decision.suppression_key,
                )

            results.append({
                "client_id": profile.client_id,
                "score": score,
                "decision": decision,
                "alert_id": alert_row.id if alert_row else None,
            })

            logger.info(
                "Client %s: score=%.0f disposition=%s",
                profile.client_id,
                score.final_score,
                decision.final_disposition,
            )

        self.db.commit()
        return results

    # ------------------------------------------------------------------
    # Stage 8: Deliver alerts via Telegram
    # ------------------------------------------------------------------
    def deliver_alerts(self, client_results: list[dict]) -> dict:
        """Send pending alerts via Telegram. Returns delivery summary."""
        if not self.telegram_sender:
            logger.info("No Telegram sender configured, skipping delivery")
            return {"sent": 0, "failed": 0, "skipped": 0}

        alerts_to_send: list = []
        for cr in client_results:
            alert_id = cr.get("alert_id")
            if not alert_id:
                continue
            decision = cr.get("decision")
            if decision and decision.final_disposition in ("immediate", "digest"):
                alert = self.db.get(Alert, alert_id)
                if alert:
                    alerts_to_send.append(alert)

        if not alerts_to_send:
            return {"sent": 0, "failed": 0, "skipped": 0}

        result = self.telegram_sender.send_pending_alerts(alerts_to_send)
        self.db.commit()
        logger.info(
            "Alert delivery: sent=%d failed=%d skipped=%d",
            result["sent"], result["failed"], result["skipped"],
        )
        return result

    def _sync_clients_to_db(self, profiles: list[ClientProfile]) -> None:
        """Ensure all client profiles are represented in the DB."""
        if self.client_config_dir:
            config_dir = self.client_config_dir
        else:
            config_dir = Path(__file__).parent.parent.parent / "config" / "clients"

        for profile in profiles:
            # Try to load metadata from YAML
            yaml_path = config_dir / f"{profile.client_id}.yaml"
            if yaml_path.exists():
                meta = get_client_metadata(yaml_path)
                client = self.client_repo.upsert(
                    client_id=meta["client_id"],
                    display_name=meta["display_name"],
                    is_active=meta["is_active"],
                    alert_threshold=meta["alert_threshold"],
                    digest_threshold=meta["digest_threshold"],
                )
                self.client_repo.save_profile(client.id, meta["profile_yaml"])
            else:
                self.client_repo.upsert(
                    client_id=profile.client_id,
                    display_name=profile.client_id,
                )
        self.db.flush()

    # ------------------------------------------------------------------
    # Full pipeline run
    # ------------------------------------------------------------------
    def run_daily(self) -> list[dict]:
        """Run the full daily pipeline. Returns results for each new FC."""
        results: list[dict] = []

        # Collect
        rows = self.collect_daily()
        if not rows:
            logger.info("No new file copies to process")
            return results

        # Persist
        new_entries = self.persist_rows(rows)
        if not new_entries:
            logger.info("No new entries after dedup")
            return results

        # Process each new entry
        for entry in new_entries:
            result = self._process_entry(entry)
            if result:
                results.append(result)

        logger.info("Pipeline complete: processed %d entries", len(results))
        return results

    def run_reconciliation(self) -> list[dict]:
        """Run full reconciliation pipeline using all-FC page."""
        results: list[dict] = []

        rows = self.collect_all()
        if not rows:
            return results

        new_entries = self.persist_rows(rows)
        for entry in new_entries:
            result = self._process_entry(entry)
            if result:
                results.append(result)

        logger.info("Reconciliation complete: %d entries", len(results))
        return results

    def _process_entry(self, entry: dict) -> dict | None:
        """Process a single file copy entry through the pipeline."""
        canonical_id = entry["canonical_id"]
        bill_db_id = entry["bill_db_id"]
        bill_id = entry["bill_id"]

        # Download
        pdf_path = self.download_pdf(entry)
        if not pdf_path:
            return None

        # Extract
        doc = self.extract_document(pdf_path, canonical_id)
        if not doc:
            return None

        # Persist extraction and sections
        self.extraction_repo.save_extraction(doc)
        self.section_repo.save_sections(doc)
        self.db.commit()
        logger.info("Persisted extraction for %s", canonical_id)

        # Diff
        diff_result = self.diff_version(doc, bill_db_id, entry["file_copy_number"])

        # Persist diff and change events
        self.diff_repo.save_diff(diff_result, bill_db_id)
        self.db.commit()
        logger.info("Persisted diff for %s", canonical_id)

        # Enrich bill metadata from status page (best-effort, non-blocking)
        try:
            self.enrich_bill_status(bill_id, self.session_year)
        except Exception as e:
            logger.warning("Bill status enrichment failed for %s: %s", bill_id, e)

        # Score and summarize (includes tag persistence)
        bill = self.bill_repo.get_by_bill_id(self.session_year, bill_id)
        bill_title = bill.current_title if bill else ""
        result = self.score_and_summarize(doc, diff_result, bill_title=bill_title)
        result["canonical_id"] = canonical_id
        result["bill_id"] = bill_id
        result["file_copy_number"] = entry["file_copy_number"]

        # Per-client scoring and alert decisioning
        try:
            client_results = self.score_clients(
                doc=doc,
                tag_result=result["tags"],
                summary=result["summary"],
                bill_db_id=bill_db_id,
                committee=bill.committee_name if bill else None,
                pdf_url=entry.get("pdf_url", ""),
                bill_status_url=bill.bill_status_url if bill else None,
            )
            result["client_scores"] = client_results
            logger.info(
                "Scored %d clients for %s", len(client_results), canonical_id
            )

            # Deliver alerts via Telegram
            try:
                delivery = self.deliver_alerts(client_results)
                result["delivery"] = delivery
            except Exception as e:
                logger.warning("Alert delivery failed for %s: %s", canonical_id, e)
                result["delivery"] = {"sent": 0, "failed": 0, "skipped": 0, "error": str(e)}

        except Exception as e:
            logger.warning("Client scoring failed for %s: %s", canonical_id, e)
            result["client_scores"] = []

        return result
