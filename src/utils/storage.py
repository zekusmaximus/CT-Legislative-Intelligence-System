"""Local file storage adapter for PDFs and raw HTML."""

import hashlib
from pathlib import Path


class LocalStorage:
    """Store and retrieve files on local disk."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def store(self, key: str, data: bytes) -> str:
        """Store bytes under the given key. Returns the absolute path."""
        path = self._resolve(key)
        path.write_bytes(data)
        return str(path)

    def retrieve(self, key: str) -> bytes | None:
        """Retrieve bytes by key, or None if not found."""
        path = self._resolve(key)
        if path.exists():
            return path.read_bytes()
        return None

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def store_pdf(self, session_year: int, bill_id: str, file_copy_number: int, data: bytes) -> str:
        """Store a PDF with a standardized key structure."""
        key = f"pdfs/{session_year}/{bill_id}/FC{file_copy_number:05d}.pdf"
        return self.store(key, data)

    def store_html(
        self, source_type: str, session_year: int, content_hash: str, data: bytes
    ) -> str:
        """Store raw HTML source page."""
        key = f"html/{session_year}/{source_type}/{content_hash}.html"
        return self.store(key, data)

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
