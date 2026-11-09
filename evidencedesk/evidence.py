"""Deterministic citation gates and bounded public-URL checks."""
import asyncio
import ipaddress
import re
import socket
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx


def normalize(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def canonical_url(url):
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
            return ""
        if parts.port not in (None, 80, 443):
            return ""
        query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in ("gclid", "fbclid")]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query), ""))
    except (ValueError, TypeError):
        return ""


async def assert_public(url):
    safe = canonical_url(url)
    if not safe:
        raise ValueError("Unsupported URL")
    host = urlsplit(safe).hostname
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        raise ValueError("Private host blocked")
    loop = asyncio.get_running_loop()
    try:
        records = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), timeout=5)
    except (OSError, TimeoutError):
        raise ValueError("DNS lookup failed") from None
    if not records or any(not ipaddress.ip_address(record[4][0]).is_global for record in records):
        raise ValueError("Non-public address blocked")
    return safe


async def check_url(client, url):
    """GET headers, do not download full bodies. Recheck each redirect's target."""
    try:
        current = await assert_public(url)
        for _ in range(5):
            async with client.stream("GET", current, follow_redirects=False,
                                     headers={"User-Agent": "EvidenceDesk/0.1 (research source verification)",
                                              "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5"}, timeout=12) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    current = await assert_public(urljoin(current, response.headers.get("location", "")))
                    continue
                if response.status_code != 200:
                    return None
                return {"final_url": current, "http_status": response.status_code}
    except (ValueError, httpx.RequestError):
        return None
    return None


def rank_candidates(results, limit=6):
    """Search score plus a transparent primary-source heuristic; never a truth score."""
    unique = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        url = canonical_url(result.get("url", ""))
        if not url or url in unique:
            continue
        host = urlsplit(url).hostname
        primary_hint = bool(re.search(r"\.(gov|edu)(\.|$)", host) or host in ("arxiv.org", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov") or host.startswith("docs."))
        try:
            score = float(result.get("score", 0))
        except (ValueError, TypeError):
            score = 0
        unique[url] = {**result, "url": url, "domain": host,
                       "rank": score + (0.15 if primary_hint else 0),
                       "selection_note": "Primary-source domain heuristic; check authorship and methods." if primary_hint else "Ranked by search relevance; source authority needs reader judgment."}
    selected, counts = [], {}
    for item in sorted(unique.values(), key=lambda r: r["rank"], reverse=True):
        domain = item["domain"].removeprefix("www.")
        if counts.get(domain, 0) >= 2:
            continue
        counts[domain] = counts.get(domain, 0) + 1
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def evidence_for_claim(claim, sources):
    """All citations must exist and quote a contiguous passage, case-sensitively."""
    by_id = {source.id: source for source in sources}
    evidence = []
    if re.search(r"https?://|\[\d+\]", claim.text):
        return None, "Model-generated URLs or citation numbers in claim text were rejected."
    for citation in claim.citations:
        source = by_id.get(citation.source_id)
        if source is None:
            return None, "Citation references an unknown source."
        quote, text = normalize(citation.quote), normalize(source.text)
        if len(quote) < 20 or len(quote.split()) < 4:
            return None, "Evidence quote was too short."
        position = text.find(quote)
        if position < 0:
            return None, "Evidence quote was not found in the retrieved source."
        evidence.append({"source_id": source.id, "quote": quote,
                         "context": text[max(0, position-200):position+len(quote)+300]})
    return evidence, ""
