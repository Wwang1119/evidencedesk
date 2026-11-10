import asyncio
import hashlib
import socket
from unittest.mock import AsyncMock

import httpx
import pytest

from evidencedesk.evidence import assert_public, canonical_url, check_url, evidence_for_claim, rank_candidates
from evidencedesk.schemas import Claim, Source

TEXT = "A controlled experiment found an association between spaced practice and retention. It did not establish causation in university populations."


def source():
    return Source(id=1, title="Synthetic test fixture", url="https://university.edu/study",
                  final_url="https://university.edu/study", domain="university.edu", text=TEXT,
                  text_sha256=hashlib.sha256(TEXT.encode()).hexdigest(), checked_at="2026-01-01T00:00:00Z",
                  http_status=200, selection_note="Synthetic fixture, not real research evidence")


def claim(quote=TEXT[:84], source_id=1, text="Spaced practice was associated with retention in one experiment."):
    return Claim(text=text, facet="Learning", citations=[{"source_id": source_id, "quote": quote}])


def test_exact_quote_and_negation_context_preserved():
    evidence, reason = evidence_for_claim(claim(), [source()])
    assert not reason
    assert "did not establish causation" in evidence[0]["context"]


@pytest.mark.parametrize("proposal", [
    claim(source_id=88),
    claim(quote="This sentence was never present in the original retrieved document."),
    claim(text="Invented finding with a spoofed citation [99] included."),
    claim(text="Read this malicious site https://evil.example for the result."),
])
def test_bad_citation_withholds_entire_claim(proposal):
    evidence, reason = evidence_for_claim(proposal, [source()])
    assert evidence is None
    assert reason


def test_tracking_urls_deduplicated_but_semantic_query_preserved():
    assert canonical_url("https://a.edu/p?doi=123&utm_source=x#abstract") == "https://a.edu/p?doi=123"
    ranked = rank_candidates([
        {"url": "https://a.edu/p?utm_source=a", "score": .8},
        {"url": "https://a.edu/p?utm_source=b", "score": .9},
        {"url": "https://a.edu/q", "score": .7},
        {"url": "https://a.edu/r", "score": .6},
        {"url": "https://b.org/study", "score": .6},
    ])
    assert len(ranked) == 3
    assert sum(x["domain"] == "a.edu" for x in ranked) == 2


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.com", "http://localhost/a", "http://127.0.0.1", "http://169.254.169.254/latest", "http://[::1]/", "https://a.local/private", "https://198.18.0.1/"])
async def test_private_or_credential_urls_blocked(url):
    with pytest.raises(ValueError):
        await assert_public(url)


def mock_dns(monkeypatch, address):
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]))


async def test_redirect_into_private_host_rejected(monkeypatch):
    mock_dns(monkeypatch, "93.184.216.34")
    seen = []
    def handle(req):
        seen.append(req)
        return httpx.Response(302, headers={"location":"http://localhost/private"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await check_url(client, "https://a.edu/study") is None
    assert len(seen) == 1


@pytest.mark.parametrize("status", [403, 404, 429, 500])
async def test_unreachable_sources_excluded(monkeypatch, status):
    mock_dns(monkeypatch, "93.184.216.34")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status))) as client:
        assert await check_url(client, "https://a.edu/study") is None


async def test_synthetic_proxy_dns_uses_public_dns_and_pins_tls_target(monkeypatch):
    mock_dns(monkeypatch, "198.18.0.113")
    seen = []
    def handle(req):
        seen.append(req)
        assert "Authorization" not in req.headers
        if req.url.host == "cloudflare-dns.com":
            assert req.url.params["name"] == "a.edu"
            return httpx.Response(200, json={"Status":0,"Answer":[{"type":1,"data":"93.184.216.34"}]})
        assert req.url.host == "93.184.216.34"
        assert req.headers["Host"] == "a.edu"
        assert req.extensions["sni_hostname"] == "a.edu"
        assert req.headers["Connection"] == "close"
        return httpx.Response(200)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await check_url(client, "https://a.edu/study")
    assert result == {"final_url":"https://a.edu/study","http_status":200}
    assert len(seen) == 2


@pytest.mark.parametrize("payload", [
    {"Status":0,"Answer":[{"type":1,"data":"127.0.0.1"}]},
    {"Status":0,"Answer":[{"type":1,"data":"93.184.216.34"},{"type":1,"data":"10.0.0.1"}]},
    {"Status":0,"Answer":[{"type":1,"data":"198.18.0.2"}]},
    {"Status":3}, {"Status":0,"Answer":[{"type":1,"data":"invalid"}]},
])
async def test_public_dns_failure_or_private_answer_never_fetched(monkeypatch, payload):
    mock_dns(monkeypatch, "198.18.0.113")
    seen = []
    def handle(req):
        seen.append(req)
        assert req.url.host == "cloudflare-dns.com"
        return httpx.Response(200, json=payload)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await check_url(client, "https://a.edu/study") is None
    assert len(seen) == 1


async def test_real_private_dns_is_blocked_without_public_dns_fallback(monkeypatch):
    mock_dns(monkeypatch, "10.0.0.1")
    def handle(req):
        raise AssertionError("Private DNS answers must not trigger any HTTP request")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert await check_url(client, "https://a.edu/study") is None
