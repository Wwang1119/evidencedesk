import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import ResearchAgent
from .config import Settings, SetupError
from .providers import ProviderError

WEB = Path(__file__).parent / "web"
app = FastAPI(title="EvidenceDesk", docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.mount("/assets", StaticFiles(directory=WEB), name="assets")
busy = asyncio.Lock()


class Question(BaseModel):
    question: str = Field(min_length=10, max_length=1200)


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/status")
async def status():
    settings = Settings.load(require_keys=False)
    return {"ready": bool(settings.nebius_key and settings.tavily_key), "model": settings.model,
            "nebius_configured": bool(settings.nebius_key), "tavily_configured": bool(settings.tavily_key)}


@app.post("/api/research")
async def research(question: Question, request: Request):
    # Local-only application: prevent cross-site pages from spending the user's API credits.
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Open EvidenceDesk directly to start research.")
    if busy.locked():
        raise HTTPException(429, "A research run is in progress. Wait for it to finish.")
    try:
        settings = Settings.load()
    except SetupError as exc:
        raise HTTPException(503, str(exc)) from None
    await busy.acquire()

    async def stream():
        queue = asyncio.Queue()
        async def event(data):
            await queue.put({"type": "progress", **data})
        async def work():
            try:
                result = await ResearchAgent(settings, event).research(question.question)
                await queue.put({"type": "result", "brief": result.model_dump()})
            except (ProviderError, ValueError) as exc:
                await queue.put({"type": "error", "message": str(exc)})
            except Exception:
                await queue.put({"type": "error", "message": "Research could not complete. No unvalidated answer was published."})
            finally:
                await queue.put(None)
        task = asyncio.create_task(work())
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    yield json.dumps({"type": "heartbeat"}) + "\n"
                    continue
                if data is None:
                    break
                yield json.dumps(data, ensure_ascii=False) + "\n"
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            busy.release()
    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
