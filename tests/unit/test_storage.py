"""Tests for local file storage adapter."""

import tempfile
from pathlib import Path

from src.utils.storage import LocalStorage


class TestLocalStorage:
    def test_store_and_retrieve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            storage.store("test/file.txt", b"hello world")
            result = storage.retrieve("test/file.txt")
            assert result == b"hello world"

    def test_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            assert storage.exists("test/missing.txt") is False
            storage.store("test/file.txt", b"data")
            assert storage.exists("test/file.txt") is True

    def test_retrieve_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            assert storage.retrieve("nonexistent") is None

    def test_store_pdf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            path = storage.store_pdf(2026, "SB00093", 44, b"%PDF-fake")
            assert Path(path).exists()
            assert "SB00093" in path
            assert "FC00044" in path

    def test_store_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = LocalStorage(tmpdir)
            path = storage.store_html("daily_filecopies", 2026, "abc123", b"<html>test</html>")
            assert Path(path).exists()
            assert "abc123" in path

    def test_sha256(self):
        result = LocalStorage.sha256(b"test data")
        assert len(result) == 64
        assert result == LocalStorage.sha256(b"test data")  # deterministic
        assert result != LocalStorage.sha256(b"different")
