import hashlib
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


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.com", "http://localhost/a", "http://127.0.0.1", "http://169.254.169.254/latest", "http://[::1]/", "https://a.local/private"])
async def test_private_or_credential_urls_blocked(url):
    with pytest.raises(ValueError):
        await assert_public(url)


async def test_redirect_into_private_host_rejected(monkeypatch):
    async def validate(url):
        if "localhost" in url:
            raise ValueError("Private host")
        return url
    monkeypatch.setattr("evidencedesk.evidence.assert_public", validate)
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(302, headers={"location":"http://localhost/private"}))) as client:
        assert await check_url(client, "https://a.edu/study") is None


@pytest.mark.parametrize("status", [403, 404, 429, 500])
async def test_unreachable_sources_excluded(monkeypatch, status):
    monkeypatch.setattr("evidencedesk.evidence.assert_public", AsyncMock(side_effect=lambda x:x))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status))) as client:
        assert await check_url(client, "https://a.edu/study") is None
