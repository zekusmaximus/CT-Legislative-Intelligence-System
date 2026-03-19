"""Collector for the CGA all-file-copies session page (backfill/reconciliation)."""

import hashlib
from datetime import date, datetime

from bs4 import BeautifulSoup

from src.schemas.intake import FileCopyListingRow, SourcePageRecord
from src.utils.bill_id import normalize_bill_id

CGA_BASE_URL = "https://www.cga.ct.gov"


def parse_all_filecopies_page(
    html: str,
    session_year: int,
    source_url: str = "",
    fetched_at: datetime | None = None,
) -> tuple[SourcePageRecord, list[FileCopyListingRow]]:
    """Parse the all-file-copies session page.

    This page has an additional 'Date' column compared to the daily page.
    """
    fetched_at = fetched_at or datetime.now()
    content_sha256 = hashlib.sha256(html.encode()).hexdigest()

    source_record = SourcePageRecord(
        source_type="all_filecopies",
        source_url=(
            source_url
            or f"{CGA_BASE_URL}/asp/cgabillstatus/CGABillCopy.asp?which_year={session_year}"
        ),
        fetched_at=fetched_at,
        content_sha256=content_sha256,
        http_status=200,
        session_year=session_year,
    )

    soup = BeautifulSoup(html, "lxml")
    rows: list[FileCopyListingRow] = []

    table = _find_table(soup)
    if table is None:
        return source_record, rows

    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue

        row = _parse_row(tds, session_year, str(source_record.source_url))
        if row is not None:
            rows.append(row)

    return source_record, rows


def _find_table(soup: BeautifulSoup):
    """Find the file-copies data table."""
    for table in soup.find_all("table"):
        header_text = table.get_text(strip=True).lower()
        if "bill no" in header_text and "date" in header_text:
            return table
    for table in soup.find_all("table"):
        if len(table.find_all("tr")) > 1:
            return table
    return None


def _parse_row(
    tds: list,
    session_year: int,
    source_url: str,
) -> FileCopyListingRow | None:
    """Parse a row from the all-file-copies table (5 columns: Bill, Title, File No, Date, PDF)."""
    try:
        # Column 0: Bill number
        bill_display = tds[0].get_text(strip=True)
        bill_id = normalize_bill_id(bill_display)

        # Column 1: Title
        title = tds[1].get_text(strip=True)

        # Column 2: File copy number
        file_copy_number = int(tds[2].get_text(strip=True))

        # Column 3: Date (MM/DD/YYYY)
        date_text = tds[3].get_text(strip=True)
        listing_date = _parse_date(date_text)

        # Column 4: PDF link
        pdf_link = tds[4].find("a")
        if pdf_link and pdf_link.get("href"):
            href = pdf_link["href"]
            pdf_url = f"{CGA_BASE_URL}{href}" if href.startswith("/") else href
        else:
            return None

        return FileCopyListingRow(
            session_year=session_year,
            bill_id=bill_id,
            bill_number_display=bill_display,
            bill_title=title,
            file_copy_number=file_copy_number,
            file_copy_pdf_url=pdf_url,
            listing_date=listing_date or date.today(),
            listing_source_url=source_url,
        )
    except (ValueError, IndexError, AttributeError):
        return None


def _parse_date(text: str) -> date | None:
    """Parse date from MM/DD/YYYY format."""
    try:
        return datetime.strptime(text.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None
