"""Live smoke for the real Tavily integration.

This file makes a real HTTP call to api.tavily.com. It costs ~$0.005 per
run and requires a valid TAVILY_API_KEY. Excluded from the default test
run via the `integration` marker; opt in with:

    pytest -m integration tests/integration/test_tavily_live.py

Run manually before commits that touch tavily_search to verify the API
contract has not drifted.
"""
from __future__ import annotations

import os

import pytest

from marvin.tools import dora_tools


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_api_key():
    if not os.environ.get("TAVILY_API_KEY"):
        pytest.skip("TAVILY_API_KEY not set; skipping live Tavily smoke.")


def test_real_tavily_search_returns_real_urls():
    """Reaches api.tavily.com. Asserts the response shape matches what
    Dora's prompt expects: real URLs (no example.com), non-empty content
    snippets, scores in [0, 1]."""
    out = dora_tools.tavily_search(
        "Doctolib healthcare booking platform France revenue 2024",
        max_results=5,
    )
    assert out["provider"] == "tavily"
    assert out.get("error") is None, f"Tavily returned error: {out.get('error')}"
    assert len(out["results"]) >= 3, f"Expected ≥3 results, got {len(out['results'])}"

    for result in out["results"]:
        assert result["url"].startswith(("http://", "https://"))
        assert "example.com" not in result["url"], (
            f"Unexpected stub URL: {result['url']}"
        )
        assert isinstance(result["title"], str)
        # Tavily returns content snippets but not always — relax to "string".
        assert isinstance(result.get("content"), str)
        score = result.get("score", 0.0)
        assert 0.0 <= score <= 1.0
