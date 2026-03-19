"""Tests for text normalization."""

from src.extract.normalize_text import normalize_full_text, normalize_pages
from src.schemas.extraction import PageText


class TestNormalizeFullText:
    def test_removes_standalone_page_numbers(self):
        text = "Some text\n\n42\n\nMore text"
        result = normalize_full_text(text)
        assert "\n42\n" not in result
        assert "Some text" in result
        assert "More text" in result

    def test_repairs_hyphenation(self):
        text = "This is a transpor-\ntation bill."
        result = normalize_full_text(text)
        assert "transportation" in result

    def test_collapses_blank_lines(self):
        text = "Line 1\n\n\n\n\nLine 2"
        result = normalize_full_text(text)
        assert "\n\n\n" not in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_removes_trailing_whitespace(self):
        text = "Line with spaces   \nNext line"
        result = normalize_full_text(text)
        lines = result.split("\n")
        for line in lines:
            assert line == line.rstrip()

    def test_preserves_section_markers(self):
        text = "Section 1. This is the first section.\n\nSec. 2. This is the second."
        result = normalize_full_text(text)
        assert "Section 1." in result
        assert "Sec. 2." in result


class TestNormalizePages:
    def test_header_footer_removal(self):
        # Create pages with repeated headers/footers
        pages = []
        for i in range(5):
            pages.append(
                PageText(
                    page_number=i + 1,
                    raw_text=f"REPEATED HEADER\nPage content {i}\nPAGE FOOTER",
                    cleaned_text="",
                    extraction_method="text",
                    extraction_confidence=0.9,
                )
            )

        result = normalize_pages(pages)
        # Headers/footers should be removed (they appear >= 3 times)
        for page in result:
            assert "REPEATED HEADER" not in page.cleaned_text
            assert "PAGE FOOTER" not in page.cleaned_text
            assert "Page content" in page.cleaned_text

    def test_raw_text_preserved(self):
        pages = [
            PageText(
                page_number=1,
                raw_text="Original raw text",
                cleaned_text="",
                extraction_method="text",
                extraction_confidence=0.9,
            )
        ]
        result = normalize_pages(pages)
        assert result[0].raw_text == "Original raw text"

    def test_page_number_removal(self):
        pages = [
            PageText(
                page_number=1,
                raw_text="Content here\n\n42\n\nMore content",
                cleaned_text="",
                extraction_method="text",
                extraction_confidence=0.9,
            )
        ]
        result = normalize_pages(pages)
        assert "Content here" in result[0].cleaned_text
        assert "More content" in result[0].cleaned_text
