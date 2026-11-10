"""Offline contract tests with clearly synthetic content. These are not live evaluations."""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from evidencedesk.agent import ResearchAgent
from evidencedesk.config import Settings
from evidencedesk.providers import ProviderError, Providers

QUESTION = "What does evidence say about spaced learning in students?"
QUOTE = "Distributed practice was associated with improved retention in this synthetic experiment."
TEXT = QUOTE + " " + "This document is a synthetic test fixture with no real-world evidentiary value. " * 4


def settings():
    return Settings("test-nebius-credential", "test-tavily-credential", "synthetic-test-model")


def transport(*, review=True, quote=QUOTE, empty=False, auth_error=False, review_error=False):
    seen = []
    def handle(request):
        seen.append(request)
        body = json.loads(request.content)
        if request.url.host == "api.tavily.com":
            assert request.headers["Authorization"] == "Bearer test-tavily-credential"
            if request.url.path == "/search":
                assert body["include_answer"] is False
                return httpx.Response(200, json={"results": [] if empty else [{"url":"https://a.edu/study", "title":"Synthetic fixture", "score":.9}], "request_id":"fixture-search"})
            assert request.url.path == "/extract"
            return httpx.Response(200, json={"results":[{"url":"https://a.edu/study", "raw_content":TEXT}], "request_id":"fixture-extract"})
        assert request.url.host == "api.tokenfactory.nebius.com"
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-nebius-credential"
        assert body["model"] == "synthetic-test-model"
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        system = body["messages"][0]["content"]
        if auth_error:
            return httpx.Response(401, json={"secret":"never reflect provider response bodies"})
        if "Plan two" in system:
            result = {"queries":["spaced learning study"], "facets":["Learning"]}
        elif "Build a short" in system:
            result = {"claims":[{"text":"Distributed practice was associated with retention in the supplied experiment.","kind":"finding","facet":"Learning","citations":[{"source_id":1,"quote":quote}]}], "gaps":[],"follow_up_query":""}
        else:
            if review_error:
                return httpx.Response(401, json={"error":"unauthorized"})
            result = {"verdicts":[{"claim_index":0,"supported":review,"reason":"Synthetic fixture review result."}]}
        return httpx.Response(200, json={"id":"fixture-inference", "usage":{"total_tokens":100},"choices":[{"finish_reason":"stop","message":{"content":json.dumps(result)}}]})
    return httpx.MockTransport(handle), seen


@pytest.fixture(autouse=True)
def mock_url_check(monkeypatch):
    monkeypatch.setattr("evidencedesk.agent.check_url", AsyncMock(return_value={"final_url":"https://a.edu/study","http_status":200}))


async def run(**kwargs):
    mock, seen = transport(**kwargs)
    async with httpx.AsyncClient(transport=mock) as client:
        result = await ResearchAgent(settings(), client=client).research(QUESTION)
    return result, seen


async def test_end_to_end_wire_contract_and_citation_survival():
    result, seen = await run()
    assert result.status == "complete"
    assert len(result.claims) == 1
    assert "[1](https://a.edu/study)" in result.markdown
    assert result.claims[0].evidence[0].quote == QUOTE
    assert result.stats["calls"] == {"nebius":3,"tavily_search":1,"tavily_extract":1}
    assert len(seen) == 5
    exported = result.model_dump_json()
    assert "test-nebius-credential" not in exported
    assert "test-tavily-credential" not in exported
    assert '"text_sha256"' in exported
    assert '"text":' in exported  # claim text is exported, full source text is not
    assert TEXT not in exported


async def test_fabricated_quote_is_withheld_before_model_review():
    result, _ = await run(quote="This fabricated quotation was never retrieved from any source at all.")
    assert result.status == "insufficient_evidence"
    assert not result.claims
    assert result.stats["calls"]["nebius"] == 2
    assert result.stats["claims_withheld"] == 1


@pytest.mark.parametrize("options", [{"review":False}, {"review_error":True}])
async def test_failed_support_review_never_publishes_claim(options):
    result, _ = await run(**options)
    assert not result.claims
    assert result.status == "insufficient_evidence"


async def test_empty_search_refines_once_then_abstains():
    result, _ = await run(empty=True)
    assert result.stats["calls"]["tavily_search"] == 2
    assert result.stats["calls"]["nebius"] == 1
    assert not result.claims
    assert result.gaps


async def test_auth_error_does_not_leak_response_or_keys():
    with pytest.raises(ProviderError) as caught:
        await run(auth_error=True)
    assert "401" in str(caught.value)
    assert "secret" not in str(caught.value)
    assert "credential" not in str(caught.value)


async def test_planned_site_filter_is_enforced_by_tavily_native_filter():
    seen = []
    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"results":[]})
    async def emit(*args, **kwargs):
        pass
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await Providers(settings(), client, emit).search('original paper site:arxiv.org -site:example.org')
    assert seen[0]["include_domains"] == ["arxiv.org"]
