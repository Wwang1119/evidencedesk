import httpx

from evidencedesk.config import Settings
from evidencedesk.server import app


async def test_static_ui_no_credentials_or_project_directory_listing():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "Research you can" in response.text
        assert (await client.get("/.env")).status_code == 404
        assert (await client.get("/assets/../.env")).status_code == 404


async def test_missing_keys_returns_actionable_error(monkeypatch):
    def missing(*args, **kwargs):
        from evidencedesk.config import SetupError
        raise SetupError("Add NEBIUS_API_KEY and TAVILY_API_KEY to the local .env file, then restart.")
    monkeypatch.setattr(Settings, "load", missing)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/research", json={"question":"A question about evidence"})
        assert response.status_code == 503
        assert ".env" in response.json()["detail"]


async def test_cross_site_request_cannot_spend_credits():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/research", headers={"Origin":"https://other.example"}, json={"question":"A question about evidence"})
        assert response.status_code == 403
