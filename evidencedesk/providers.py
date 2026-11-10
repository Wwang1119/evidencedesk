"""Real REST calls. Only the official Token Factory and Tavily hosts get keys."""
import asyncio
import json
import re
from time import perf_counter

import httpx
from pydantic import ValidationError

from .config import Settings


class ProviderError(Exception):
    """Safe to display: never includes response bodies, prompts or credentials."""


class Providers:
    def __init__(self, settings: Settings, client: httpx.AsyncClient, emit):
        self.settings, self.client, self.emit = settings, client, emit
        self.calls = {"nebius": 0, "tavily_search": 0, "tavily_extract": 0}
        self.tokens = 0

    async def _post(self, service, url, key, body):
        # One bounded retry for transient service failures. No retry on auth/credit errors.
        for attempt in range(2):
            try:
                response = await self.client.post(url, headers={"Authorization": f"Bearer {key}"}, json=body)
            except httpx.RequestError:
                if not attempt:
                    await asyncio.sleep(0.7)
                    continue
                raise ProviderError(f"{service} could not be reached. Check your connection and retry.") from None
            if response.status_code in (429, 500, 502, 503, 504) and not attempt:
                await asyncio.sleep(1)
                continue
            if response.status_code >= 400:
                hints = {401: "Check your API key.", 402: "Check available credits.",
                         403: "Check account access and credits.", 429: "Rate limit reached; retry later.",
                         404: "Check the configured model against the live model catalog."}
                raise ProviderError(f"{service} returned HTTP {response.status_code}. " + hints.get(response.status_code, "Try again later."))
            try:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError
                return data
            except ValueError:
                raise ProviderError(f"{service} returned an invalid JSON response.") from None

    async def model(self, system, payload, schema, *, stage, max_tokens=3500):
        self.calls["nebius"] += 1
        started = perf_counter()
        data = await self._post("Nebius Token Factory", "https://api.tokenfactory.nebius.com/v1/chat/completions",
                                self.settings.nebius_key, {
            "model": self.settings.model,
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "schema": schema.model_json_schema(), "strict": True,
            }},
            "messages": [
                {"role": "system", "content": system + "\nReturn only a JSON object matching this schema:\n" + json.dumps(schema.model_json_schema())},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        })
        self.tokens += int(data.get("usage", {}).get("total_tokens", 0))
        await self.emit("tool", service="Nebius Token Factory", operation=stage,
                        model=self.settings.model, request_id=data.get("id"),
                        seconds=round(perf_counter()-started, 2), usage=data.get("usage", {}))
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ValueError
            content = choice["message"]["content"]
            # Some open models wrap a valid JSON object in fences or thinking tags.
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
            return schema.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise ProviderError(f"Token Factory returned an invalid or incomplete {stage} result. No unvalidated answer was published.") from None

    async def search(self, query):
        self.calls["tavily_search"] += 1
        started = perf_counter()
        body = {
            "query": query, "search_depth": "advanced", "topic": "general",
            "max_results": 5, "include_answer": False, "include_raw_content": False,
        }
        domains = re.findall(r"(?<![-\w])site:((?:[a-z0-9-]+\.)+[a-z]{2,})(?=\s|$)", query.lower())
        if domains:
            body["include_domains"] = list(dict.fromkeys(domains))
        data = await self._post("Tavily Search", "https://api.tavily.com/search", self.settings.tavily_key, body)
        await self.emit("tool", service="Tavily", operation="search", query=query,
                        results=len(data.get("results", [])), request_id=data.get("request_id"),
                        seconds=round(perf_counter()-started, 2))
        return data.get("results", [])

    async def extract(self, urls):
        self.calls["tavily_extract"] += 1
        data = await self._post("Tavily Extract", "https://api.tavily.com/extract", self.settings.tavily_key, {
            "urls": urls, "extract_depth": "advanced", "format": "text",
        })
        await self.emit("tool", service="Tavily", operation="extract", results=len(data.get("results", [])),
                        failed=len(data.get("failed_results", [])), request_id=data.get("request_id"))
        return data
