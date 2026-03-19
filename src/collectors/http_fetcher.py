"""HTTP fetcher with retry and rate-limiting for CGA pages."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF = 2.0
DEFAULT_RATE_LIMIT_DELAY = 1.0

# Standard headers to mimic a browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (CT-Legislative-Intelligence-System; research-bot) AppleWebKit/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class CGAFetcher:
    """Fetch pages from the CGA website with retry and rate limiting."""

    def __init__(
        self,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time: float = 0.0

    def fetch_html(self, url: str) -> tuple[str, int]:
        """Fetch an HTML page. Returns (html_content, http_status)."""
        self._rate_limit()

        for attempt in range(self.max_retries):
            try:
                response = httpx.get(
                    url,
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers=_HEADERS,
                )
                self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    return response.text, 200

                logger.warning(
                    "Non-200 response: %d for %s",
                    response.status_code,
                    url,
                )
                return response.text, response.status_code

            except httpx.HTTPError as e:
                wait = self.backoff_factor * (2**attempt)
                logger.warning(
                    "Request failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    self.max_retries,
                    e,
                    wait,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(wait)

        logger.error("All retries exhausted for %s", url)
        return "", 0

    def fetch_pdf(self, url: str) -> tuple[bytes, int]:
        """Fetch a PDF file. Returns (pdf_bytes, http_status)."""
        self._rate_limit()

        for attempt in range(self.max_retries):
            try:
                response = httpx.get(
                    url,
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers=_HEADERS,
                )
                self._last_request_time = time.monotonic()

                if response.status_code == 200:
                    return response.content, 200

                logger.warning(
                    "Non-200 response: %d for PDF %s",
                    response.status_code,
                    url,
                )
                return b"", response.status_code

            except httpx.HTTPError as e:
                wait = self.backoff_factor * (2**attempt)
                logger.warning(
                    "PDF download failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(wait)

        logger.error("All retries exhausted for PDF %s", url)
        return b"", 0

    def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        if self._last_request_time > 0:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
