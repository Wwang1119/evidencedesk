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


SYNTHETIC_PROXY_RANGE = ipaddress.ip_network("198.18.0.0/15")
PUBLIC_DNS_URL = "https://cloudflare-dns.com/dns-query"


async def resolve_public(url, client=None):
    """Resolve and validate a target; never connect to a synthetic or private IP.

    Only a hostname resolved entirely into the proxy benchmarking range may use
    the public-DNS fallback. Literal IPs and private DNS answers cannot use it.
    """
    safe = canonical_url(url)
    if not safe:
        raise ValueError("Unsupported URL")
    host = urlsplit(safe).hostname
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        raise ValueError("Private host blocked")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise ValueError("Non-public address blocked")
        return safe, str(literal)
    loop = asyncio.get_running_loop()
    try:
        records = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), timeout=5)
    except (OSError, TimeoutError):
        raise ValueError("DNS lookup failed") from None
    addresses = list(dict.fromkeys(ipaddress.ip_address(record[4][0]) for record in records))
    synthetic = addresses and all(a.version == 4 and a in SYNTHETIC_PROXY_RANGE for a in addresses)
    if synthetic and client is not None:
        # Public research domains only. No provider credentials accompany this request.
        response = await client.get(PUBLIC_DNS_URL, params={"name": host, "type": "A"},
                                    headers={"Accept": "application/dns-json"},
                                    follow_redirects=False, timeout=8)
        if response.status_code != 200:
            raise ValueError("Public DNS lookup failed")
        data = response.json()
        if not isinstance(data, dict) or data.get("Status") != 0:
            raise ValueError("Public DNS lookup failed")
        answers = data.get("Answer", [])
        if not isinstance(answers, list) or any(not isinstance(answer, dict) for answer in answers):
            raise ValueError("Invalid public DNS response")
        addresses = [ipaddress.ip_address(answer.get("data", "")) for answer in answers
                     if answer.get("type") in (1, 28)]
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Non-public address blocked")
    addresses.sort(key=lambda a: a.version)
    return safe, str(addresses[0])


async def assert_public(url):
    return (await resolve_public(url))[0]


async def check_url(client, url):
    """Pin each public IP, preserve Host/TLS SNI, and recheck every redirect."""
    try:
        current = url
        for _ in range(5):
            current, address = await resolve_public(current, client)
            original = httpx.URL(current)
            async with client.stream("GET", original.copy_with(host=address), follow_redirects=False,
                                     headers={"User-Agent": "EvidenceDesk/0.1 (research source verification)",
                                              "Host": original.netloc.decode("ascii"),
                                              "Connection": "close",
                                              "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5"},
                                     extensions={"sni_hostname": original.raw_host.decode("ascii")}, timeout=12) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    current = urljoin(current, response.headers.get("location", ""))
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
