import argparse
import asyncio
import json
from pathlib import Path
import sys

import httpx

from .agent import ResearchAgent
from .config import Settings, SetupError
from .providers import ProviderError, Providers
from .schemas import Plan


async def quiet(*args, **kwargs):
    pass


async def doctor(settings):
    """Two separate, real API probes. No keys or response bodies in logs."""
    failed = False
    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        providers = Providers(settings, client, quiet)
        for service in ("Nebius Token Factory", "Tavily"):
            try:
                if service == "Nebius Token Factory":
                    result = await providers.model("Return a JSON object with queries=['test'] and facets=['test'].", {}, Plan, stage="connectivity test", max_tokens=100)
                    ok = bool(result.queries)
                else:
                    ok = bool(await providers.search("Tavily official search API documentation"))
                print(f"{service}: {'PASS (live response)' if ok else 'FAIL (empty response)'}")
                failed |= not ok
            except ProviderError as exc:
                print(f"{service}: FAIL — {exc}")
                failed = True
    return 1 if failed else 0


async def run_ask(settings, args):
    async def progress(event):
        if "message" in event:
            print(f"[{event['elapsed']:6.1f}s] {event['message']}", file=sys.stderr)
    brief = await ResearchAgent(settings, progress).research(args.question)
    print(brief.markdown)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{brief.id}.json").write_text(brief.model_dump_json(indent=2), encoding="utf-8")
        (out / f"{brief.id}.md").write_text(brief.markdown, encoding="utf-8")
    return 0 if brief.claims else 2


async def list_models(settings):
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.get("https://api.tokenfactory.nebius.com/v1/models",
                                    headers={"Authorization": f"Bearer {settings.nebius_key}"})
        if response.status_code != 200:
            raise ProviderError(f"Model catalog returned HTTP {response.status_code}.")
        for model in response.json().get("data", []):
            print(model["id"])


def main():
    parser = argparse.ArgumentParser(description="EvidenceDesk — research with inspectable citations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Make a minimal real call to each required API")
    sub.add_parser("models", help="List models in the live Nebius catalog")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--out", help="Save an auditable Markdown/JSON brief")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn
            uvicorn.run("evidencedesk.server:app", host="127.0.0.1", port=args.port, log_level="warning")
            return
        settings = Settings.load()
        if args.command == "doctor":
            sys.exit(asyncio.run(doctor(settings)))
        elif args.command == "models":
            asyncio.run(list_models(settings))
        else:
            sys.exit(asyncio.run(run_ask(settings, args)))
    except (SetupError, ProviderError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except (httpx.RequestError, json.JSONDecodeError):
        print("The service could not be reached or returned invalid data. Check connectivity and retry.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
