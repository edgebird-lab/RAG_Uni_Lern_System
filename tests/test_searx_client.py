"""Tests fuer ragapp.searx_client (Mock-HTTP, Allowlist)."""
from __future__ import annotations

import httpx
import pytest

from ragapp import searx_client
from ragapp.searx_client import (
    SCIENCE_DOMAIN_ALLOWLIST,
    SearxError,
    domain_allowed,
    search_science,
)


def test_domain_allowed_arxiv_and_pubmed():
    assert domain_allowed("https://arxiv.org/abs/1234.5678")
    assert domain_allowed("https://pubmed.ncbi.nlm.nih.gov/123/")
    assert domain_allowed("https://doi.org/10.1000/xyz")
    assert not domain_allowed("https://example.com/paper")
    assert not domain_allowed("https://random-blog.net/post")


def test_domain_allowed_uses_custom_allowlist():
    assert domain_allowed("https://foo.example/x", allowlist=("example",))
    assert not domain_allowed("https://foo.example/x", allowlist=("arxiv.org",))


def test_search_science_requires_enabled(monkeypatch):
    monkeypatch.setattr(searx_client.settings, "SEARXNG_ENABLED", False)
    with pytest.raises(SearxError, match="ausgeschaltet"):
        search_science("quantum computing")


def test_search_science_filters_allowlist(monkeypatch):
    monkeypatch.setattr(searx_client.settings, "SEARXNG_ENABLED", True)
    monkeypatch.setattr(searx_client.settings, "SEARXNG_BASE_URL", "https://search.test/")
    monkeypatch.setattr(searx_client.settings, "SEARXNG_TIMEOUT_S", 5.0)
    monkeypatch.setattr(searx_client.settings, "SEARXNG_MAX_RESULTS", 10)

    payload = {
        "results": [
            {"title": "Good", "url": "https://arxiv.org/abs/1", "content": "a"},
            {"title": "Bad", "url": "https://spam.example/x", "content": "b"},
            {"title": "Nature", "url": "https://www.nature.com/articles/1", "content": "c"},
        ]
    }

    class _Resp:
        status_code = 200

        def json(self):
            return payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, params=None):
            return _Resp()

    monkeypatch.setattr(searx_client.httpx, "Client", _Client)
    hits = search_science("test query")
    urls = [h.url for h in hits]
    assert "https://arxiv.org/abs/1" in urls
    assert "https://www.nature.com/articles/1" in urls
    assert all("spam.example" not in u for u in urls)


def test_search_science_timeout_raises(monkeypatch):
    monkeypatch.setattr(searx_client.settings, "SEARXNG_ENABLED", True)
    monkeypatch.setattr(searx_client.settings, "SEARXNG_BASE_URL", "https://search.test/")

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(searx_client.httpx, "Client", _Client)
    with pytest.raises(SearxError, match="Zeitüberschreitung"):
        search_science("x")


def test_allowlist_covers_expected_publishers():
    # Sanity: Kern-Hosts aus dem Plan sind drin
    for host in ("arxiv.org", "doi.org", "nature.com", "ieee.org",
                 "acm.org", "semanticscholar.org", "openalex.org"):
        assert any(host in a for a in SCIENCE_DOMAIN_ALLOWLIST), host
