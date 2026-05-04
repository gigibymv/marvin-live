"""SEC EDGAR full-text retrieval client.

Replaces the previous stubbed `search_sec_filings` that returned hardcoded
fake URLs. Real EDGAR access requires:
  - a User-Agent identifying the requester (SEC fair-access policy)
  - ticker/name → CIK resolution via company_tickers.json
  - submissions feed via data.sec.gov for the recent filings index
  - HTML primary document fetch from www.sec.gov/Archives

Section extraction is deliberately heuristic: 10-K/10-Q HTML is highly
variable across registrants and years. We aim to recover the four sections
that matter for CDD (Business, Risk Factors, MD&A, Financial Statements)
with bounded recall — when a section can't be cleanly delimited, we return
None so the caller can decide whether to ingest the full body or surface
a gap rather than synthesize from noise.
"""
from __future__ import annotations

import logging
import os
import re
from html.parser import HTMLParser
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_ARCHIVE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{document}"
)
_TIMEOUT_S = 30.0

_HTTP_CLIENT_FACTORY = httpx.Client

_COMPANY_ALIASES: dict[str, str] = {
    "meta": "META",
    "meta platforms": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "netflix inc": "NFLX",
    "nvidia": "NVDA",
    "nvidia corporation": "NVDA",
    "uber": "UBER",
    "uber technologies": "UBER",
    "uber technologies inc": "UBER",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "alphabet inc": "GOOGL",
}

_COMPANY_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "plc",
}


def _normalize_company_key(value: str) -> str:
    """Normalize company names for EDGAR title matching.

    EDGAR's ticker list uses formal registrant names such as
    "Uber Technologies, Inc." while mission briefs often pass
    "Uber Technologies Inc" or "Uber, mobility platform". Keep this narrow:
    punctuation/suffix cleanup only, no fuzzy similarity or fallback company.
    """
    raw_tokens = re.findall(r"[a-z0-9]+", value.lower())
    tokens = [tok for tok in raw_tokens if tok not in _COMPANY_SUFFIXES]
    return " ".join(tokens)


def _user_agent() -> str:
    ua = os.environ.get("MARVIN_SEC_USER_AGENT")
    if ua:
        return ua
    contact = os.environ.get("MARVIN_SEC_CONTACT_EMAIL", "contact@example.org")
    return f"MARVIN CDD Platform ({contact})"


def _client(**kwargs: Any) -> httpx.Client:
    # NOTE: do not set the Host header here. EDGAR uses two distinct hosts
    # (www.sec.gov for archives + tickers, data.sec.gov for submissions).
    # Forcing Host to one breaks the other with a 404. Let httpx derive
    # Host from each request URL.
    headers = {
        "User-Agent": _user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }
    return _HTTP_CLIENT_FACTORY(timeout=_TIMEOUT_S, headers=headers, **kwargs)


_TICKER_CACHE: dict[str, dict[str, Any]] | None = None


def resolve_cik(company_name_or_ticker: str) -> dict[str, Any] | None:
    """Resolve a ticker or company name to its 10-digit zero-padded CIK.

    Returns {"cik": "0000000000", "ticker": "...", "title": "..."} or None.
    Tries exact ticker match first (case-insensitive), then case-insensitive
    substring on the registered title.
    """
    global _TICKER_CACHE
    needle = company_name_or_ticker.strip()
    if not needle:
        return None

    if _TICKER_CACHE is None:
        try:
            with _client() as c:
                r = c.get(_TICKERS_URL)
                r.raise_for_status()
                payload = r.json()
        except httpx.HTTPError as exc:
            logger.warning("EDGAR ticker fetch failed: %s", exc)
            return None
        _TICKER_CACHE = {}
        for _, entry in payload.items():
            ticker = str(entry.get("ticker", "")).upper()
            cik = str(entry.get("cik_str", "")).zfill(10)
            title = str(entry.get("title", ""))
            if ticker:
                _TICKER_CACHE[ticker] = {"cik": cik, "ticker": ticker, "title": title}

    upper = needle.upper()
    needle_lower = needle.lower()
    normalized_needle = _normalize_company_key(needle)
    alias = _COMPANY_ALIASES.get(needle_lower) or _COMPANY_ALIASES.get(normalized_needle)
    if alias and alias in _TICKER_CACHE:
        return _TICKER_CACHE[alias]
    if upper in _TICKER_CACHE:
        return _TICKER_CACHE[upper]
    for alias_name, alias_ticker in _COMPANY_ALIASES.items():
        if (
            alias_name in needle_lower
            or alias_name in normalized_needle
            or _normalize_company_key(alias_name) in normalized_needle
        ) and alias_ticker in _TICKER_CACHE:
            return _TICKER_CACHE[alias_ticker]
    for entry in _TICKER_CACHE.values():
        title_lower = entry["title"].lower()
        normalized_title = _normalize_company_key(entry["title"])
        if needle_lower in title_lower:
            return entry
        if normalized_needle and (
            normalized_needle == normalized_title
            or normalized_needle in normalized_title
            or normalized_title in normalized_needle
        ):
            return entry
    return None


def list_filings(
    cik: str,
    forms: tuple[str, ...] = ("10-K", "10-Q", "20-F", "8-K"),
    since_year: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fetch the recent filings index for a CIK and filter by form/year.

    Returns a list of {form, accession, filing_date, primary_document,
    report_date, url}. Empty list on network failure (logged).
    """
    cik10 = cik.zfill(10)
    url = _SUBMISSIONS_URL.format(cik10=cik10)
    try:
        with _client() as c:
            r = c.get(url)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        logger.warning("EDGAR submissions fetch failed for CIK %s: %s", cik, exc)
        return []

    recent = (data.get("filings") or {}).get("recent") or {}
    accs = recent.get("accessionNumber") or []
    forms_arr = recent.get("form") or []
    dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    docs = recent.get("primaryDocument") or []

    filings: list[dict[str, Any]] = []
    cik_int = str(int(cik))
    for acc, form, fdate, rdate, doc in zip(accs, forms_arr, dates, report_dates, docs):
        if form not in forms:
            continue
        if since_year is not None and fdate:
            try:
                yr = int(fdate.split("-")[0])
            except (ValueError, IndexError):
                yr = 0
            if yr < since_year:
                continue
        accession_nodash = acc.replace("-", "")
        filings.append(
            {
                "form": form,
                "accession": acc,
                "filing_date": fdate,
                "report_date": rdate,
                "primary_document": doc,
                "url": _ARCHIVE_URL.format(
                    cik=cik_int, accession_nodash=accession_nodash, document=doc
                ),
            }
        )
        if len(filings) >= limit:
            break
    return filings


def list_filings_result(
    cik: str,
    forms: tuple[str, ...] = ("10-K", "10-Q", "20-F", "8-K"),
    since_year: int | None = None,
    limit: int = 20,
    max_scan: int | None = None,
) -> dict[str, Any]:
    """Fetch recent filings while preserving why a result set is empty.

    ``max_scan`` bounds how many recent EDGAR rows we inspect before applying
    form/year filters. It intentionally differs from ``limit`` so active
    registrants with many 8-K/Form 4 rows do not hide the relevant 10-K/10-Q
    before fiscal-year matching happens upstream.
    """
    cik10 = cik.zfill(10)
    url = _SUBMISSIONS_URL.format(cik10=cik10)
    try:
        with _client() as c:
            r = c.get(url)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("EDGAR submissions fetch failed for CIK %s: %s", cik, exc)
        status = exc.response.status_code if exc.response is not None else None
        return {
            "filings": [],
            "error": "edgar_rate_limited" if status == 429 else "edgar_submissions_fetch_failed",
        }
    except httpx.HTTPError as exc:
        logger.warning("EDGAR submissions fetch failed for CIK %s: %s", cik, exc)
        return {"filings": [], "error": "edgar_submissions_fetch_failed"}

    recent = (data.get("filings") or {}).get("recent") or {}
    accs = recent.get("accessionNumber") or []
    forms_arr = recent.get("form") or []
    dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    docs = recent.get("primaryDocument") or []

    filings: list[dict[str, Any]] = []
    cik_int = str(int(cik))
    for scanned, (acc, form, fdate, rdate, doc) in enumerate(
        zip(accs, forms_arr, dates, report_dates, docs)
    ):
        if max_scan is not None and scanned >= max_scan:
            break
        if form not in forms:
            continue
        if since_year is not None and fdate:
            try:
                yr = int(fdate.split("-")[0])
            except (ValueError, IndexError):
                yr = 0
            if yr < since_year:
                continue
        accession_nodash = acc.replace("-", "")
        filings.append(
            {
                "form": form,
                "accession": acc,
                "filing_date": fdate,
                "report_date": rdate,
                "primary_document": doc,
                "url": _ARCHIVE_URL.format(
                    cik=cik_int, accession_nodash=accession_nodash, document=doc
                ),
            }
        )
        if len(filings) >= limit:
            break
    return {"filings": filings, "error": None}


class _TextOnly(HTMLParser):
    """Strip HTML to text while preserving block-level whitespace."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip > 0:
            self._skip -= 1
        elif tag in {"p", "div", "tr", "li", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        text = "".join(self._chunks)
        text = re.sub(r"\xa0", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()


def fetch_filing_text(filing: dict[str, Any]) -> str:
    """Fetch a filing's primary document and return cleaned text.

    `filing` must carry a `url` field (from list_filings). Returns "" on
    failure. The text is HTML-stripped; tables are linearized but not
    parsed structurally.
    """
    url = filing.get("url")
    if not url:
        return ""
    try:
        with _client() as c:
            r = c.get(url)
            r.raise_for_status()
            body = r.text
    except httpx.HTTPError as exc:
        logger.warning("EDGAR document fetch failed for %s: %s", url, exc)
        return ""
    parser = _TextOnly()
    try:
        parser.feed(body)
    except Exception as exc:
        logger.warning("EDGAR HTML parse failed for %s: %s", url, exc)
        return body
    return parser.get_text()


# Section delimiters for 10-K. 10-Q sections are similar (Item 2 = MD&A,
# Item 1 = financials) but we keep the 10-K mapping authoritative for now.
_SECTION_PATTERNS = {
    "business": [r"item\s*1\b\.?\s*business"],
    "risk_factors": [r"item\s*1a\b\.?\s*risk\s*factors"],
    "mdna": [
        r"item\s*7\b\.?\s*management.s\s+discussion",
        r"item\s*2\b\.?\s*management.s\s+discussion",
    ],
    "financial_statements": [
        r"item\s*8\b\.?\s*financial\s+statements",
        r"item\s*1\b\.?\s*financial\s+statements",
    ],
}

_NEXT_ITEM = re.compile(r"\n\s*item\s*\d+[a-z]?\b\.?", re.IGNORECASE)


def extract_sections(text: str) -> dict[str, str | None]:
    """Best-effort 10-K section extraction by Item header.

    Returns {business, risk_factors, mdna, financial_statements}. Unfound
    sections are None. The caller should treat None as "no section
    isolated; do not synthesize quotes from this section."

    Real 10-K HTML usually contains the Item header at least twice: once
    in the table of contents (with no body) and once at the actual
    section. We iterate all occurrences and keep the first chunk that
    exceeds the body-length threshold.
    """
    out: dict[str, str | None] = {k: None for k in _SECTION_PATTERNS}
    for section, patterns in _SECTION_PATTERNS.items():
        chosen: str | None = None
        best_len = 0
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                start = m.end()
                tail = text[start:]
                n = _NEXT_ITEM.search(tail)
                end = n.start() if n else len(tail)
                chunk = tail[:end].strip()
                if len(chunk) >= 200 and len(chunk) > best_len:
                    chosen = chunk
                    best_len = len(chunk)
            if chosen:
                break
        out[section] = chosen
    return out
