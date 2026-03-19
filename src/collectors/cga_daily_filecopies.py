"""Collector for the CGA daily file-copies page."""

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from src.schemas.intake import FileCopyListingRow, SourcePageRecord
from src.utils.bill_id import normalize_bill_id

CGA_BASE_URL = "https://www.cga.ct.gov"
DAILY_FC_URL = f"{CGA_BASE_URL}/asp/cgabillstatus/CGABillCopy.asp"

# Pattern to extract bill number from display text like "S.B. No. 93" or "H.B. No. 5140"
_BILL_DISPLAY_RE = re.compile(r"(S\.B\.|H\.B\.)\s*No\.?\s*(\d+)", re.IGNORECASE)

# Pattern to extract date from heading like "File Copies for Wednesday, March 18, 2026"
_DATE_HEADING_RE = re.compile(r"File\s+Copies\s+for\s+\w+,\s+(\w+\s+\d+,\s+\d{4})", re.IGNORECASE)


def parse_daily_filecopies_page(
    html: str,
    session_year: int,
    source_url: str = DAILY_FC_URL,
    fetched_at: datetime | None = None,
) -> tuple[SourcePageRecord, list[FileCopyListingRow]]:
    """Parse the daily file-copies HTML page into structured records.

    Returns a tuple of (source page record, list of file-copy listing rows).
    """
    import hashlib

    fetched_at = fetched_at or datetime.now()
    content_sha256 = hashlib.sha256(html.encode()).hexdigest()

    source_record = SourcePageRecord(
        source_type="daily_filecopies",
        source_url=source_url,
        fetched_at=fetched_at,
        content_sha256=content_sha256,
        http_status=200,
        session_year=session_year,
    )

    soup = BeautifulSoup(html, "lxml")

    # Try to extract listing date from page heading
    listing_date = _extract_listing_date(soup)

    rows: list[FileCopyListingRow] = []
    table = _find_filecopies_table(soup)
    if table is None:
        return source_record, rows

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 4:
            continue

        row = _parse_table_row(tds, session_year, listing_date, source_url)
        if row is not None:
            rows.append(row)

    return source_record, rows


def _find_filecopies_table(soup: BeautifulSoup):
    """Find the main file-copies data table."""
    # Look for table with header row containing "Bill No." or "File No."
    for table in soup.find_all("table"):
        header_text = table.get_text(strip=True).lower()
        if "bill no" in header_text and ("file no" in header_text or "file copy" in header_text):
            return table
    # Fallback: first table with multiple rows
    tables = soup.find_all("table")
    for table in tables:
        if len(table.find_all("tr")) > 1:
            return table
    return None


def _extract_listing_date(soup: BeautifulSoup) -> date | None:
    """Try to extract the listing date from page heading."""
    from datetime import datetime as dt

    for heading in soup.find_all(["h1", "h2", "h3"]):
        match = _DATE_HEADING_RE.search(heading.get_text())
        if match:
            try:
                return dt.strptime(match.group(1), "%B %d, %Y").date()
            except ValueError:
                continue
    return None


def _parse_table_row(
    tds: list,
    session_year: int,
    listing_date: date | None,
    source_url: str,
) -> FileCopyListingRow | None:
    """Parse a single table row into a FileCopyListingRow."""
    try:
        # Column 0: Bill number with link
        bill_cell = tds[0]
        bill_display = bill_cell.get_text(strip=True)
        bill_id = normalize_bill_id(bill_display)

        # Column 1: Title
        title = tds[1].get_text(strip=True)

        # Column 2: File copy number
        fc_num_text = tds[2].get_text(strip=True)
        file_copy_number = int(fc_num_text)

        # Column 3: PDF link
        pdf_cell = tds[3]
        pdf_link = pdf_cell.find("a")
        if pdf_link and pdf_link.get("href"):
            pdf_href = pdf_link["href"]
            if pdf_href.startswith("/"):
                pdf_url = f"{CGA_BASE_URL}{pdf_href}"
            else:
                pdf_url = pdf_href
        else:
            return None

        # Use today if listing date not found
        effective_date = listing_date or date.today()

        return FileCopyListingRow(
            session_year=session_year,
            bill_id=bill_id,
            bill_number_display=bill_display,
            bill_title=title,
            file_copy_number=file_copy_number,
            file_copy_pdf_url=pdf_url,
            listing_date=effective_date,
            listing_source_url=source_url,
        )
    except (ValueError, IndexError, AttributeError):
        return None
