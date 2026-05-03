"""Wiring tests for the EDGAR client + calculus tools.

These tests mock httpx via the `_HTTP_CLIENT_FACTORY` injection point so
we never hit the live SEC endpoint. They verify:
  - resolve_cik handles ticker + name lookup and missing entries
  - list_filings returns parsed entries with real URLs
  - fetch_filing_text strips HTML safely
  - extract_sections recovers Item 1A / Item 7 from real-shaped 10-K HTML
  - search_sec_filings + fetch_filing_section return structured failures
    when the company is unknown (no fabricated citation)
"""
from __future__ import annotations

import json

import httpx
import pytest


def _factory(handler):
    def _make(**kwargs):
        kwargs.pop("headers", None)
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
    return _make


SAMPLE_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    "2": {"cik_str": 1326801, "ticker": "META", "title": "Meta Platforms, Inc."},
    "3": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corp"},
}

SAMPLE_SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": ["0000320193-24-000123", "0000320193-23-000456"],
            "form": ["10-K", "10-K"],
            "filingDate": ["2024-11-01", "2023-11-03"],
            "reportDate": ["2024-09-28", "2023-09-30"],
            "primaryDocument": ["aapl-20240928.htm", "aapl-20230930.htm"],
        }
    }
}

UBER_FY2024_FILED_2025_SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": ["0001543151-25-000012", "0001543151-24-000010"],
            "form": ["10-K", "10-K"],
            "filingDate": ["2025-02-14", "2024-02-15"],
            "reportDate": ["2024-12-31", "2023-12-31"],
            "primaryDocument": ["uber-20241231.htm", "uber-20231231.htm"],
        }
    }
}

SAMPLE_10K_HTML = """
<html><body>
<h1>Apple Inc. Annual Report</h1>
<p>Cover stuff and TOC.</p>
<h2>Item 1. Business</h2>
<p>The Company designs, manufactures and markets smartphones, personal
computers, tablets, wearables and accessories. This Business section
must be at least two hundred characters long for the extractor to keep
it as a real section rather than discarding it as noise. Adding more
filler so the threshold is exceeded comfortably.</p>
<h2>Item 1A. Risk Factors</h2>
<p>The Company's business, reputation, results of operations and
financial condition can be affected by many factors. We need this
section to also exceed two hundred characters of body text so the
extractor returns it. So here is some additional padding text to make
that happen reliably across runs.</p>
<h2>Item 7. Management's Discussion and Analysis of Financial Condition</h2>
<p>Total net sales increased 2% during 2024 compared to 2023. The MD&A
section needs to be long enough that the heuristic accepts it. We pad
it with realistic-sounding commentary about gross margins and segment
performance to ensure two hundred characters are exceeded.</p>
<h2>Item 8. Financial Statements and Supplementary Data</h2>
<p>The Consolidated Statements of Operations are presented below.
Padding to make this section also exceed the two-hundred-character
floor used by the extractor when isolating sections.</p>
</body></html>
"""


def _make_handler(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, response in routes.items():
            if url.startswith(prefix):
                if isinstance(response, dict):
                    return httpx.Response(200, json=response)
                return httpx.Response(200, text=response)
        return httpx.Response(404, text="not found")
    return handler


@pytest.fixture(autouse=True)
def _reset_ticker_cache():
    import marvin.tools.edgar_client as ec
    ec._TICKER_CACHE = None
    yield
    ec._TICKER_CACHE = None


def test_resolve_cik_by_ticker(monkeypatch):
    import marvin.tools.edgar_client as ec
    handler = _make_handler({"https://www.sec.gov/files/company_tickers.json": SAMPLE_TICKERS})
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    out = ec.resolve_cik("AAPL")
    assert out is not None
    assert out["cik"] == "0000320193"
    assert out["ticker"] == "AAPL"


def test_resolve_cik_by_name_substring(monkeypatch):
    import marvin.tools.edgar_client as ec
    handler = _make_handler({"https://www.sec.gov/files/company_tickers.json": SAMPLE_TICKERS})
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    out = ec.resolve_cik("microsoft")
    assert out is not None
    assert out["ticker"] == "MSFT"


def test_resolve_cik_uses_common_company_aliases(monkeypatch):
    import marvin.tools.edgar_client as ec
    tickers = {
        **SAMPLE_TICKERS,
        "4": {"cik_str": 1543151, "ticker": "UBER", "title": "Uber Technologies, Inc."},
    }
    handler = _make_handler({"https://www.sec.gov/files/company_tickers.json": tickers})
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))

    meta = ec.resolve_cik("Meta, social media / digital advertising, global")
    nvidia = ec.resolve_cik("Nvidia, semiconductors / AI infrastructure, global")
    uber = ec.resolve_cik("Uber, mobility and delivery platform, global")

    assert meta is not None
    assert meta["ticker"] == "META"
    assert nvidia is not None
    assert nvidia["ticker"] == "NVDA"
    assert uber is not None
    assert uber["ticker"] == "UBER"


def test_resolve_cik_normalizes_company_suffixes(monkeypatch):
    import marvin.tools.edgar_client as ec
    tickers = {
        **SAMPLE_TICKERS,
        "4": {"cik_str": 1543151, "ticker": "UBER", "title": "Uber Technologies, Inc."},
    }
    handler = _make_handler({"https://www.sec.gov/files/company_tickers.json": tickers})
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))

    out = ec.resolve_cik("Uber Technologies Inc")

    assert out is not None
    assert out["ticker"] == "UBER"


def test_resolve_cik_missing(monkeypatch):
    import marvin.tools.edgar_client as ec
    handler = _make_handler({"https://www.sec.gov/files/company_tickers.json": SAMPLE_TICKERS})
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    assert ec.resolve_cik("nonexistent-co-xyz") is None


def test_list_filings_filters_by_form_and_year(monkeypatch):
    import marvin.tools.edgar_client as ec
    handler = _make_handler({
        "https://data.sec.gov/submissions/CIK0000320193.json": SAMPLE_SUBMISSIONS,
    })
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    out = ec.list_filings("0000320193", forms=("10-K",), since_year=2024)
    assert len(out) == 1
    f = out[0]
    assert f["form"] == "10-K"
    assert f["accession"] == "0000320193-24-000123"
    assert f["url"].startswith("https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/")
    assert f["primary_document"] == "aapl-20240928.htm"


def test_extract_sections_recovers_item_headers():
    from marvin.tools.edgar_client import _TextOnly, extract_sections
    p = _TextOnly()
    p.feed(SAMPLE_10K_HTML)
    text = p.get_text()
    out = extract_sections(text)
    assert out["business"] is not None and "smartphones" in out["business"]
    assert out["risk_factors"] is not None and "factors" in out["risk_factors"].lower()
    assert out["mdna"] is not None and "net sales" in out["mdna"].lower()
    assert out["financial_statements"] is not None


def test_search_sec_filings_returns_real_metadata(monkeypatch):
    import marvin.tools.edgar_client as ec
    from marvin.tools.calculus_tools import search_sec_filings
    handler = _make_handler({
        "https://www.sec.gov/files/company_tickers.json": SAMPLE_TICKERS,
        "https://data.sec.gov/submissions/CIK0000320193.json": SAMPLE_SUBMISSIONS,
    })
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    out = search_sec_filings("AAPL", year=2024)
    assert out.get("error") in (None, "")
    assert out["cik"] == "0000320193"
    assert out["ticker"] == "AAPL"
    assert len(out["filings"]) == 1
    assert "sec.gov" in out["filings"][0]["url"]


def test_search_sec_filings_matches_fiscal_year_when_10k_filed_next_year(monkeypatch):
    import marvin.tools.edgar_client as ec
    from marvin.tools.calculus_tools import search_sec_filings

    tickers = {
        **SAMPLE_TICKERS,
        "4": {"cik_str": 1543151, "ticker": "UBER", "title": "Uber Technologies, Inc."},
    }
    handler = _make_handler({
        "https://www.sec.gov/files/company_tickers.json": tickers,
        "https://data.sec.gov/submissions/CIK0001543151.json": UBER_FY2024_FILED_2025_SUBMISSIONS,
    })
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))

    out = search_sec_filings("Uber Technologies Inc.", year=2024)

    assert out.get("error") in (None, "")
    assert out["ticker"] == "UBER"
    assert len(out["filings"]) == 1
    assert out["filings"][0]["filing_date"] == "2025-02-14"
    assert out["filings"][0]["report_date"] == "2024-12-31"


def test_search_sec_filings_unknown_company_returns_error(monkeypatch):
    import marvin.tools.edgar_client as ec
    from marvin.tools.calculus_tools import search_sec_filings
    handler = _make_handler({"https://www.sec.gov/files/company_tickers.json": SAMPLE_TICKERS})
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    out = search_sec_filings("definitely-not-a-real-co", year=2024)
    assert out["error"] == "company_not_found_on_edgar"
    assert out["filings"] == []


def test_fetch_filing_section_returns_quotable_text(monkeypatch):
    import marvin.tools.edgar_client as ec
    from marvin.tools.calculus_tools import fetch_filing_section
    archive_prefix = "https://www.sec.gov/Archives/edgar/data/320193/"
    handler = _make_handler({
        "https://www.sec.gov/files/company_tickers.json": SAMPLE_TICKERS,
        "https://data.sec.gov/submissions/CIK0000320193.json": SAMPLE_SUBMISSIONS,
        archive_prefix: SAMPLE_10K_HTML,
    })
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    out = fetch_filing_section("AAPL", form="10-K", year=2024, section="risk_factors")
    assert out["error"] is None
    assert out["text"] is not None
    assert "factors" in out["text"].lower()
    assert out["url"].startswith(archive_prefix)
    assert out["accession"] == "0000320193-24-000123"


def test_fetch_filing_section_matches_fiscal_year_when_10k_filed_next_year(monkeypatch):
    import marvin.tools.edgar_client as ec
    from marvin.tools.calculus_tools import fetch_filing_section

    tickers = {
        **SAMPLE_TICKERS,
        "4": {"cik_str": 1543151, "ticker": "UBER", "title": "Uber Technologies, Inc."},
    }
    archive_prefix = "https://www.sec.gov/Archives/edgar/data/1543151/"
    handler = _make_handler({
        "https://www.sec.gov/files/company_tickers.json": tickers,
        "https://data.sec.gov/submissions/CIK0001543151.json": UBER_FY2024_FILED_2025_SUBMISSIONS,
        archive_prefix: SAMPLE_10K_HTML,
    })
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))

    out = fetch_filing_section("Uber", form="10-K", year=2024, section="mdna")

    assert out["error"] is None
    assert out["ticker"] == "UBER"
    assert out["filing_date"] == "2025-02-14"
    assert out["report_date"] == "2024-12-31"
    assert out["text"] is not None


def test_fetch_filing_section_unknown_company_returns_no_quote(monkeypatch):
    import marvin.tools.edgar_client as ec
    from marvin.tools.calculus_tools import fetch_filing_section
    handler = _make_handler({"https://www.sec.gov/files/company_tickers.json": SAMPLE_TICKERS})
    monkeypatch.setattr(ec, "_HTTP_CLIENT_FACTORY", _factory(handler))
    out = fetch_filing_section("not-real-co", form="10-K", year=2024, section="mdna")
    assert out["error"] == "company_not_found_on_edgar"
    assert out["text"] is None
    assert out["url"] is None
