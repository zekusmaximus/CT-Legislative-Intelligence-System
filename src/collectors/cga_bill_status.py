"""Collector for CGA bill status pages."""

from bs4 import BeautifulSoup


def parse_bill_status_page(html: str) -> dict:
    """Parse a bill status page and extract key metadata.

    Returns a dict with keys: title, committee, introduced_by, history.
    """
    soup = BeautifulSoup(html, "lxml")

    title = _extract_title(soup)
    committee = _extract_committee(soup)
    introduced_by = _extract_introduced_by(soup)
    history = _extract_history(soup)
    statement_of_purpose = _extract_statement_of_purpose(soup)

    return {
        "title": title,
        "committee": committee,
        "introduced_by": introduced_by,
        "statement_of_purpose": statement_of_purpose,
        "history": history,
    }


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract bill title from the page."""
    # Try class-based selectors first
    title_el = soup.find(class_="billtitleheader")
    if title_el:
        return title_el.get_text(strip=True)

    # Fallback: look for "AN ACT" pattern in the page
    for td in soup.find_all("td"):
        text = td.get_text(strip=True)
        if text.upper().startswith("AN ACT"):
            return text

    return ""


def _extract_committee(soup: BeautifulSoup) -> str:
    """Extract committee name."""
    for td in soup.find_all("td"):
        if td.find("b") and "committee" in td.get_text(strip=True).lower():
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(strip=True)
    return ""


def _extract_introduced_by(soup: BeautifulSoup) -> str:
    """Extract introducer information."""
    for td in soup.find_all("td"):
        if td.find("b") and "introduced by" in td.get_text(strip=True).lower():
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(strip=True)
    return ""


def _extract_statement_of_purpose(soup: BeautifulSoup) -> str:
    """Extract statement of purpose."""
    for td in soup.find_all("td"):
        if td.find("b") and "statement of purpose" in td.get_text(strip=True).lower():
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(strip=True)
    return ""


def _extract_history(soup: BeautifulSoup) -> list[dict]:
    """Extract bill history timeline entries."""
    entries = []
    # Look for history section after an h3
    history_heading = None
    for h in soup.find_all(["h3", "h4"]):
        if "history" in h.get_text(strip=True).lower():
            history_heading = h
            break

    if history_heading:
        table = history_heading.find_next("table")
        if table:
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    entries.append(
                        {
                            "date": tds[0].get_text(strip=True),
                            "action": tds[1].get_text(strip=True),
                        }
                    )

    return entries
