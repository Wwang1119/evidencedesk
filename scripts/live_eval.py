"""Actual API evaluation. Never substitutes fixtures or cached answers."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidencedesk.agent import ResearchAgent
from evidencedesk.config import ROOT, Settings
from evidencedesk.providers import ProviderError


async def main():
    settings = Settings.load()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / ".local" / "evaluation" / stamp
    out.mkdir(parents=True, exist_ok=False)
    prompts = json.loads((ROOT / "examples" / "questions.json").read_text())
    rows = []
    for prompt in prompts:
        print(f"Running real APIs: {prompt['id']}", flush=True)
        try:
            brief = await ResearchAgent(settings).research(prompt["question"])
            (out / f"{prompt['id']}.json").write_text(brief.model_dump_json(indent=2))
            (out / f"{prompt['id']}.md").write_text(brief.markdown)
            rows.append({"example":prompt["id"], "status":brief.status, **brief.stats,
                         "manual_source_review":"pending", "inspection_prompt":prompt["inspect"]})
        except ProviderError as exc:
            rows.append({"example":prompt["id"], "status":"provider_error", "error":str(exc)})
        (out / "summary.json").write_text(json.dumps(rows, indent=2))
    print(f"Saved actual results to {out}. Manual source review is still required.")


if __name__ == "__main__":
    asyncio.run(main())
