"""PDF downloader with idempotency checks."""

import logging

import httpx

from src.utils.storage import LocalStorage

logger = logging.getLogger(__name__)


class PDFDownloader:
    """Downloads PDFs from CGA with idempotency."""

    def __init__(self, storage: LocalStorage, timeout: int = 30):
        self.storage = storage
        self.timeout = timeout

    def download(
        self,
        pdf_url: str,
        session_year: int,
        bill_id: str,
        file_copy_number: int,
    ) -> tuple[str, str] | None:
        """Download a PDF if not already stored.

        Returns (local_path, sha256) or None on failure.
        """
        storage_key = f"pdfs/{session_year}/{bill_id}/FC{file_copy_number:05d}.pdf"

        if self.storage.exists(storage_key):
            data = self.storage.retrieve(storage_key)
            if data:
                sha = self.storage.sha256(data)
                logger.info(
                    "PDF already exists, skipping download",
                    extra={"bill_id": bill_id, "file_copy": file_copy_number},
                )
                return str(self.storage._resolve(storage_key)), sha

        try:
            response = httpx.get(pdf_url, timeout=self.timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(
                "Failed to download PDF: %s",
                e,
                extra={"pdf_url": pdf_url, "bill_id": bill_id},
            )
            return None

        data = response.content
        if not data or len(data) < 100:
            logger.warning(
                "Downloaded PDF is suspiciously small",
                extra={"pdf_url": pdf_url, "size": len(data)},
            )
            return None

        sha = self.storage.sha256(data)
        local_path = self.storage.store_pdf(session_year, bill_id, file_copy_number, data)
        logger.info(
            "Downloaded PDF successfully",
            extra={
                "bill_id": bill_id,
                "file_copy": file_copy_number,
                "size": len(data),
                "sha256": sha[:12],
            },
        )
        return local_path, sha

    def download_bytes(
        self, data: bytes, session_year: int, bill_id: str, file_copy_number: int
    ) -> tuple[str, str]:
        """Store already-downloaded PDF bytes. Used in testing."""
        sha = self.storage.sha256(data)
        local_path = self.storage.store_pdf(session_year, bill_id, file_copy_number, data)
        return local_path, sha
