"""Unit tests for marvin.tools.dora_tools.tavily_search.

Mocks Tavily HTTP via httpx.MockTransport — no real network calls. The
real-API smoke lives in tests/integration/test_tavily_live.py and is
excluded from the default test run.
"""
from __future__ import annotations

import json

import httpx
import pytest

from marvin.tools import dora_tools


@pytest.fixture
def mock_tavily(monkeypatch):
    """Return a helper that installs an httpx.MockTransport for the Tavily
    endpoint. Each call replaces dora_tools._HTTP_CLIENT_FACTORY with a
    Client constructor bound to the supplied response handler."""

    def install(handler):
        def _factory(*, timeout=None):
            transport = httpx.MockTransport(handler)
            return httpx.Client(transport=transport, timeout=timeout)

        monkeypatch.setattr(dora_tools, "_HTTP_CLIENT_FACTORY", _factory)

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
    return install


def _ok(payload):
    return lambda request: httpx.Response(200, json=payload)


def test_returns_real_results_when_api_succeeds(mock_tavily):
    mock_tavily(
        _ok(
            {
                "results": [
                    {
                        "title": "Doctolib official site",
                        "url": "https://www.doctolib.fr/about",
                        "content": "Doctolib operates across France, Germany, Italy ...",
                        "score": 0.92,
                    },
                    {
                        "title": "Industry coverage",
                        "url": "https://techcrunch.com/2024/doctolib-revenue",
                        "content": "Reported €600M revenue in FY2024 ...",
                        "score": 0.81,
                    },
                ]
            }
        )
    )

    out = dora_tools.tavily_search("Doctolib revenue 2024")

    assert out["provider"] == "tavily"
    assert out["query"] == "Doctolib revenue 2024"
    assert "error" not in out
    urls = [r["url"] for r in out["results"]]
    assert urls == [
        "https://www.doctolib.fr/about",
        "https://techcrunch.com/2024/doctolib-revenue",
    ]
    assert all("example.com" not in u for u in urls)
    assert out["results"][0]["content"].startswith("Doctolib operates")
    assert out["results"][0]["score"] == 0.92


def test_handles_missing_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = dora_tools.tavily_search("anything")
    assert out["error"] == "no_api_key"
    assert out["results"] == []
    assert out["provider"] == "tavily"


def test_handles_api_error_500(mock_tavily):
    mock_tavily(lambda req: httpx.Response(500, json={"error": "server"}))
    out = dora_tools.tavily_search("anything")
    assert out["error"] == "http_500"
    assert out["results"] == []


def test_handles_rate_limit_429(mock_tavily):
    mock_tavily(lambda req: httpx.Response(429, json={"error": "too many"}))
    out = dora_tools.tavily_search("anything")
    assert out["error"] == "rate_limited"
    assert out["results"] == []


def test_handles_network_timeout(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")

    def _raising_factory(*, timeout=None):
        def _handler(request):
            raise httpx.ConnectTimeout("simulated timeout")

        transport = httpx.MockTransport(_handler)
        return httpx.Client(transport=transport, timeout=timeout)

    monkeypatch.setattr(dora_tools, "_HTTP_CLIENT_FACTORY", _raising_factory)

    out = dora_tools.tavily_search("anything")
    assert out["error"] == "network"
    assert out["results"] == []


def test_truncates_long_content_to_500_chars(mock_tavily):
    mock_tavily(
        _ok(
            {
                "results": [
                    {
                        "title": "Big article",
                        "url": "https://example-real.com/article",
                        "content": "x" * 10_000,
                        "score": 0.5,
                    }
                ]
            }
        )
    )
    out = dora_tools.tavily_search("anything")
    assert len(out["results"][0]["content"]) == 500


def test_passes_max_results_parameter(mock_tavily, monkeypatch):
    captured: dict = {}

    def _factory(*, timeout=None):
        def _handler(request):
            captured["payload"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"results": []})

        return httpx.Client(transport=httpx.MockTransport(_handler), timeout=timeout)

    monkeypatch.setattr(dora_tools, "_HTTP_CLIENT_FACTORY", _factory)

    dora_tools.tavily_search("query", max_results=10)

    assert captured["payload"]["max_results"] == 10
    assert captured["payload"]["query"] == "query"
    assert captured["payload"]["api_key"] == "tvly-test-key"
